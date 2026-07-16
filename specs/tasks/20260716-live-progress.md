# Task: live-progress

<!-- Fill Goal/Type/Scope/Acceptance BEFORE any code. This file IS the plan for
     this task; drift_check.py enforces the Scope line mechanically. -->

Status: DONE
Type: feature
Scope: src/orchestrator/executor.py, src/orchestrator/cli.py, tests/unit/test_executor.py, tests/unit/test_cli.py
Phase: Phase 2 — UX (world-class, never looks stuck); reinforces AC-2 (slow != hung)

## Goal

The user sees continuous progress instead of a long silence then everything at once. Thread an
optional `progress` callback (default no-op, so tests stay silent/deterministic) through the
executor and have the CLI print those lines to **stderr** (stdout stays clean for `--json` and the
final answer). Emitted events: a "Starting apps..." line before the outset preflight; a live per-
subtask line as each STARTS and as each FINISHES (with status + duration); and a heartbeat during a
long async poll ("still working, app responding") so a genuinely slow start-then-poll job proves it
is alive (slow != hung). No behaviour change to results, ordering, or exit codes.

## Acceptance criteria

Each one names the test that proves it.

1. `execute_plan` emits a start line and a finish line (with status) per subtask via the `progress`
   callback — proven by `tests/unit/test_executor.py::test_execute_emits_progress`.
2. A long async poll emits at least one heartbeat while the job keeps responding — proven by
   `tests/unit/test_executor.py::test_async_poll_emits_heartbeat`.
3. The CLI prints progress to stderr (not stdout) and stdout is unchanged for `--execute` —
   proven by `tests/unit/test_cli.py::test_execute_progress_goes_to_stderr`.
4. Default is silent (no callback passed = no output) and all existing tests stay green — make verify.

## Plan (before coding)

1. `executor.py`: add a `ProgressFn = Callable[[str], None]` alias + a `_null_progress` default;
   thread `progress` through `execute_plan` -> `_guarded` (emit start/finish per subtask) ->
   `_run_subtask` -> `_run_app_op` -> `_run_async` (emit a heartbeat every few polls).
2. `cli.py`: a `_stderr_progress` helper; print "Starting apps..." before `start_all`; pass
   `progress=_stderr_progress` into `execute_plan`. Keep the readiness note as today.
3. Tests as named; assert ordering/among-events and the stdout/stderr split.
4. `make verify` (+ decomposition eval stays 16/16).

## Failure analysis

<!-- MANDATORY when the same check fails 3x (doom-loop protocol). -->

## Done

Proof commit: sealed via `make push`   Auditor verdict: <pending>   Docs updated: STATE.md
