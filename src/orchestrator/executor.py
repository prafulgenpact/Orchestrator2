"""Execute a validated Plan: call the real app per subtask, collect grounded results.

Thin slice: subtasks run in dependency order (waves); for each, the selector picks the operation
+ arguments and the app-caller invokes it under the block-B safety layer. Subtasks that route to
the web-search fallback are answered from the web (Tavily) with citations, grounded and bounded by
the same hard deadline. A per-run circuit breaker isolates a repeatedly-failing app, and one
subtask's failure never aborts the rest.
"""

from __future__ import annotations

import time

import httpx

from orchestrator.app_caller import call_operation
from orchestrator.grounding import check_relevance
from orchestrator.llm.base import LLMClient
from orchestrator.models import Plan, PlanResult, Subtask, SubtaskResult
from orchestrator.registry import AppEntry, Registry
from orchestrator.render import compute_waves
from orchestrator.resilience import CircuitBreaker, run_with_deadline
from orchestrator.selector import SelectionError, select_operation
from orchestrator.web_search import DEFAULT_TIMEOUT_S, resolve_search_key, search_web


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
        return await _run_web_fallback(app, sub, http_client)
    result = await _run_app_op(app, sub, llm_client, http_client, model, breaker, upstream)
    if result.status == "ok":
        return result
    # Safety net: the chosen app could not ground this subtask (skip/error/no_match). Rather than
    # give up, answer it from the web — so "give it any task" holds even when the routed app can't
    # deliver. Keep the original failure if the web can't help either (never mask it with worse).
    fallback_app = next(entry for entry in registry.apps if entry.fallback)
    web = await _run_web_fallback(fallback_app, sub, http_client)
    return web if web.status == "ok" else result


async def _run_app_op(
    app: AppEntry,
    sub: Subtask,
    llm_client: LLMClient,
    http_client: httpx.AsyncClient,
    model: str,
    breaker: CircuitBreaker,
    upstream: tuple[SubtaskResult, ...],
) -> SubtaskResult:
    """Run one non-fallback app operation: select -> required-field skip -> call -> relevance."""
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


async def _run_web_fallback(
    app: AppEntry, sub: Subtask, http_client: httpx.AsyncClient
) -> SubtaskResult:
    """Answer a no-app subtask from the web (Tavily), grounded with citations.

    Degrades cleanly: no key -> "skipped"; a failed search -> "error". Bounded by the same hard
    deadline as app calls, so the fallback can never hang the run (AC-2).
    """
    key = resolve_search_key()
    if not key:
        return SubtaskResult(
            sub.id,
            app.id,
            app.name,
            "skipped",
            "web_search",
            None,
            None,
            "web search unavailable: set TAVILY_API_KEY to enable the web fallback",
            0.0,
        )
    start = time.monotonic()
    query = f"{sub.title}: {sub.description}"
    try:
        web = await run_with_deadline(
            search_web(query, client=http_client, api_key=key), DEFAULT_TIMEOUT_S
        )
    except Exception as exc:  # any failure becomes a recorded error, never raised
        detail = str(exc) or type(exc).__name__
        return SubtaskResult(
            sub.id,
            app.id,
            app.name,
            "error",
            "web_search",
            None,
            None,
            f"web search failed: {detail}",
            time.monotonic() - start,
        )
    source = web.citations[0] if web.citations else None
    return SubtaskResult(
        sub.id,
        app.id,
        app.name,
        "ok",
        "web_search",
        web.to_dict(),
        source,
        None,
        time.monotonic() - start,
    )
