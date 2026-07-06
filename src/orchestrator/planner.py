"""Turn a task into a validated Plan with one model call and bounded retries.

A single request does both decomposition and app selection: the registry is small,
so one structured call is cheaper and makes record/replay trivial. The response is
validated by ``validation.parse_plan``; on failure the concrete error is fed back to
the model for up to ``max_retries`` corrections before giving up. Every retry is a
distinct request (extra messages), so each records/replays as its own fixture.
"""

from __future__ import annotations

import json
from pathlib import Path

from orchestrator.llm.base import LLMClient, LLMRequest
from orchestrator.models import Plan
from orchestrator.registry import Registry
from orchestrator.validation import PlanValidationError, parse_plan

PROMPT_VERSION = "1"
_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "planner_system.md"
_MAX_TOKENS = 8000


class PlannerError(RuntimeError):
    """The model did not produce a valid plan within the retry budget."""


def load_system_prompt() -> str:
    return _PROMPT_PATH.read_text()


def _registry_json(registry: Registry) -> str:
    apps = [app.to_prompt_dict() for app in registry.apps]
    return json.dumps({"apps": apps}, sort_keys=True, separators=(",", ":"))


def build_user_message(registry: Registry, task: str) -> str:
    return (
        f"AVAILABLE APPS (JSON):\n{_registry_json(registry)}\n\n"
        f"TASK:\n{task}\n\n"
        "Return the plan as one raw JSON object only."
    )


def plan_task(
    client: LLMClient,
    registry: Registry,
    task: str,
    *,
    model: str,
    max_retries: int = 2,
) -> Plan:
    """Ask the model for a plan, validating and retrying on invalid output.

    Returns the validated Plan. Raises PlannerError if every attempt is invalid.
    """
    system = load_system_prompt()
    messages: list[dict[str, str]] = [
        {"role": "user", "content": build_user_message(registry, task)}
    ]
    last_error = ""
    for _attempt in range(max_retries + 1):
        request = LLMRequest(
            model=model,
            system=system,
            messages=tuple(messages),
            max_tokens=_MAX_TOKENS,
        )
        raw = client.complete(request)
        try:
            return parse_plan(raw, registry, task=task, model=model, prompt_version=PROMPT_VERSION)
        except PlanValidationError as exc:
            last_error = str(exc)
            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"That response was invalid: {last_error}. "
                        "Return corrected raw JSON only — no prose, no code fences."
                    ),
                }
            )
    raise PlannerError(
        f"model did not produce a valid plan after {max_retries + 1} attempts; "
        f"last error: {last_error}"
    )
