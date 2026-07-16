# Task: reduce-unwarranted-web-fallbacks

<!-- Umbrella task for the "fix unexpected web fallbacks" work (the human asked for
     these together and will review/commit as one unit). Scope covers all three fixes. -->

Status: in progress
Type: bugfix
Scope: src/orchestrator/**, tests/unit/**, registry/**
Phase: Phase 2 — accuracy/robustness (fewer unwarranted web fallbacks; serves AC-1, AC-2)

## Goal

Cut the web fallbacks that happen when the RIGHT app was chosen but execution failed.
Three fixes:

1. Relevance guard judges the app's FULL output (no 1500-char truncation) under explicit
   PASS/FAIL rules with a deterministic empty gate — it no longer silently discards a
   correct answer on a strict judge's discretion. (DONE)
2. Slow ≠ hung: the async poll loop no longer gives up on a fixed wall-clock budget. It keeps
   polling while the app keeps responding (progress), stops early only when the app goes
   silent (consecutive failed polls = no progress), and retains only a GENEROUS, env-tunable
   absolute ceiling as the AC-2 anti-hang backstop. Long sync ops (Teach Me create_topic /
   send_user_message) get generous timeouts. (NOTE: Teach Me exposes no status endpoint, so
   it cannot be converted to background-poll with glue code — it stays synchronous with a
   raised bound; true progress-polling needs a status endpoint inside the Teach Me app.)
3. Start all apps at the outset: before any subtask executes, every non-fallback app is
   started and health-confirmed, so a dead app is never invoked (which today falls to web).

## Acceptance criteria

Each one names the test that proves it.

1. Full output, no truncation — `tests/unit/test_grounding.py::test_full_output_is_not_truncated`.
2. Deterministic empty gate (no LLM) — `::test_blank_output_fails_without_llm`.
3. Verdict handling + fail-open — `::test_verdict_fail`, `::test_verdict_pass`,
   `::test_fails_open_on_bad_json`, `::test_fails_open_on_unknown_verdict`,
   `::test_fails_open_on_llm_error`; prompt rules — `::test_prompt_states_pass_fail_rules`.
4. Async keeps polling a responsive-but-slow job and completes (past the old cap) —
   `tests/unit/test_executor.py::test_async_slow_but_responsive_completes`.
5. Async stops on no-progress (consecutive silent polls), not on a blip —
   `::test_async_stops_when_app_goes_silent`, and a single blip is tolerated —
   `::test_async_tolerates_transient_poll_blip`.
6. Async still has a hard absolute ceiling (AC-2 backstop) — `::test_async_times_out`.
7. Start-all preflight starts + health-confirms every non-fallback app before execution and
   reports which came up — `tests/unit/test_executor.py::test_prestart_apps_*` (or launcher).

## Plan (before coding)

1. (done) relevance: grounding.py + relevance_system.md + tests.
2. executor `_run_async`: no-progress semantics + env-tunable generous ceiling; registry: raise
   Teach Me create_topic/send_user_message timeouts; update async tests.
3. preflight start-all in the execute path (cli/executor + launcher.ensure_started fan-out).
4. `make verify`.

## Failure analysis

<!-- MANDATORY when the same check fails 3x (doom-loop protocol). -->

## Done

Proof commit: <sha>   Auditor verdict: <ON_TRACK/...>   Docs updated: yes/no/n-a
