"""Execute a validated Plan: call the real app per subtask, collect grounded results.

Thin slice: subtasks run in dependency order (waves); for each, the selector picks the operation
+ arguments and the app-caller invokes it under the block-B safety layer. The web-search fallback
is not executed yet (recorded as skipped). A per-run circuit breaker isolates a repeatedly-failing
app, and one subtask's failure never aborts the rest.
"""

from __future__ import annotations

import httpx

from orchestrator.app_caller import call_operation
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
    """Run every subtask in dependency order and collect a PlanResult."""
    cb = breaker or CircuitBreaker()
    results: list[SubtaskResult] = []
    for wave in compute_waves(plan.subtasks):
        for sub in wave:
            results.append(await _run_subtask(sub, registry, llm_client, http_client, model, cb))
    return PlanResult(task=plan.task, intent=plan.intent, results=tuple(results))


async def _run_subtask(
    sub: Subtask,
    registry: Registry,
    llm_client: LLMClient,
    http_client: httpx.AsyncClient,
    model: str,
    breaker: CircuitBreaker,
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
        op, args = select_operation(llm_client, app, sub, model=model)
    except SelectionError as exc:
        return SubtaskResult(sub.id, app.id, app.name, "error", None, None, None, str(exc), 0.0)

    result = await call_operation(app, op, args, client=http_client, breaker=breaker)
    return SubtaskResult(
        subtask_id=sub.id,
        app_id=app.id,
        app_name=app.name,
        status="ok" if result.ok else "error",
        operation=op.name,
        output=result.data,
        source=result.url or None,
        error=result.error,
        duration_s=result.duration_s,
    )
