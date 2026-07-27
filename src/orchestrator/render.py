"""Render a Plan for humans (stepped DAG) or machines (JSON).

The human view groups subtasks into dependency "waves": a wave is every subtask
whose dependencies are already satisfied, so a wave with more than one subtask runs
in parallel. This is what makes sequential vs parallel execution visible at a glance.
Nothing here runs an app; the output always ends with the dry-run banner.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from orchestrator.models import Plan, PlanResult, Subtask
from orchestrator.synthesis import Synthesis

DRY_RUN_BANNER = "DRY RUN — no apps were invoked."


def render_chart_paths(paths: list[Path]) -> str:
    """A block listing saved chart files so the user can open them ("" when there are none)."""
    if not paths:
        return ""
    lines = ["Charts (open in a browser):"]
    lines.extend(f"  📊 {p}" for p in paths)
    return "\n".join(lines)


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


def _preview(data: Any, limit: int = 500) -> str:
    """A one-line, length-bounded preview of an app's real output."""
    text = data if isinstance(data, str) else json.dumps(data, default=str)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "…"


def _full(data: Any) -> str:
    """The app's full output, untruncated (verbose mode)."""
    return data if isinstance(data, str) else json.dumps(data, indent=2, default=str)


def _indent(text: str, prefix: str = "       ") -> str:
    return "\n".join(prefix + line for line in text.splitlines())


def _one_line(text: str, limit: int = 120) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "…"


def _list_lines(items: list[Any], top: int = 5) -> list[str]:
    """Numbered top-N titles for a list result (clean mode)."""
    out: list[str] = []
    for i, item in enumerate(items[:top], start=1):
        if isinstance(item, dict):
            label = item.get("title") or item.get("name") or item.get("id") or json.dumps(item)
        else:
            label = item
        out.append(f"       {i}. {_one_line(str(label))}")
    if len(items) > top:
        out.append(f"       … ({len(items) - top} more)")
    return out


def render_execution(
    plan: Plan,
    result: PlanResult,
    synthesis: Synthesis | None = None,
    *,
    verbose: bool = False,
    include_answer: bool = True,
) -> str:
    """Clean view of an executed plan: the Answer on top, then input, decomposition, output.

    When ``synthesis`` is given, its grounded answer (and sources) leads — it is what the user
    reads first. Below it: the task + intent (input), how it was decomposed with the chosen app /
    confidence / rationale (decomposition), and each subtask's grounded result + source (output).
    Operational detail — operation name, status, timing, and the full payload — appears only with
    ``verbose``.
    """
    waves = compute_waves(plan.subtasks)
    lines: list[str] = [
        f"Task: {plan.task}",
        "",
        f"Intent: {plan.intent}",
        "",
    ]
    if synthesis is not None and include_answer:
        # include_answer=False when the caller already showed the answer (e.g. the CLI streamed it
        # live), so it is not printed twice.
        lines.append("Answer:")
        lines.extend(f"  {line}" for line in (synthesis.answer.splitlines() or [""]))
        if synthesis.sources:
            lines.append("  Sources:")
            lines.extend(f"    - {src}" for src in synthesis.sources)
        lines.append("")
    # Announce any note up front — the user must never have to dig for it (traceability).
    notes = [r.note for r in result.results if r.note]
    if notes:
        lines.append("⚠ Heads up:")
        lines.extend(f"  - {note}" for note in notes)
        lines.append("")
    # Surface chosen-app failures right under the answer, so a partial failure is never hidden by
    # a confident-looking synthesized answer (the answer is built only from the ok results).
    failed = [r for r in result.results if r.status != "ok"]
    if failed:
        lines.append("⚠ Some parts of the task could not be completed:")
        lines.extend(f"  - {r.app_name}: {r.error or r.status}" for r in failed)
        lines.append("")
    # Label web-sourced content explicitly: the answer body reads the same whether it came from a
    # tuned app or the open web, so a web-sourced part must be called out (no app covered it).
    web = [r for r in result.results if r.status == "ok" and r.operation == "web_search"]
    if web:
        lines.append("Answered from a web search (no specialized app covered this):")
        lines.extend(f"  - {r.subtask_id}" for r in web)
        lines.append("")
    lines.append(f"Plan — {len(plan.subtasks)} subtask(s) in {len(waves)} step(s):")
    for step, wave in enumerate(waves, start=1):
        lines.append(f"  Step {step}" + (" (parallel)" if len(wave) > 1 else "") + ":")
        for sub in wave:
            deps = f"  (needs {', '.join(sub.depends_on)})" if sub.depends_on else ""
            fallback = "  [fallback]" if sub.app.fallback else ""
            lines.append(f"    [{sub.id}] {sub.title}{deps}")
            lines.append(
                f"         -> {sub.app.app_name}  (confidence {sub.app.confidence:.2f}){fallback}"
            )
            lines.append(f"         why: {sub.app.rationale}")

    lines.append("")
    lines.append("Results:")
    by_id = {r.subtask_id: r for r in result.results}
    for sub in plan.subtasks:
        r = by_id.get(sub.id)
        header = f"  [{sub.id}] {r.app_name if r else sub.app.app_name}"
        if r is not None and r.status == "ok" and isinstance(r.output, list) and not verbose:
            header += f"  — {len(r.output)} result(s)"
        lines.append(header)
        if r is None:
            lines.append("       (no result)")
            continue
        if r.status == "ok":
            if verbose:
                lines.append(_indent(_full(r.output)))
            elif isinstance(r.output, list):
                lines.extend(_list_lines(r.output))
            else:
                lines.append(_indent(_preview(r.output)))
            if r.source:
                lines.append(f"       source: {r.source}")
        elif r.status == "no_match":
            lines.append(f"       no relevant results found — {r.error}")
        elif r.status == "skipped":
            lines.append(f"       (not executed — {r.error})")
        else:
            lines.append(f"       could not complete: {r.error}")
        if r.note:
            lines.append(f"       ⚠ {r.note}")
        if verbose:
            lines.append(f"       [op={r.operation}  status={r.status}  {r.duration_s:.2f}s]")
            if r.args:
                # Show exactly what the app was asked — so a guessed/defaulted input is auditable.
                lines.append(f"       args: {json.dumps(r.args, default=str, ensure_ascii=False)}")
    return "\n".join(lines)
