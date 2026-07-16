# Task: cache-endpoint-per-run

<!-- Fill Goal/Type/Scope/Acceptance BEFORE any code. This file IS the plan for
     this task; drift_check.py enforces the Scope line mechanically. -->

Status: DONE
Type: refactor
Scope: src/orchestrator/app_caller.py, src/orchestrator/executor.py, tests/unit/test_app_caller.py, tests/unit/test_executor.py
Phase: Phase 2 — UX (responses faster) / efficiency; keeps the AC-2 safety intact

## Goal

Stop re-issuing the launcher-resolve (`GET /api/apps`) and health-check (`GET {health}`) before
**every** call to an app. Today `call_operation` does both on each invocation; on the async poll
path `_run_async` calls `call_operation` for the start AND every poll, so a long job pays ~2 extra
HTTP round-trips per poll (up to ~1800 on an hour-long run). Introduce a per-run `AppEndpoints`
cache that resolves the base URL once per app and confirms health once per app (auto-starting a
down app on first miss, exactly as today), then reuses both. The safety is unchanged — an app is
still resolved + health-confirmed once, auto-start still runs, the circuit breaker still trips on
real failures, and the actual request still surfaces any later death. Only the *duplicate* pre-call
pings are removed. Backward compatible: `endpoints=None` (the default) keeps today's per-call
behaviour, so no existing caller changes semantics.

## Acceptance criteria

Each one names the test that proves it.

1. Sharing one `AppEndpoints` across calls resolves the launcher + health only once, while each
   operation call still goes through — proven by
   `tests/unit/test_app_caller.py::test_shared_endpoints_dedupes_resolve_and_health`.
2. Without a shared cache (`endpoints=None`), behaviour is unchanged (resolve + health each call) —
   proven by `tests/unit/test_app_caller.py::test_no_shared_endpoints_resolves_each_call`.
3. A real async poll loop over several polls resolves the launcher + checks health ONCE, not per
   poll — proven by `tests/unit/test_executor.py::test_async_poll_reuses_resolved_endpoint`.
4. All existing app_caller + executor tests stay green (auto-start, circuit breaker, deadline,
   health-failure paths) — make verify.

## Plan (before coding)

1. `app_caller.py`: add an `AppEndpoints` class caching resolved base URL (`_base`) and confirmed
   health (`_healthy`) per app id; move the resolve + health/auto-start/re-check logic into its
   `base_url()` / `ensure_healthy()` methods. `call_operation` gains `endpoints: AppEndpoints | None
   = None` and uses `endpoints or AppEndpoints()` (fresh = no caching = today's behaviour).
2. `executor.py`: create one `AppEndpoints` per `execute_plan` run and thread it through
   `_run_subtask` → `_run_app_op` → `call_operation` and `_run_async` → `call_operation`.
3. Tests as named above; keep existing tests untouched.
4. `make verify` (+ confirm decomposition eval stays 16/16).

## Failure analysis

<!-- MANDATORY when the same check fails 3x (doom-loop protocol). -->

## Done

Proof commit: sealed via `make push`   Auditor verdict: <pending>   Docs updated: STATE.md
