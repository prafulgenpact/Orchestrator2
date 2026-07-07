"""Pick which app operation to call for a subtask, and its arguments (one LLM call).

Grounded: the model is shown ONLY the app's real operations (name + request_fields) and must
return one of them; the returned arguments are filtered to that operation's known request fields.
Endpoints are never invented — they come from the registry.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from orchestrator.llm.base import LLMClient, LLMRequest
from orchestrator.models import Subtask
from orchestrator.registry import AppEntry, AppOperation

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "operation_select_system.md"
_MAX_TOKENS = 1000


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


def build_select_message(app: AppEntry, subtask: Subtask) -> str:
    view = json.dumps(
        {"app": app.name, "operations": _operations_view(app)},
        sort_keys=True,
        separators=(",", ":"),
    )
    return (
        f"APP OPERATIONS (JSON):\n{view}\n\n"
        f"SUBTASK:\n{subtask.title}: {subtask.description}\n\n"
        'Return one raw JSON object: {"operation": "<name>", "arguments": {<field>: <value>}}.'
    )


def _strip_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def select_operation(
    client: LLMClient, app: AppEntry, subtask: Subtask, *, model: str
) -> tuple[AppOperation, dict[str, Any]]:
    """Choose an operation + arguments for ``subtask`` on ``app``. Raises SelectionError."""
    request = LLMRequest(
        model=model,
        system=load_system_prompt(),
        messages=({"role": "user", "content": build_select_message(app, subtask)},),
        max_tokens=_MAX_TOKENS,
    )
    raw = client.complete(request)
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
