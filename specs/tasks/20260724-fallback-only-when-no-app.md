# Task: fallback-only-when-no-app

Status: in progress
Type: bugfix
Scope: src/orchestrator/executor.py, src/orchestrator/synthesis.py, src/orchestrator/render.py, tests/unit/**, STATE.md
Phase: Phase 2 — Fix 2 of the web-fallback deep-dive (plan: ~/.claude/plans/before-going-to-solutions-modular-lampson.md)

## Goal

Web is used ONLY when the planner routes a subtask to the web-search app (no app fits). The
runtime "safety net" that silently answered from the web whenever a CHOSEN app failed/skipped/
returned no_match is removed. A chosen app that fails now produces an HONEST, visible failure —
naming the app and why — never a web substitute wearing the app's badge. Matches the objective:
"If some task has no relevant app, it fetches from the web" (planner-time only).

## Acceptance criteria

Each one names the test that proves it.

1. A chosen app that errors stays `error` (no web substitution) — proven by
   `tests/unit/test_executor.py::test_app_error_is_not_web_rescued`.
2. A chosen app that skips (missing required input) stays `skipped` — proven by
   `tests/unit/test_executor.py::test_app_skip_is_not_web_rescued`.
3. A chosen app whose output fails relevance stays `no_match` — proven by
   `tests/unit/test_executor.py::test_app_no_match_is_not_web_rescued`.
4. Planner-routed web fallback (app.fallback=True) STILL works unchanged — proven by the
   retained `tests/unit/test_executor.py::test_web_fallback_success`.
5. When no app produced a grounded result, the answer honestly names each app and why it could
   not complete (not the bland generic line) — proven by
   `tests/unit/test_synthesis.py::test_all_failed_answer_names_apps_and_reasons`.
6. A partial failure is surfaced under the answer ("⚠ Some parts could not be completed") —
   proven by `tests/unit/test_render.py::test_failed_subtasks_surface_as_heads_up`.
7. `make verify` PASS; decomposition eval unchanged.
8. Live (user acceptance): a task routed to a down/failing app returns an honest failure, no
   web answer; a genuinely no-app task still gets a web answer via the planner.

## Plan (before coding)

1. executor.py `_run_subtask`: delete the runtime rescue (current lines 151-163); return the
   app result directly. Keep the planner-routed `if app.fallback` path (line 146-147) untouched.
2. synthesis.py: add `_failed_results`; in the no-ok branch build a grounded, honest answer
   listing each failed app + a human reason from its status/error (no LLM, no invented facts).
3. render.py: add a "⚠ Some parts of the task could not be completed:" heads-up listing non-ok
   subtasks + reason, right under the Answer (reuses the existing traceability-banner pattern).
4. tests: invert the 4 web-safety-net tests (skip/error/no_match/selection-error now stay
   failed); keep the 4 planner-fallback tests; add synthesis + render tests. Remove the now-dead
   disclosure-note test.
5. `make verify`; user live-tests (criterion 8); STATE.md.

## Notes / decisions

- A mid-execution selector LLM error is now handled honestly per-subtask (rc=0, "could not be
  completed", names the app) instead of the old path (web rescue → synthesis LLM error → rc=4).
  The old test_execute_llm_error_returns_4 implicitly depended on the web rescue succeeding; it is
  repurposed to lock in the new honest behavior. Planner-stage LLM errors still exit 4
  (test_planner_failure_returns_4, test_max_retries_zero — unchanged).
- Possible follow-up (out of scope here): a non-zero exit code when ALL subtasks fail, for
  scripting hygiene. Not done — keeps Fix 2 to "remove web rescue + surface honestly".

## Failure analysis

(none — clean run)

## Done

Proof commit: <this commit>   Auditor verdict: <pending>   Docs updated: STATE.md
