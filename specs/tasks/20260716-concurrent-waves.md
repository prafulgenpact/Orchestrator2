# Task: concurrent-waves

<!-- Fill Goal/Type/Scope/Acceptance BEFORE any code. This file IS the plan for
     this task; drift_check.py enforces the Scope line mechanically. -->

Status: DONE
Type: refactor
Scope: src/orchestrator/executor.py, tests/unit/test_executor.py
Phase: Phase 2 — accuracy/robustness (AC-2: nothing may hang) + UX (responses faster)

## Goal

Independent subtasks within one dependency wave run **concurrently** instead of one-at-a-time, so a
plan the renderer already labels "(parallel)" actually executes in parallel. Two coupled changes:
(1) run a wave's subtasks with `asyncio.gather` rather than a serial `for`/`await`; (2) offload the
blocking synchronous LLM calls (`select_operation`, `check_relevance`) off the event loop with
`asyncio.to_thread`, so the coroutines can genuinely overlap. Concurrency is bounded by an
env-tunable semaphore (`ORCHESTRATOR_MAX_CONCURRENCY`, default 5) so parallel work never floods the
Foundry API. Cross-wave ordering and upstream→downstream data-flow are unchanged (waves stay
sequential; a wave still starts only after all its dependencies have finished). What is true after:
a wave of N independent subtasks finishes in ~1× the per-subtask time, not N×.

## Acceptance criteria

Each one names the test that proves it.

1. Independent subtasks in a wave run concurrently (peak in-flight == wave size when unbounded) —
   proven by `tests/unit/test_executor.py::test_wave_runs_subtasks_concurrently`.
2. Concurrency is capped by `ORCHESTRATOR_MAX_CONCURRENCY` (peak in-flight never exceeds the cap,
   and reaches it) — proven by `tests/unit/test_executor.py::test_wave_concurrency_is_bounded`.
3. Cross-wave ordering + upstream data-flow into downstream selection is preserved — proven by the
   existing `tests/unit/test_executor.py::test_execute_threads_upstream_output_into_downstream_selection`
   (stays green), and all existing executor tests stay green (make verify).

## Plan (before coding)

1. `executor.py`: in `execute_plan`, create a per-run `asyncio.Semaphore` from
   `ORCHESTRATOR_MAX_CONCURRENCY`; replace the inner `for sub in wave` loop with
   `asyncio.gather` over the wave, each subtask wrapped `async with sem`; index results into
   `by_id` after the wave completes (dependencies already satisfied — waves are sequential).
2. `executor.py`: in `_run_app_op`, call the two synchronous LLM functions via
   `await asyncio.to_thread(select_operation, ...)` and `await asyncio.to_thread(check_relevance, ...)`
   so they no longer block the event loop. Keep `selector.py`/`grounding.py` unchanged.
3. `tests/unit/test_executor.py`: add a thread-safe local fake client that records peak concurrency;
   assert concurrency happens (crit 1) and is bounded (crit 2). Existing tests unchanged.
4. `make verify` (+ confirm the decomposition eval stays 16/16).

## Failure analysis

<!-- MANDATORY when the same check fails 3x (doom-loop protocol). -->

## Done

Proof commit: sealed via `make push`   Auditor verdict: <pending>   Docs updated: STATE.md
