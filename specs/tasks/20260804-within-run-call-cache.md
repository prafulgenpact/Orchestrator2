# Task: within-run-call-cache

Status: Done
Type: fix
Scope: src/orchestrator/executor.py, tests/unit/test_executor.py, STATE.md
Phase: Phase 2 — executor

## Goal (fix 2 of the RCA set)

When two subtasks in a run resolve to the exact same app call (same app, operation, and args) —
the redundant-decomposition case behind the duplicate cards — the executor should issue that app
call ONCE and share the result, instead of hammering the app twice. Must handle the concurrent
case (two identical subtasks in the same wave run in parallel).

## Acceptance criteria

1. Two identical idempotent calls (same app/op/args), whether concurrent or sequential, invoke the
   underlying `call_operation` exactly ONCE and both receive the same result — unit-tested with a
   call counter.
2. Non-idempotent or destructive ops are never cached (always call fresh); a failed call is not
   cached (a later identical call may retry) — unit-tested.
3. `make verify` PASS; decomposition eval unchanged.

## Plan

- executor.py: a per-run `call_cache: dict[key, asyncio.Task[CallResult]]` created in `execute_plan`,
  threaded to `_run_subtask` -> `_run_app_op`. New `_call_cached(...)` coalesces by
  `(app_id, op_name, json(args))` for idempotent non-destructive ops using a shared Task (so
  concurrent duplicates await the same call); pops the key on a not-ok result. `call_cache=None`
  (the default for direct callers/tests) means no caching — behaviour unchanged.
- Only the non-poll call path is cached (async start-then-poll is left as-is).

## Done

Proof commit: (this commit)   Proof fingerprint: 8d91b3c340b9   Auditor verdict: <pending>   Docs updated: STATE.md
