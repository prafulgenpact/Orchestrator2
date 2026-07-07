# Task: execute-clean-output

<!-- Fill Goal/Type/Scope/Acceptance BEFORE any code. This file IS the plan for
     this task; drift_check.py enforces the Scope line mechanically. -->

Status: in progress
Type: feature
Scope: src/orchestrator/render.py, src/orchestrator/cli.py, tests/unit/test_render.py, tests/unit/test_cli.py, STATE.md
Phase: Phase 2 — invoke apps (UX: clean --execute output)

## Goal

`--execute` prints a clean, three-part view by default: the input (task + intent), how the task was
decomposed (subtasks in steps, each with the chosen app, confidence, and rationale), and the output
(each subtask's grounded result + source). All operational detail (operation name, HTTP status,
timing, full payloads, per-subtask summary) moves behind a new `--verbose` flag.

## Acceptance criteria

Each one names the test that proves it.

1. Clean output shows task, intent, the decomposition with confidence + rationale, and each
   result with its source — proven by `tests/unit/test_render.py::test_execution_clean_shows_plan_and_result`.
2. Clean output omits operation name, HTTP status, timing, and status badges — proven by
   `tests/unit/test_render.py::test_execution_clean_hides_operational_detail`.
3. `--verbose` adds operation, status, timing, and full (untruncated) output — proven by
   `tests/unit/test_render.py::test_execution_verbose_adds_detail`.
4. `--execute` renders the clean view; `--execute --verbose` adds detail — proven by
   `tests/unit/test_cli.py` (updated execute tests).
5. `make verify` PASS (>=90% coverage; e2e replay unchanged).

## Plan (before coding)

1. `render_execution(plan, result, *, verbose=False)` — rebuild: Task / Intent / Plan (waves with
   app + confidence + rationale) / Results (grounded output + source). Verbose appends op/status/
   timing and shows full output instead of a preview.
2. `cli.py`: add `--verbose`; pass the plan + flag into `render_execution`.
3. Update `test_render.py` + `test_cli.py` for the new signature and clean-vs-verbose output.
4. `make verify` green; update STATE.md; mark Done with the sealed proof.

## Failure analysis

<!-- MANDATORY when the same check fails 3x (doom-loop protocol). -->

## Done

All 5 acceptance criteria met. `make verify` PASS — 201 unit tests, 100% coverage, e2e replay
green. `--execute` now prints a clean three-part view (input: task + intent; decomposition:
subtasks in steps with chosen app + confidence + rationale; output: grounded result + source).
Operational detail (operation name, status, timing, full untruncated payload) moved behind the
new `--verbose` flag. Verified live against the running arXiv app.

Proof commit: auto-sealed by `make verify` (AUTOSEAL) on branch Orchestrator2   Auditor verdict: (not yet run)   Docs updated: yes
