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

from orchestrator.contract import field_types, load_snapshot, snapshot_path
from orchestrator.llm.base import LLMClient, LLMRequest
from orchestrator.models import Subtask, SubtaskResult
from orchestrator.registry import AppEntry, AppOperation

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "operation_select_system.md"
# Big headroom for arguments that embed a whole multi-section code block: the old 2000 truncated
# the JSON mid-`code` string (Unterminated string) and every retry truncated identically -> web
# fallback. Combined with forced tool-use below, a realistic code arg now returns intact.
_MAX_TOKENS = 8000
_UPSTREAM_LIMIT = 2000  # chars per upstream result — enough to keep ids, bounded for tokens
_SELECT_TOOL_NAME = "select_operation"


def _selection_tool() -> dict[str, Any]:
    """The single forced tool: the model MUST return ``{operation, arguments}`` as *structured*
    input, so the response is always valid JSON — no code fences, no raw-newline breakage — even
    when an argument carries a large multi-line code block. This is the structural fix for the
    selection-JSON-truncation/parse failures; the free-text parse+retry path below stays as
    defense-in-depth for non-tool-use clients."""
    return {
        "name": _SELECT_TOOL_NAME,
        "description": "Return the chosen operation and its arguments for this subtask.",
        "input_schema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "description": "the exact operation name, chosen from the provided list",
                },
                "arguments": {
                    "type": "object",
                    "description": "field -> value, using only that operation's request_fields",
                },
            },
            "required": ["operation", "arguments"],
        },
    }


class SelectionError(ValueError):
    """The model did not pick a valid operation for the app."""


# Free-text "primary input" fields. When the model leaves one of these blank — often because an
# upstream dependency distracts it into thinking the value must come from upstream — we fill it
# deterministically from the SUBTASK's own text. The subtask description is the grounded source of
# what to act on (the user's request for this step), not an invented value. Id/path fields (e.g.
# blog_id, arxiv_id) are deliberately NOT here: those cannot be derived and must genuinely skip.
_PRIMARY_TEXT_FIELDS = frozenset({"topic", "query", "question", "text", "subject"})


def _backfill_primary_fields(op: AppOperation, args: dict[str, Any], subtask: Subtask) -> None:
    """Fill a required free-text primary field the model omitted, from the subtask itself.

    A stochastic prompt can't guarantee the model fills ``topic``/``query``/…; this makes it a
    guarantee, so a chosen app runs on the user's request instead of 422-ing / skipping to web.
    """
    subject = (subtask.description or subtask.title).strip()
    if not subject:
        return
    for field in op.required_fields:
        if field in _PRIMARY_TEXT_FIELDS and (field not in args or args[field] in (None, "")):
            args[field] = subject


def load_system_prompt() -> str:
    return _PROMPT_PATH.read_text()


def _app_field_types(app: AppEntry) -> dict[str, dict[str, str]]:
    """``{op.name: {field: json-type}}`` from the app's committed OpenAPI snapshot.

    The registry keeps only field NAMES; the snapshot is where each field's real type lives.
    Missing/unreadable snapshot (e.g. a brand-new app) → empty maps, view unchanged — types are
    an additive hint, never a hard dependency.
    """
    try:
        snapshot = load_snapshot(snapshot_path(app.id))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return {op.name: field_types(op, snapshot) for op in app.operations}


def _operations_view(app: AppEntry) -> list[dict[str, Any]]:
    # request_fields carries "name: type" pairs when the type is known — the model fills a typed
    # field correctly ("word_count_target: integer" → 800, not "short"), which is what keeps a
    # perfectly legit task from 422-ing the app and falling back to the web.
    types_by_op = _app_field_types(app)

    def _fields(op: AppOperation) -> list[str]:
        op_types = types_by_op.get(op.name, {})
        return [f"{f}: {op_types[f]}" if f in op_types else f for f in op.request_fields]

    return [
        {
            "name": op.name,
            "description": op.description,
            "method": op.method,
            "request_fields": _fields(op),
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
    # Fill any request field the model omitted from the operation's declared defaults, so an app
    # that needs standing context (e.g. a course module) is still usable — never overriding a value
    # the model did provide.
    for key, value in op.defaults.items():
        args.setdefault(key, value)
    return op, args


def _coerce(value: Any, json_type: str) -> tuple[Any, bool]:
    """(coerced_value, ok). Safe conversions only — anything lossy or ambiguous is not ok."""
    if json_type == "integer":
        if isinstance(value, bool):
            return value, False
        if isinstance(value, int):
            return value, True
        if isinstance(value, float) and value.is_integer():
            return int(value), True
        if isinstance(value, str):
            try:
                return int(value.strip()), True
            except ValueError:
                return value, False
        return value, False
    if json_type == "number":
        if isinstance(value, bool):
            return value, False
        if isinstance(value, int | float):
            return value, True
        if isinstance(value, str):
            try:
                return float(value.strip()), True
            except ValueError:
                return value, False
        return value, False
    if json_type == "boolean":
        if isinstance(value, bool):
            return value, True
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in ("true", "yes", "1"):
                return True, True
            if lowered in ("false", "no", "0"):
                return False, True
        return value, False
    if json_type == "string":
        if isinstance(value, str):
            return value, True
        if isinstance(value, int | float) and not isinstance(value, bool):
            return str(value), True
        return value, False
    if json_type == "array":
        return value, isinstance(value, list)
    if json_type == "object":
        return value, isinstance(value, dict)
    return value, True  # unknown type name — pass through untouched


def _enforce_field_types(args: dict[str, Any], types: dict[str, str]) -> None:
    """Coerce safely-convertible argument values to their schema type; DROP the uncoercible.

    This is the value-level gate the name-level grounding never had: a wrongly-typed value
    (live proof: ``word_count_target: "short"`` for an integer field) would 422 the app and send
    a perfectly legit task to the web. Dropping is honest in both cases — a dropped optional
    field falls back to the app's own default; a dropped required field trips the executor's
    existing "missing required input" skip instead of a garbage call.
    """
    for field in list(args):
        json_type = types.get(field)
        if json_type is None or args[field] is None:
            continue
        coerced, ok = _coerce(args[field], json_type)
        if ok:
            args[field] = coerced
        else:
            del args[field]


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
    types_by_op = _app_field_types(app)
    messages: list[dict[str, str]] = [
        {"role": "user", "content": build_select_message(app, subtask, upstream)}
    ]
    last_error: SelectionError | None = None
    for _attempt in range(max_retries + 1):
        raw = client.complete(
            LLMRequest(
                model=model,
                system=system,
                messages=tuple(messages),
                max_tokens=_MAX_TOKENS,
                tools=(_selection_tool(),),
                tool_choice={"type": "tool", "name": _SELECT_TOOL_NAME},
            )
        )
        try:
            op, args = _parse_selection(raw, app)
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
        else:
            # Value-level gate: coerce/drop wrongly-typed arguments BEFORE they can 422 the app.
            _enforce_field_types(args, types_by_op.get(op.name, {}))
            # Guarantee the primary input is present even if the model left it blank (deterministic,
            # grounded in the subtask) — a chosen app must run on the request, not fall back to web.
            _backfill_primary_fields(op, args, subtask)
            return op, args
    assert last_error is not None  # loop runs >=1 time; a success would have returned
    raise last_error
