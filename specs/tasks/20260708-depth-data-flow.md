# Task: depth-data-flow

<!-- Fill Goal/Type/Scope/Acceptance BEFORE any code. This file IS the plan for
     this task; drift_check.py enforces the Scope line mechanically. -->

Status: planned
Type: feature
Scope: src/orchestrator/selector.py, src/orchestrator/executor.py, src/orchestrator/prompts/operation_select_system.md, tests/unit/test_selector.py, tests/unit/test_executor.py, plan-depth-orchestration.md, STATE.md
Phase: Phase 2 — depth (plan-depth-orchestration.md, Task 1: data flow between steps)

## Goal

A downstream subtask can use an upstream subtask's result: the operation+argument selector is
given the outputs of the subtasks it depends on, so (e.g.) step 2 can use the arXiv id that step 1
returned. Enables real multi-step orchestration (not independent single calls).

## Acceptance criteria

Each one names the test that proves it.

1. `select_operation` accepts upstream results and includes them in the prompt — proven by
   `tests/unit/test_selector.py` (new).
2. Executor passes each subtask's dependency outputs into selection — proven by
   `tests/unit/test_executor.py` (new).
3. `make verify` PASS (>=90% coverage; e2e replay unchanged).

## Plan (before coding)

<!-- NOT STARTED. This task file is committed now only so the depth phase plan
     (plan-depth-orchestration.md) is tracked. Fill this in and set Status: in progress
     before writing any code. -->

## Failure analysis

## Done

Proof commit: <sha>   Auditor verdict: <ON_TRACK/...>   Docs updated: yes/no/n-a
