# Task: route-graph-work-to-coding-playground

Status: DONE (code + eval; live headless CLT proof owed together with step-status-honesty per the agreed e2e protocol)
Type: bugfix
Scope: registry/apps.json, tests/eval/cases.json, tests/eval/fixtures/**, tests/e2e/fixtures/**, STATE.md
Phase: Phase 3 — routing accuracy

## Goal

A "create graphs/charts" task routes to Coding Playground (which can actually draw), never to
Simulated Learning (whose Python sandbox has no plotting library). Today the registry misroutes
it: Simulated Learning's card never says it can't chart, and Coding Playground's card actively
tells the planner "to execute a code snippet use simulated-learning".

## Acceptance criteria

Each one names the test that proves it.

1. New routing case "Create graphs and charts illustrating the Central Limit Theorem" must pick
   coding-playground and must NOT pick simulated-learning — proven by
   `tests/eval/test_decomposition.py::test_decomposition_case[clt-graphs-to-coding-playground]`
   (failing-first: recorded against the OLD registry it fails; after the card fix and
   re-recording it passes).
2. The existing 16-case baseline stays green after the registry change — proven by re-recording
   all fixtures (`tests/eval/record.sh`) and `tests/eval/test_decomposition.py` passing 17/17
   with zero skips.
3. `make verify` PASS with the new registry text.

## Plan (before coding)

1. Add the CLT-graphs case to `tests/eval/cases.json`; record its fixture against the CURRENT
   registry and show the case FAIL (bugfix-first proof).
2. Edit `registry/apps.json`:
   - simulated-learning: state plainly it cannot make charts/graphs (no plotting library);
     point chart work at coding-playground in `when_not`.
   - coding-playground: delete the `when_not` line "to execute a code snippet use
     simulated-learning".
3. Re-record ALL fixtures via `tests/eval/record.sh` (registry text is in the request hash).
4. Run the eval: 17/17 pass, 0 skips. Then `make verify`.

## Failure analysis

<!-- MANDATORY when the same check fails 3x (doom-loop protocol). -->

## Done

Proof commit: 6527c9c (sealed by 34a9864)   Auditor verdict: pending   Docs updated: STATE.md
