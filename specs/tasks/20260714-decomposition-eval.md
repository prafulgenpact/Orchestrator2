# Task: decomposition-eval

Status: in progress
Type: feature
Scope: tests/eval/**, specs/tasks/**, STATE.md
Phase: Phase 2 — depth (measure decomposition accuracy; serves AC-1)

## Goal

A labelled decomposition test set + offline scorer exists, so any change to the planner
prompt or app cards can be measured (routing + shape) instead of hand-checked on one task.
Today decomposition accuracy is judged by eyeballing a single example; after this we have a
number and can catch regressions.

## Acceptance criteria

1. `tests/eval/cases.json` holds >=15 labelled cases, each with `task`, `must_include`,
   `must_not_include`, `min_subtasks`, `max_subtasks` — proven by
   `tests/eval/test_decomposition.py::test_cases_wellformed` (schema + registry ids valid).
2. `tests/eval/test_decomposition.py` replays each case through `plan_task` and asserts the
   routing + subtask-count expectations; a case with no recorded fixture SKIPS (never errors),
   so `make verify` stays green before fixtures are recorded.
3. `make verify` PASS (coverage counts only `src`, so the harness does not move the gate).
4. Fixtures recorded live for the cases; the scorecard (pass rate + any misroutes) is written
   into this task's Done notes. Recording is model-driven, so the scorecard is the evidence,
   not a unit assert.

## Plan (before coding)

1. `tests/eval/cases.json` — cases covering the known app collisions (teach-me vs stanford-llm
   vs stats-teacher; ai-news vs social; blogs vs research; code -> simulated-learning not
   coding-playground; no-fit -> web-search) plus shape cases (the live multi-ask failure;
   don't over-decompose a single ask).
2. `tests/eval/test_decomposition.py` — well-formed check + per-case replay scorer (skips on
   MissingFixtureError). Builds the same request the CLI does, so hashes line up.
3. `tests/eval/record.sh` + `README.md` — record fixtures via the sanctioned CLI
   (`AGENT_LLM_MODE=record AGENT_LLM_FIXTURES=tests/eval/fixtures python -m orchestrator "<task>"`).
4. Record fixtures live; run the scorer; write the scorecard here. `make verify`, then stop for
   review before seal/push.

## Failure analysis

(none)

## Scorecard (baseline — current planner prompt v2)

Recorded live (`claude-opus-4-6`, prompt v2) and scored offline: **16 / 16 cases pass**.
Every collision routed correctly — LLM→stanford-llm (not teach-me), stats→stats-teacher,
news→ai-intelligence-deck (not social), blog→blogs-playground (not research), code→
simulated-learning (not coding-playground), no-fit→web-search. Shape held too: the live
multi-ask case split into stanford-llm + simulated-learning + blogs-playground; the single
ask stayed at 1 subtask. So prompt v2 is genuinely good across the collisions, not just the
one example — this is now the number to beat before/after any card or prompt change.

## Done

Proof commit: <pending seal/push>   Auditor verdict: <pending>   Docs updated: yes (tests/eval/README.md)
