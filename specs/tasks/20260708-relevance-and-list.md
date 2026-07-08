# Task: relevance-and-list

<!-- Fill Goal/Type/Scope/Acceptance BEFORE any code. This file IS the plan for
     this task; drift_check.py enforces the Scope line mechanically. -->

Status: in progress
Type: feature
Scope: src/orchestrator/grounding.py, src/orchestrator/executor.py, src/orchestrator/render.py, src/orchestrator/prompts/relevance_system.md, tests/unit/test_grounding.py, tests/unit/test_executor.py, tests/unit/test_render.py, STATE.md, plan-fix-relevance-and-list.md
Phase: Phase 2 — invoke apps (accuracy: relevance guard + list display)

## Goal

Two fixes so `--execute` never presents useless output: (1) clean output lists all results
(count + top titles) instead of truncating to one; (2) after an app returns results, a relevance
guard (one LLM check) confirms they actually address the task — if not, the subtask reports
"no relevant results found — <reason>" instead of the irrelevant payload.

## Acceptance criteria

Each one names the test that proves it.

1. A list result renders as a count + numbered top titles in clean mode; `--verbose` shows the
   full payload — proven by `tests/unit/test_render.py::test_execution_lists_results`.
2. `check_relevance` returns (relevant, reason) from one LLM call; fails open (relevant) on an
   unparseable check — proven by `tests/unit/test_grounding.py`.
3. Executor: a relevant result stays "ok"; an irrelevant one becomes status "no_match" with the
   reason and the raw output suppressed — proven by `tests/unit/test_executor.py`.
4. `no_match` renders as "no relevant results found — <reason>" — proven by
   `tests/unit/test_render.py::test_execution_no_match`.
5. `make verify` PASS (>=90% coverage; e2e replay unchanged).

## Plan (before coding)

1. New `grounding.py` + `prompts/relevance_system.md`: `check_relevance(client, subtask, output,
   *, model)` — compact-summarize the output, one LLM call -> {relevant, reason}; parse errors
   fail open.
2. `executor.py`: after a successful `call_operation`, run `check_relevance`; if not relevant set
   status "no_match" (output=None, error=reason).
3. `render.py`: list-aware clean output (count + top N titles) + a `no_match` line; verbose shows
   the full payload.
4. Tests for each (hermetic: FakeLLM); `make verify` green; update STATE.md; mark Done.

## Deferred (next slice)

Answering out-of-domain questions via a web-search fallback (for now they correctly return
"no relevant results found").

## Failure analysis

<!-- MANDATORY when the same check fails 3x (doom-loop protocol). -->

## Done

All 5 acceptance criteria met. `make verify` PASS — 217 unit tests, 100% coverage, e2e replay
green. `--execute` now: (1) lists all results (count + top titles) in clean mode, with the full
payload behind `--verbose`; (2) runs a relevance guard (`grounding.check_relevance`) after each
successful call — irrelevant results become `no relevant results found — <reason>` with the raw
output suppressed. New `grounding.py` + `relevance_system.md`; executor + render updated.

Proof commit: auto-sealed by `make verify` (AUTOSEAL) on branch Orchestrator2   Auditor verdict: (not yet run)   Docs updated: yes
