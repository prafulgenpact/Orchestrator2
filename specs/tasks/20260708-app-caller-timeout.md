# Task: app-caller-timeout

Status: done
Type: bugfix
Scope: src/orchestrator/app_caller.py, tests/unit/test_app_caller.py, STATE.md
Phase: Phase 2 — depth (unblocks plan-depth-orchestration.md Task 3 live demo; serves AC-2)

## Goal

Long, legitimately-slow app operations (e.g. arXiv `analyze_paper`, an LLM-backed call with a 90s
budget in the registry) currently fail after ~5s with an empty-message `fatal:` error. The
app-caller wraps each call in `run_with_deadline(..., op.timeout_s)` (a 90s HARD outer cap) but
never passes a per-read `timeout` to the httpx request, so httpx's built-in 5s default fires first
and raises `httpx.ReadTimeout('')`. When this task is done, each call honors its own
`op.timeout_s` at the httpx layer, so slow-but-valid operations complete — and any error message
names the exception type instead of rendering a bare `fatal:`.

## Acceptance criteria

Each one names the test that proves it (bugfix = failing test FIRST).

1. The httpx request is issued with the operation's own timeout (not httpx's 5s default) — proven
   by `tests/unit/test_app_caller.py::test_operation_timeout_is_passed_to_httpx` (fails before the
   fix: read timeout is 5.0; passes after: equals `op.timeout_s`).
2. An exception with an empty message renders with its type name, not a bare `fatal:` — proven by
   `tests/unit/test_app_caller.py::test_empty_error_message_includes_exception_type`.
3. `make verify` PASS (>=90% coverage; e2e replay unchanged). The existing deadline/hang test
   still passes (the hard outer cap is unchanged and remains the anti-hang guarantee).

## Plan (before coding)

1. Write the two failing tests above in test_app_caller.py.
   - #1: MockTransport handler captures `request.extensions["timeout"]` for the operation call;
     assert its `read` equals a custom op's `timeout_s` (e.g. 90.0). Fails today (5.0 default).
   - #2: a transport that raises an empty-message error on the op call; assert the CallResult error
     contains the exception type name.
2. Fix app_caller.py:
   - In `attempt()`, pass `timeout=op.timeout_s` to `client.request(...)` so httpx honors the
     per-operation budget. `run_with_deadline(..., op.timeout_s)` stays as the hard outer cap.
   - In the `except` branch, render `f"{classify_error(exc)}: {exc or type(exc).__name__}"` so an
     empty exception string still carries the type.
3. `make verify`, commit (feat/fix), `make seal`.

Note (out of scope, logged for later): `httpx.ReadTimeout` is classified `fatal` by
`classify_error` because httpx timeout exceptions are not Python `TimeoutError` subclasses and
carry an empty message. Fixing the per-read timeout makes this moot for the happy path; a broader
classification review is a separate task.

## Failure analysis

## Done

Bugfix reproduced test-first (both tests failed before the fix: read timeout was 5.0 not 90.0;
error was a bare "fatal:"). All acceptance criteria met:
1. httpx request now carries `timeout=op.timeout_s` — proven by
   `test_operation_timeout_is_passed_to_httpx`.
2. Empty-message errors render with the exception type — proven by
   `test_empty_error_message_includes_exception_type`.
3. `make verify` PASS (fingerprint 964cbc013324); `test_deadline_on_hang` still green (hard outer
   cap unchanged). VERIFIED LIVE: MoE demo runs end-to-end (step 2 analyzed paper 2402.14800).

Proof commit: sealed via `make seal`   Auditor verdict: (pending @auditor)   Docs updated: yes (STATE.md)
