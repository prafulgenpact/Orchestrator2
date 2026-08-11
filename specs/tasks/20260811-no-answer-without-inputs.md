# Task: no-answer-without-inputs

Status: in progress
Type: bugfix
Scope: src/orchestrator/executor.py, tests/unit/test_executor.py, STATE.md
Phase: Phase 3 — honest output

## Goal

A step that depends on other steps must not run when EVERY one of those steps failed. Today it
runs with no data and the app invents an answer — the HR run's blog step received only a topic
string (both analysis steps had failed) and produced confident, fabricated metrics ("95%
accuracy", "12% recall") that no computation ever produced. After this task such a step is
"skipped", stating which steps it was waiting on, and the honest failure flows into the final
answer, the feed, the trace and the run log.

## Acceptance criteria

Each one names the test that proves it.

1. A subtask whose dependencies ALL failed is skipped and its app is never called — proven by
   `tests/unit/test_executor.py::test_step_skipped_when_all_dependencies_failed`.
2. The skip reason names the steps it was waiting on, so the answer can explain itself — proven by
   `tests/unit/test_executor.py::test_skip_reason_names_the_failed_dependencies`.
3. A subtask with at least ONE successful dependency still runs as before — proven by
   `tests/unit/test_executor.py::test_step_runs_when_any_dependency_succeeded`.
4. A subtask with no dependencies always runs (rule applies only to dependent steps) — proven by
   `tests/unit/test_executor.py::test_step_without_dependencies_always_runs`.
5. The skip cascades: a step depending only on a skipped step is skipped too, and no app is
   called for either — proven by `tests/unit/test_executor.py::test_skip_cascades_downstream`.
6. `make verify` PASS; the whole executor suite stays green (no existing behaviour regressed).

## Plan (before coding)

1. Write the five tests above (failing first, bugfix rule).
2. In `executor.py`, before running a subtask: if it declares dependencies and none of them
   finished "ok", return a `skipped` SubtaskResult naming those steps — no selection LLM call,
   no app call.
3. Reuse the existing `skipped` status so the counts, run record, synthesis wording, trace badge
   and feed all follow with no further change.

## Failure analysis

<!-- MANDATORY when the same check fails 3x (doom-loop protocol). -->

## Done

Proof commit: <sha>   Auditor verdict: <ON_TRACK/...>   Docs updated: yes/no/n-a
