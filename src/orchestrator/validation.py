"""Parse and validate the planner model's JSON into a Plan.

The model returns a JSON object: an ``intent`` string and a ``subtasks`` list, where
each subtask names an ``app_id`` from the registry. This module is the trust
boundary. It strips accidental markdown fences, parses JSON, checks the schema,
verifies the subtask graph is a DAG (no dangling or cyclic dependencies — those are
what encode sequential vs parallel execution), and confirms every app_id exists,
denormalizing the app name and fallback flag from the registry rather than trusting
the model. Any problem raises PlanValidationError with a concrete, feed-back-able
message so the planner can ask the model to correct itself.
"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from typing import Any

from orchestrator.models import AppSelection, Plan, Subtask
from orchestrator.registry import Registry


class PlanValidationError(ValueError):
    """The model's response is not a valid plan (bad JSON, schema, graph, or app)."""


def _require_nonempty_str(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PlanValidationError(f"{label} must be a non-empty string")
    return value


def _strip_fences(text: str) -> str:
    """Drop a leading ``` / ```json fence and trailing ``` if the model added them."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _load_json(text: str) -> dict[str, Any]:
    try:
        data = json.loads(_strip_fences(text))
    except json.JSONDecodeError as exc:
        raise PlanValidationError(f"response is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise PlanValidationError("response must be a JSON object")
    return data


def _confidence(value: Any) -> float:
    try:
        conf = float(value)
    except (TypeError, ValueError):
        raise PlanValidationError(f"confidence must be a number, got {value!r}") from None
    if not 0.0 <= conf <= 1.0:
        raise PlanValidationError(f"confidence must be in [0, 1], got {conf}")
    return conf


def _parse_app_selection(raw: Any, registry: Registry, sub_id: str) -> AppSelection:
    if not isinstance(raw, dict):
        raise PlanValidationError(f"subtask {sub_id!r} 'app' must be an object")
    app_id = _require_nonempty_str(raw.get("app_id"), f"subtask {sub_id!r} app_id")
    entry = registry.get(app_id)
    if entry is None:
        raise PlanValidationError(
            f"subtask {sub_id!r} names unknown app_id {app_id!r}; "
            f"valid ids: {', '.join(registry.ids())}"
        )
    return AppSelection(
        app_id=entry.id,
        app_name=entry.name,  # denormalized from the registry, not trusted from the model
        rationale=_require_nonempty_str(raw.get("rationale"), f"subtask {sub_id!r} rationale"),
        confidence=_confidence(raw.get("confidence")),
        fallback=entry.fallback,  # denormalized from the registry
    )


def _parse_subtask(raw: Any, registry: Registry, index: int) -> Subtask:
    if not isinstance(raw, dict):
        raise PlanValidationError(f"subtask #{index} must be an object")
    sub_id = _require_nonempty_str(raw.get("id"), f"subtask #{index} id")
    depends_on = raw.get("depends_on", [])
    if not isinstance(depends_on, list) or not all(isinstance(d, str) for d in depends_on):
        raise PlanValidationError(f"subtask {sub_id!r} depends_on must be a list of ids")
    return Subtask(
        id=sub_id,
        title=_require_nonempty_str(raw.get("title"), f"subtask {sub_id!r} title"),
        description=_require_nonempty_str(
            raw.get("description"), f"subtask {sub_id!r} description"
        ),
        depends_on=tuple(depends_on),
        app=_parse_app_selection(raw.get("app"), registry, sub_id),
    )


def _check_acyclic(subtasks: tuple[Subtask, ...]) -> None:
    """Kahn-style reachability: every subtask must be resolvable in dependency order."""
    pending = {s.id: set(s.depends_on) for s in subtasks}
    resolved: set[str] = set()
    progressed = True
    while progressed:
        progressed = False
        for sub_id, deps in pending.items():
            if sub_id not in resolved and deps <= resolved:
                resolved.add(sub_id)
                progressed = True
    if len(resolved) != len(subtasks):
        cyclic = ", ".join(sorted(set(pending) - resolved))
        raise PlanValidationError(f"subtask dependencies form a cycle among: {cyclic}")


def _norm_title(title: str) -> str:
    """Normalize a subtask title for duplicate detection: lowercase, collapse whitespace, drop
    trailing sentence punctuation. So 'Find papers on X.' and 'find  papers on x' match."""
    return re.sub(r"\s+", " ", title.strip().lower()).rstrip(".!?…").strip()


def _dedupe_subtasks(subtasks: tuple[Subtask, ...]) -> tuple[Subtask, ...]:
    """Collapse subtasks that are exact duplicates — same app AND normalized title — into one.

    The planner occasionally emits two steps that do the same thing (e.g. two "find papers on X"
    routed to the same app), which then run redundantly and show as duplicate cards. Keep the first,
    drop later twins, and rewire any dependency on a dropped twin to the kept one. Deterministic and
    conservative (title-exact only); a no-op when there are no duplicates.
    """
    kept: list[Subtask] = []
    canonical: dict[tuple[str, str], str] = {}  # (app_id, norm title) -> the kept subtask id
    remap: dict[str, str] = {}  # dropped twin id -> kept id
    for s in subtasks:
        key = (s.app.app_id, _norm_title(s.title))
        if key in canonical:
            remap[s.id] = canonical[key]
        else:
            canonical[key] = s.id
            kept.append(s)
    if not remap:
        return subtasks
    rewired: list[Subtask] = []
    for s in kept:
        deps: list[str] = []
        for d in s.depends_on:
            target = remap.get(d, d)
            if target != s.id and target not in deps:
                deps.append(target)
        rewired.append(replace(s, depends_on=tuple(deps)))
    return tuple(rewired)


def parse_plan(
    text: str,
    registry: Registry,
    *,
    task: str,
    model: str,
    prompt_version: str,
) -> Plan:
    """Validate the model's response and combine it with call context into a Plan.

    ``task``/``model``/``prompt_version`` come from the planner (call context), not
    from the model's JSON, so they cannot be spoofed by the response.
    """
    payload = _load_json(text)
    intent = _require_nonempty_str(payload.get("intent"), "intent")

    subtasks_raw = payload.get("subtasks")
    if not isinstance(subtasks_raw, list) or not subtasks_raw:
        raise PlanValidationError("subtasks must be a non-empty list")
    subtasks = tuple(_parse_subtask(raw, registry, i) for i, raw in enumerate(subtasks_raw))
    # Collapse exact-duplicate subtasks (same app + title) so a redundant decomposition doesn't run
    # the same call twice / show duplicate cards. Deterministic; validated (ids, deps, DAG) below.
    subtasks = _dedupe_subtasks(subtasks)

    ids = [s.id for s in subtasks]
    if len(set(ids)) != len(ids):
        raise PlanValidationError("subtask ids must be unique")
    id_set = set(ids)
    for sub in subtasks:
        for dep in sub.depends_on:
            if dep not in id_set:
                raise PlanValidationError(f"subtask {sub.id!r} depends on unknown id {dep!r}")
    _check_acyclic(subtasks)

    return Plan(
        task=task,
        intent=intent,
        subtasks=subtasks,
        model=model,
        prompt_version=prompt_version,
    )
