# Task: web-safety-net

Status: in progress
Type: feature
Scope: src/orchestrator/executor.py, tests/unit/test_executor.py, STATE.md
Phase: Phase 2 — depth (completes the web fallback; serves the objective's "give it any task -> answer")

## Goal

When the app the planner chose for a subtask cannot ground it — it skips (missing input), errors
(app down / call failed), or its result is judged irrelevant (no_match) — the executor now
automatically retries that subtask via the web fallback (Tavily), and uses the web answer if it
succeeds. So general-knowledge tasks that route to a specialized-but-incapable app (e.g. "what is a
p-value?" -> Statistics Teacher, which skips) still return a grounded, cited answer. If the web
also fails, the ORIGINAL failure is preserved (no masking with a worse result). Bounded by the same
hard deadline (no hang). Decision: fall back on ANY non-ok outcome (skip/error/no_match).

## Acceptance criteria

Each one names the test that proves it.

1. A skipped subtask falls back to the web and returns the web answer, attributed to the fallback
   app — proven by `tests/unit/test_executor.py::test_web_safety_net_on_skip`.
2. An errored and a no_match subtask likewise fall back — proven by
   `::test_web_safety_net_on_error` and `::test_web_safety_net_on_no_match`.
3. If the web also fails, the original failure is returned unchanged (not masked) — proven by
   `::test_web_safety_net_keeps_original_failure_when_web_fails`.
4. `make verify` PASS (>=90% cov; existing failure tests still green — safety net is offline by
   default in unit tests). Live: "what is a p-value?" now returns a grounded, cited web answer.

## Plan (before coding)

1. executor.py: extract the primary app path (select -> required-field skip -> call -> relevance)
   into `_run_app_op`. In `_run_subtask`: run it; if `status == "ok"` return; else run
   `_run_web_fallback` against the registry's fallback entry and return the web result iff it is ok,
   otherwise return the original failure.
2. tests: autouse fixture disables the safety net by default (resolve_search_key -> None) so the
   existing failure tests stay offline and unchanged; add the 4 opt-in safety-net tests above.
3. `make verify`, commit, seal, push. Live-verify "what is a p-value?".

## Failure analysis

## Done

Proof commit: <sha>   Auditor verdict: <pending>   Docs updated: yes/no
