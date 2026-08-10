# Task: step-status-honesty

Status: in progress
Type: bugfix
Scope: src/orchestrator/executor.py, tests/unit/test_executor.py, STATE.md
Phase: Phase 3 — routing accuracy / honest status

## Goal

When an app's reply itself says the work failed (HTTP 200 but `success: false`, or a body that
is nothing but an error message), the step is marked "error" carrying the app's own message —
never "ok". Today the executor only checks transport success, so a crash inside a polite reply
shows a Done badge (the CLT-graphs silent failure).

## Acceptance criteria

Each one names the test that proves it.

1. A 200 reply shaped like Simulated Learning's real crash (`success: false` + traceback in
   `error`) marks the step "error" with the app's message — proven by
   `tests/unit/test_executor.py::test_app_reported_failure_marks_step_error` (fails before the fix).
2. A `success: true` reply that carries stderr noise in `error` next to real output stays "ok" —
   proven by `tests/unit/test_executor.py::test_success_with_stderr_noise_stays_ok`.
3. An error-only body (`{"error": "..."}` and nothing substantive else) marks the step "error"
   carrying that message — proven by
   `tests/unit/test_executor.py::test_error_only_body_marks_step_error`.
4. A `success: false` reply with no message still errors with a clear generic message — proven by
   `tests/unit/test_executor.py::test_app_failure_without_message_gets_generic_error`.
5. `make verify` PASS (trace badge, feed, run log, and final answer follow the status field
   automatically — no UI change needed).

## Plan (before coding)

1. Write the four tests above against the real reply shapes (failing first, bugfix rule).
2. Add `_app_reported_failure(data)` to `executor.py`: explicit false verdict (`success`/`ok`)
   wins; else an error-only body counts; message from error/detail/message/stderr/traceback.
3. Hook it in `_run_app_op` right after the transport check; also skip app-reported-failure
   items inside `_run_fan_out`.
4. Decision: the optional "retry once on the correct app" is NOT included — the registry fix
   already removes the misroute; keep this fix small and honest.

## Failure analysis

<!-- MANDATORY when the same check fails 3x (doom-loop protocol). -->

## Done

Proof commit: <sha>   Auditor verdict: <ON_TRACK/...>   Docs updated: yes/no/n-a
