# Task: announce-fallbacks

Status: in progress
Type: feature
Scope: src/orchestrator/models.py, src/orchestrator/executor.py, src/orchestrator/render.py, tests/unit/test_models.py, tests/unit/test_executor.py, tests/unit/test_render.py, STATE.md
Phase: Phase 2 — depth (transparency; serves the objective's traceability constraint)

## Goal

Every web-fallback substitution is announced explicitly in the output — the user never has to dig
through the Results to discover an app was bypassed. When the safety net answers a subtask via the
web because the planner-chosen app could not (skip/error/no_match), the result carries a plain-English
`note` ("'<app>' could not handle this (<reason>); answered via web search instead"), and
`render_execution` prints a prominent "Fallbacks" block right under the Answer plus the note on the
step. No behavior change to routing/execution — this is disclosure only.

## Acceptance criteria

Each one names the test that proves it.

1. `SubtaskResult` carries an optional `note` (in `to_dict`, default None) — proven by
   `tests/unit/test_models.py::test_subtask_result_note_in_to_dict`.
2. The safety net sets a fallback `note` naming the bypassed app + reason on the web result —
   proven by `tests/unit/test_executor.py::test_web_safety_net_sets_disclosure_note`.
3. `render_execution` shows a "Fallbacks" disclosure block under the Answer when any result has a
   note, and omits it otherwise — proven by
   `tests/unit/test_render.py::test_execution_announces_fallback` and
   `::test_execution_no_fallback_block_when_none`.
4. `make verify` PASS (>=90% cov; dry-run e2e unchanged).

## Plan (before coding)

1. models.py: add `note: str | None = None` to `SubtaskResult` (+ `to_dict`).
2. executor.py: in `_run_subtask`, when the web safety net succeeds, attach the note via
   `dataclasses.replace` naming the originally-chosen app + its failure reason.
3. render.py: after the Answer/Sources, emit "Fallbacks:" listing every result `note`; also show
   the note under the step in Results.
4. Tests (above) + `make verify`, commit, seal, push.

## Failure analysis

## Done

Proof commit: <sha>   Auditor verdict: <pending>   Docs updated: yes/no
