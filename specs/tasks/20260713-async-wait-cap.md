# Task: async-wait-cap

Status: in progress
Type: fix
Scope: src/orchestrator/executor.py, STATE.md
Phase: Phase 2 — depth (follow-on to async-poll; give long jobs enough time to finish)

## Goal

Real Blogs/Research jobs take longer than the 300s async cap (measured: a real blog ran 415s), so
they timed out and fell back to the web. Raise `_ASYNC_MAX_WAIT_S` to 600s so a real blog/report
completes and is delivered BY the app — still bounded (no infinite hang, AC-2). The wait is a
genuine trade-off (a multi-minute synchronous CLI wait); a fire-and-return-handle async UX is a
later option, noted for the human.

## Acceptance criteria

1. `_ASYNC_MAX_WAIT_S` is 600 — proven by `tests/unit/test_executor.py::test_async_times_out`
   still passing (it monkeypatches the cap, so it is independent of the value) and by
   `make verify` PASS.
2. Live: "write a short blog about X" is produced BY Blogs Playground (source :8010, no web
   fallback banner).

## Plan (before coding)

1. executor.py: `_ASYNC_MAX_WAIT_S = 600.0` (was 300.0).
2. `make verify`, commit, seal, push. Final live blog run to confirm delivery from Blogs Playground.

## Failure analysis

## Done

Proof commit: <sha>   Auditor verdict: <pending>   Docs updated: yes/no
