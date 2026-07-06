"""Render a Plan for humans (stepped DAG) or machines (JSON).

The human view groups subtasks into dependency "waves": a wave is every subtask
whose dependencies are already satisfied, so a wave with more than one subtask runs
in parallel. This is what makes sequential vs parallel execution visible at a glance.
Nothing here runs an app; the output always ends with the dry-run banner.
"""

from __future__ import annotations

import json

from orchestrator.models import Plan, Subtask

DRY_RUN_BANNER = "DRY RUN — no apps were invoked."


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
