"""Execute a validated Plan: call the real app per subtask, collect grounded results.

Thin slice: subtasks run in dependency order (waves); for each, the selector picks the operation
+ arguments and the app-caller invokes it under the block-B safety layer. The web-search fallback
is not executed yet (recorded as skipped). A per-run circuit breaker isolates a repeatedly-failing
app, and one subtask's failure never aborts the rest.
"""

from __future__ import annotations

import httpx

from orchestrator.app_caller import call_operation
from orchestrator.grounding import check_relevance
from orchestrator.llm.base import LLMClient
from orchestrator.models import Plan, PlanResult, Subtask, SubtaskResult
from orchestrator.registry import Registry
from orchestrator.render import compute_waves
from orchestrator.resilience import CircuitBreaker
from orchestrator.selector import SelectionError, select_operation


async def execute_plan(
    plan: Plan,
    registry: Registry,
    *,
    llm_client: LLMClient,
    http_client: httpx.AsyncClient,
    model: str,
    breaker: CircuitBreaker | None = None,
) -> PlanResult:
    """Run every subtask in dependency order and collect a PlanResult.

    Results are indexed by subtask id as they complete so that a subtask can be given the outputs
    of the subtasks it depends on (data flow between steps). compute_waves guarantees every
    dependency has already run by the time a subtask starts.
    """
    cb = breaker or CircuitBreaker()
    results: list[SubtaskResult] = []
    by_id: dict[str, SubtaskResult] = {}
    for wave in compute_waves(plan.subtasks):
        for sub in wave:
            upstream = _upstream_for(sub, by_id)
            result = await _run_subtask(sub, registry, llm_client, http_client, model, cb, upstream)
            results.append(result)
            by_id[sub.id] = result
    return PlanResult(task=plan.task, intent=plan.intent, results=tuple(results))


def _upstream_for(sub: Subtask, by_id: dict[str, SubtaskResult]) -> tuple[SubtaskResult, ...]:
    """The successful results of the subtasks ``sub`` depends on (feeds the selector)."""
    return tuple(by_id[dep] for dep in sub.depends_on if dep in by_id and by_id[dep].status == "ok")


async def _run_subtask(
    sub: Subtask,
    registry: Registry,
    llm_client: LLMClient,
    http_client: httpx.AsyncClient,
    model: str,
    breaker: CircuitBreaker,
    upstream: tuple[SubtaskResult, ...] = (),
) -> SubtaskResult:
    app = registry.get(sub.app.app_id)
    if app is None:  # validated upstream; defensive
        return SubtaskResult(
            sub.id,
            sub.app.app_id,
            sub.app.app_name,
            "error",
            None,
            None,
            None,
            f"unknown app {sub.app.app_id!r}",
            0.0,
        )
    if app.fallback:
        return SubtaskResult(
            sub.id,
            app.id,
            app.name,
            "skipped",
            None,
            None,
            None,
            "web-search fallback not executed yet (deferred)",
            0.0,
        )
    try:
        op, args = select_operation(llm_client, app, sub, model=model, upstream=upstream)
    except SelectionError as exc:
        return SubtaskResult(sub.id, app.id, app.name, "error", None, None, None, str(exc), 0.0)

    # Skip a doomed call: if the op needs inputs the selector could not ground (e.g. a course
    # module id this task never mentioned), don't fire a request that would only 422 — skip
    # cleanly. Accuracy over a wrong answer; the anti-hang guarantee holds trivially (no call).
    missing = [f for f in op.required_fields if f not in args or args[f] in (None, "")]
    if missing:
        reason = (
            f"missing required input: {', '.join(missing)} — this app needs context "
            "the task did not provide"
        )
        return SubtaskResult(sub.id, app.id, app.name, "skipped", op.name, None, None, reason, 0.0)

    result = await call_operation(app, op, args, client=http_client, breaker=breaker)
    source = result.url or None
    if not result.ok:
        return SubtaskResult(
            sub.id,
            app.id,
            app.name,
            "error",
            op.name,
            None,
            source,
            result.error,
            result.duration_s,
        )

    # Grounding guard: the app returned data, but is it actually relevant to the task?
    relevant, reason = check_relevance(llm_client, sub, result.data, model=model)
    if not relevant:
        return SubtaskResult(
            sub.id,
            app.id,
            app.name,
            "no_match",
            op.name,
            None,
            source,
            reason or "results did not match the task",
            result.duration_s,
        )
    return SubtaskResult(
        sub.id, app.id, app.name, "ok", op.name, result.data, source, None, result.duration_s
    )
