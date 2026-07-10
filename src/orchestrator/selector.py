"""Pick which app operation to call for a subtask, and its arguments (one LLM call).

Grounded: the model is shown ONLY the app's real operations (name + request_fields) and must
return one of them; the returned arguments are filtered to that operation's known request fields.
Endpoints are never invented — they come from the registry.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from orchestrator.llm.base import LLMClient, LLMRequest
from orchestrator.models import Subtask, SubtaskResult
from orchestrator.registry import AppEntry, AppOperation

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "operation_select_system.md"
_MAX_TOKENS = 2000  # headroom for arguments that embed code, so JSON isn't truncated mid-string
_UPSTREAM_LIMIT = 2000  # chars per upstream result — enough to keep ids, bounded for tokens


class SelectionError(ValueError):
    """The model did not pick a valid operation for the app."""


def load_system_prompt() -> str:
    return _PROMPT_PATH.read_text()


def _operations_view(app: AppEntry) -> list[dict[str, Any]]:
    return [
        {
            "name": op.name,
            "description": op.description,
            "method": op.method,
            "request_fields": list(op.request_fields),
        }
        for op in app.operations
    ]


def _summarize_output(output: Any, limit: int = _UPSTREAM_LIMIT) -> str:
    """A compact, length-bounded view of one upstream result that PRESERVES ids.

    Unlike the relevance guard's title-only summary, this keeps concrete field values (an
    ``arxiv_id``, a url, …) so a downstream step can lift the value it needs out of it. Long
    lists are capped to their first items rather than truncated mid-field.
    """
    if isinstance(output, list):
        output = output[:5]
    text = output if isinstance(output, str) else json.dumps(output, default=str)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "…"


def _upstream_block(upstream: Sequence[SubtaskResult]) -> str:
    lines = [f"- [{r.subtask_id}] {r.app_name}: {_summarize_output(r.output)}" for r in upstream]
    return "UPSTREAM RESULTS (outputs of the steps this subtask depends on):\n" + "\n".join(lines)


def build_select_message(
    app: AppEntry, subtask: Subtask, upstream: Sequence[SubtaskResult] = ()
) -> str:
    view = json.dumps(
        {"app": app.name, "operations": _operations_view(app)},
        sort_keys=True,
        separators=(",", ":"),
    )
    parts = [f"APP OPERATIONS (JSON):\n{view}"]
    if upstream:
        parts.append(_upstream_block(upstream))
    parts.append(f"SUBTASK:\n{subtask.title}: {subtask.description}")
    parts.append(
        'Return one raw JSON object: {"operation": "<name>", "arguments": {<field>: <value>}}.'
    )
    return "\n\n".join(parts)


def _strip_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _parse_selection(raw: str, app: AppEntry) -> tuple[AppOperation, dict[str, Any]]:
    """Parse and ground one selection response. Raises SelectionError on any problem."""
    try:
        payload = json.loads(_strip_fences(raw))
    except json.JSONDecodeError as exc:
        raise SelectionError(f"operation selection was not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise SelectionError("operation selection must be a JSON object")

    name = payload.get("operation")
    if not isinstance(name, str) or not name:
        raise SelectionError("operation selection is missing a valid 'operation' name")
    op = app.operation(name)
    if op is None:
        valid = ", ".join(o.name for o in app.operations)
        raise SelectionError(f"app {app.id!r} has no operation {name!r}; valid: {valid}")

    raw_args = payload.get("arguments", {})
    if not isinstance(raw_args, dict):
        raise SelectionError("operation selection 'arguments' must be an object")
    # Ground the arguments: keep only the operation's declared request fields (when known).
    allowed = set(op.request_fields)
    args: dict[str, Any] = (
        {k: v for k, v in raw_args.items() if k in allowed} if allowed else dict(raw_args)
    )
    return op, args


def select_operation(
    client: LLMClient,
    app: AppEntry,
    subtask: Subtask,
    *,
    model: str,
    upstream: Sequence[SubtaskResult] = (),
    max_retries: int = 2,
) -> tuple[AppOperation, dict[str, Any]]:
    """Choose an operation + arguments for ``subtask`` on ``app``. Raises SelectionError.

    ``upstream`` carries the results of the subtasks this one depends on, so their concrete
    values (an id returned by an earlier step) are available to fill this step's arguments.

    Like the planner, an invalid response is fed back to the model with the concrete error for up
    to ``max_retries`` corrections — models routinely emit multi-line code with raw newlines inside
    a JSON string value, which is invalid JSON; re-prompting with an escape hint recovers it. The
    original SelectionError is preserved if every attempt fails.
    """
    system = load_system_prompt()
    messages: list[dict[str, str]] = [
        {"role": "user", "content": build_select_message(app, subtask, upstream)}
    ]
    last_error: SelectionError | None = None
    for _attempt in range(max_retries + 1):
        raw = client.complete(
            LLMRequest(model=model, system=system, messages=tuple(messages), max_tokens=_MAX_TOKENS)
        )
        try:
            return _parse_selection(raw, app)
        except SelectionError as exc:
            last_error = exc
            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"That response was invalid: {exc}. Return ONE raw JSON object only — no "
                        "prose, no code fences. If a value contains code or newlines, escape them "
                        'so the JSON parses (use \\n for newlines, \\" for quotes).'
                    ),
                }
            )
    assert last_error is not None  # loop runs >=1 time; a success would have returned
    raise last_error
