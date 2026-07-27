"""Execute a validated Plan: call the real app per subtask, collect grounded results.

Thin slice: subtasks run in dependency order (waves); for each, the selector picks the operation
+ arguments and the app-caller invokes it under the block-B safety layer. Subtasks that route to
the web-search fallback are answered from the web (Tavily) with citations, grounded and bounded by
the same hard deadline. A per-run circuit breaker isolates a repeatedly-failing app, and one
subtask's failure never aborts the rest.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any

import httpx

from orchestrator.app_caller import AppEndpoints, CallResult, call_operation
from orchestrator.grounding import check_relevance, is_blank
from orchestrator.llm.base import LLMClient, LLMError
from orchestrator.models import Artifact, Plan, PlanResult, Subtask, SubtaskResult
from orchestrator.registry import AppEntry, AppOperation, Registry
from orchestrator.render import compute_waves
from orchestrator.resilience import CircuitBreaker, run_with_deadline
from orchestrator.selector import SelectionError, select_operation
from orchestrator.web_search import DEFAULT_TIMEOUT_S, resolve_search_key, search_web

# Slow is NOT hung. We do not cap how long a genuinely-working start-then-poll job may take: we keep
# polling while the app keeps responding (progress), and stop early only when it goes SILENT —
# _ASYNC_MAX_SILENT_POLLS consecutive failed polls = no progress (a single blip is tolerated, not a
# hang). A generous, env-tunable absolute ceiling remains ONLY as the AC-2 anti-hang backstop, so a
# server that stays up but wedged forever still terminates. Raise ORCHESTRATOR_ASYNC_MAX_WAIT_S (or
# set it very high) for legitimately long jobs — it is a safety net, not the normal limit.
_ASYNC_MAX_WAIT_S = float(os.environ.get("ORCHESTRATOR_ASYNC_MAX_WAIT_S", "3600"))
_ASYNC_POLL_INTERVAL_S = 4.0
_ASYNC_MAX_SILENT_POLLS = 5  # consecutive failed polls tolerated before declaring "no progress"
_ASYNC_HEARTBEAT_EVERY = (
    3  # emit a "still working" heartbeat every Nth successful non-terminal poll
)

# Progress is reported through an injectable callback (default: silent), so the CLI can show live
# activity while the executor stays free of any print/stderr coupling and tests stay deterministic.
ProgressFn = Callable[[str], None]


def _null_progress(_message: str) -> None:
    return None


# Independent subtasks in a wave run concurrently; this bounds how many at once so a wide wave
# never floods the Foundry API / sibling apps. Env-tunable; blank/non-numeric/<1 uses the default.
_DEFAULT_MAX_CONCURRENCY = 5


def _resolve_max_concurrency() -> int:
    """Max subtasks to run at once (env ``ORCHESTRATOR_MAX_CONCURRENCY``, default 5)."""
    raw = os.environ.get("ORCHESTRATOR_MAX_CONCURRENCY")
    if raw is None:
        return _DEFAULT_MAX_CONCURRENCY
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_MAX_CONCURRENCY
    return value if value >= 1 else _DEFAULT_MAX_CONCURRENCY


async def execute_plan(
    plan: Plan,
    registry: Registry,
    *,
    llm_client: LLMClient,
    http_client: httpx.AsyncClient,
    model: str,
    breaker: CircuitBreaker | None = None,
    progress: ProgressFn = _null_progress,
) -> PlanResult:
    """Run every subtask in dependency order and collect a PlanResult.

    Results are indexed by subtask id as they complete so that a subtask can be given the outputs
    of the subtasks it depends on (data flow between steps). compute_waves guarantees every
    dependency has already run by the time a subtask starts.
    """
    cb = breaker or CircuitBreaker()
    results: list[SubtaskResult] = []
    by_id: dict[str, SubtaskResult] = {}
    sem = asyncio.Semaphore(_resolve_max_concurrency())
    # One endpoint cache for the whole run: each app is launcher-resolved + health-confirmed once,
    # so repeated calls (especially the async poll loop) skip the duplicate resolve/health pings.
    endpoints = AppEndpoints()

    async def _guarded(sub: Subtask) -> SubtaskResult:
        # The semaphore bounds concurrency; upstream is read here (all of this subtask's
        # dependencies live in an earlier, already-completed wave, so by_id is fully populated).
        async with sem:
            upstream = _upstream_for(sub, by_id)
            progress(f"-> {sub.title}")
            result = await _run_subtask(
                sub, registry, llm_client, http_client, model, cb, upstream, endpoints, progress
            )
            progress(f"[{result.status}] {sub.title} ({result.duration_s:.1f}s)")
            return result

    # Waves stay sequential (they encode dependencies), but the independent subtasks WITHIN a wave
    # run concurrently — the parallelism the renderer already advertises as "(parallel)". Results
    # are indexed after the wave completes so a later wave can read its dependencies' outputs.
    for wave in compute_waves(plan.subtasks):
        wave_results = await asyncio.gather(*(_guarded(sub) for sub in wave))
        for sub, result in zip(wave, wave_results, strict=True):
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
    endpoints: AppEndpoints | None = None,
    progress: ProgressFn = _null_progress,
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
        # Planner-routed web fallback: the planner decided NO app fits this subtask, so it is
        # answered from the web by design (the objective's one sanctioned web path).
        return await _run_web_fallback(app, sub, http_client)
    # A CHOSEN app owns its subtask. If it fails/skips/returns no_match we report that honestly —
    # we do NOT silently substitute a web answer wearing the app's badge. Web is only for subtasks
    # the planner routed to it (above). An honest failure beats a masked one (accuracy first).
    return await _run_app_op(
        app, sub, llm_client, http_client, model, breaker, upstream, endpoints, progress
    )


async def _run_app_op(
    app: AppEntry,
    sub: Subtask,
    llm_client: LLMClient,
    http_client: httpx.AsyncClient,
    model: str,
    breaker: CircuitBreaker,
    upstream: tuple[SubtaskResult, ...],
    endpoints: AppEndpoints | None = None,
    progress: ProgressFn = _null_progress,
) -> SubtaskResult:
    """Run one non-fallback app operation: select -> required-field skip -> call -> relevance."""
    try:
        # Offload the blocking (synchronous) LLM call off the event loop, so subtasks running
        # concurrently in the same wave genuinely overlap instead of serializing on this call.
        op, args = await asyncio.to_thread(
            select_operation, llm_client, app, sub, model=model, upstream=upstream
        )
    except (SelectionError, LLMError) as exc:
        # SelectionError = model couldn't ground a valid operation; LLMError = the LLM layer
        # failed (e.g. a truncated selection response). Either way, return a clean error so the
        # run never crashes and the web safety net (in _run_subtask) can answer with disclosure.
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
        return SubtaskResult(
            sub.id, app.id, app.name, "skipped", op.name, None, None, reason, 0.0, args=args
        )

    if op.poll is not None:
        result = await _run_async(
            app,
            op,
            args,
            http_client=http_client,
            breaker=breaker,
            endpoints=endpoints,
            progress=progress,
        )
    else:
        result = await call_operation(
            app, op, args, client=http_client, breaker=breaker, endpoints=endpoints
        )
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
            args=args,
        )

    # Grounding guard: the app returned data, but is it actually relevant to the task?
    # Offloaded off the event loop for the same reason as the selection call above.
    relevant, reason = await asyncio.to_thread(
        check_relevance, llm_client, sub, result.data, model=model
    )
    if not relevant and is_blank(result.data):
        # The one hard FAIL: the app returned nothing usable. An honest empty failure — there is
        # no answer to keep, and we never fabricate one.
        return SubtaskResult(
            sub.id,
            app.id,
            app.name,
            "no_match",
            op.name,
            None,
            source,
            reason or "the app returned no content",
            result.duration_s,
            args=args,
        )
    # The judge is ADVISORY, not a deleter. If it flagged a non-empty result as a possible
    # mismatch, we KEEP the app's answer (the apps are tuned to the user — AC-4) and attach a
    # visible caution instead of discarding it. A wrong discard is itself an inaccuracy. A clean
    # PASS carries no note.
    note = (
        f"the relevance check flagged this may not fully match the task ({reason})"
        if not relevant
        else None
    )
    return SubtaskResult(
        sub.id,
        app.id,
        app.name,
        "ok",
        op.name,
        result.data,
        source,
        None,
        result.duration_s,
        artifacts=_result_artifacts(op, sub, result.data),
        note=note,
        args=args,
    )


def _result_artifacts(op: AppOperation, sub: Subtask, data: Any) -> tuple[Artifact, ...]:
    """Promote non-text outputs to first-class artifacts so they are rendered to openable files
    (and carried for a future UI), never truncated by the text caps:

    * a chart spec — when the op declares ``produces: "chart"`` and returned an error-free dict;
    * rendered images — any base64 PNG in ``data["images"]`` (e.g. the live kernel's matplotlib
      output), one image artifact each.
    """
    if not isinstance(data, dict):
        return ()
    artifacts: list[Artifact] = []
    if op.produces == "chart" and not data.get("error"):
        artifacts.append(Artifact(kind="chart", title=sub.title, spec=data, subtask_id=sub.id))
    images = data.get("images")
    if isinstance(images, list):
        pngs = [img for img in images if isinstance(img, str) and img]
        for idx, img in enumerate(pngs):
            title = sub.title if len(pngs) == 1 else f"{sub.title} ({idx + 1})"
            artifacts.append(
                Artifact(kind="image", title=title, spec={"png_base64": img}, subtask_id=sub.id)
            )
    return tuple(artifacts)


def _dig(obj: Any, dotted_path: str) -> Any:
    """Walk a dotted path through nested dicts/lists (int segments index lists). None if missing."""
    for seg in dotted_path.split("."):
        if isinstance(obj, list):
            try:
                obj = obj[int(seg)]
            except (ValueError, IndexError):
                return None
        elif isinstance(obj, dict):
            obj = obj.get(seg)
        else:
            return None
    return obj


async def _run_async(
    app: AppEntry,
    op: AppOperation,
    args: dict[str, Any],
    *,
    http_client: httpx.AsyncClient,
    breaker: CircuitBreaker,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    endpoints: AppEndpoints | None = None,
    progress: ProgressFn = _null_progress,
) -> CallResult:
    """Drive a start-then-poll async op to completion; return the final content as a CallResult.

    Start the job, read its run id, then poll until a terminal status. Slow is not hung: a job runs
    as long as it needs while the app keeps answering polls (progress). We stop early only when it
    goes silent (``_ASYNC_MAX_SILENT_POLLS`` failed polls in a row), on a failed status, or at the
    generous ``_ASYNC_MAX_WAIT_S`` ceiling (the AC-2 anti-hang backstop). Each is a clean error (the
    caller then applies grounding / the web safety net).
    """
    spec = op.poll
    assert spec is not None  # only called when op.poll is set
    start = await call_operation(
        app, op, args, client=http_client, breaker=breaker, endpoints=endpoints
    )
    if not start.ok:
        return start
    run_id = _dig(start.data, spec.run_id_field)
    if run_id is None:
        return replace(
            start, ok=False, data=None, error=f"async start returned no '{spec.run_id_field}'"
        )
    poll_op = app.operation(spec.poll_op)
    if poll_op is None:
        return replace(start, ok=False, data=None, error=f"poll op {spec.poll_op!r} not found")
    silent = 0
    responded = 0  # successful non-terminal polls, for pacing the heartbeat
    for _ in range(max(1, int(_ASYNC_MAX_WAIT_S / _ASYNC_POLL_INTERVAL_S))):
        poll = await call_operation(
            app,
            poll_op,
            {spec.run_id_arg: run_id},
            client=http_client,
            breaker=breaker,
            endpoints=endpoints,
        )
        if not poll.ok:
            # A failed poll is a silence signal, not proof the job died — tolerate a few in a row
            # (a transient blip is not a hang). Give up only once the app has gone silent for
            # _ASYNC_MAX_SILENT_POLLS consecutive polls = no progress.
            silent += 1
            if silent >= _ASYNC_MAX_SILENT_POLLS:
                return replace(
                    poll,
                    ok=False,
                    data=None,
                    error=(
                        f"async run stopped responding after {silent} consecutive failed polls "
                        f"(no progress): {poll.error}"
                    ),
                )
            await sleep(_ASYNC_POLL_INTERVAL_S)
            continue
        silent = 0  # the app answered — it is alive and making progress; keep waiting as needed
        status = _dig(poll.data, spec.status_path)
        if status in spec.done_values:
            return replace(poll, data=_dig(poll.data, spec.result_path))
        if status in spec.failed_values:
            return replace(poll, ok=False, data=None, error=f"async run ended: {status}")
        responded += 1
        # A slow job that keeps answering is working, not hung — reassure the user periodically.
        if responded % _ASYNC_HEARTBEAT_EVERY == 0:
            progress(f"... still working: {app.name} ({responded} polls, responding)")
        await sleep(_ASYNC_POLL_INTERVAL_S)
    return replace(
        start,
        ok=False,
        data=None,
        error=f"async run did not finish within {int(_ASYNC_MAX_WAIT_S)}s (hard ceiling)",
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
