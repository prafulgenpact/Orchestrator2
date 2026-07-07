"""Render a Plan for humans (stepped DAG) or machines (JSON).

The human view groups subtasks into dependency "waves": a wave is every subtask
whose dependencies are already satisfied, so a wave with more than one subtask runs
in parallel. This is what makes sequential vs parallel execution visible at a glance.
Nothing here runs an app; the output always ends with the dry-run banner.
"""

from __future__ import annotations

import json
from typing import Any

from orchestrator.models import Plan, PlanResult, Subtask

DRY_RUN_BANNER = "DRY RUN — no apps were invoked."
_STATUS_BADGE = {"ok": "OK", "error": "ERROR", "skipped": "SKIP"}


def compute_waves(subtasks: tuple[Subtask, ...]) -> list[list[Subtask]]:
    """Group subtasks into execution waves in dependency order.

    Raises ValueError on a cycle (the renderer should only ever receive validated
    plans, but this guards against an infinite loop on a hand-built bad Plan).
    """
    placed: set[str] = set()
    remaining = list(subtasks)
    waves: list[list[Subtask]] = []
    while remaining:
        current = [s for s in remaining if all(dep in placed for dep in s.depends_on)]
        if not current:
            raise ValueError("plan contains a dependency cycle")
        placed.update(s.id for s in current)
        waves.append(current)
        remaining = [s for s in remaining if s.id not in placed]
    return waves


def render_json(plan: Plan) -> str:
    """The plan as a single pretty-printed JSON document."""
    return json.dumps(plan.to_dict(), indent=2)


def render_human(plan: Plan) -> str:
    """The plan as a readable, stepped report ending in the dry-run banner."""
    lines: list[str] = [
        f"Task:   {plan.task}",
        f"Intent: {plan.intent}",
        "",
    ]
    waves = compute_waves(plan.subtasks)
    lines.append(f"Execution plan: {len(plan.subtasks)} subtask(s) in {len(waves)} step(s)")
    for step_number, wave in enumerate(waves, start=1):
        header = f"Step {step_number}" + (" (parallel)" if len(wave) > 1 else "") + ":"
        lines.append(header)
        for sub in wave:
            deps = f"   (depends on: {', '.join(sub.depends_on)})" if sub.depends_on else ""
            marker = "  [FALLBACK]" if sub.app.fallback else ""
            lines.append(f"  [{sub.id}] {sub.title}{deps}")
            lines.append(
                f"       -> {sub.app.app_name}  (confidence {sub.app.confidence:.2f}){marker}"
            )
            lines.append(f"          rationale: {sub.app.rationale}")
    lines.append("")
    lines.append(f"{DRY_RUN_BANNER}  model={plan.model}  prompt=v{plan.prompt_version}")
    return "\n".join(lines)


def _preview(data: Any, limit: int = 400) -> str:
    """A one-line, length-bounded preview of an app's real output."""
    text = data if isinstance(data, str) else json.dumps(data, default=str)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "…"


def render_execution(result: PlanResult) -> str:
    """A readable report of an executed plan: which app ran, its real output, its source."""
    ok = sum(1 for r in result.results if r.status == "ok")
    lines: list[str] = [
        f"Task:   {result.task}",
        f"Intent: {result.intent}",
        "",
        f"Executed {len(result.results)} subtask(s): {ok} ok",
    ]
    for r in result.results:
        badge = _STATUS_BADGE.get(r.status, r.status)
        lines.append(
            f"  [{r.subtask_id}] {r.app_name} :: {r.operation or '-'}  "
            f"-> {badge}  ({r.duration_s:.2f}s)"
        )
        if r.status == "ok":
            lines.append(f"       source: {r.source}")
            lines.append(f"       result: {_preview(r.output)}")
        elif r.status == "error":
            lines.append(f"       error: {r.error}")
        else:
            lines.append(f"       {r.error}")
    return "\n".join(lines)
