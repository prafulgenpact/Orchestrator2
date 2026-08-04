# Task: plan-dedup-subtasks

Status: Done
Type: fix
Scope: src/orchestrator/validation.py, tests/unit/test_validation.py, STATE.md
Phase: Phase 2 — planner/validation

## Goal (fix 5 of the RCA set)

Stop redundant decomposition at the source: when the planner emits two subtasks that are exact
duplicates (same app AND normalized title), collapse them into one during validation, rewiring any
dependency on the dropped twin to the kept one. Deterministic and conservative (title-exact), so it
never touches the decomposition eval (its scenarios have distinct subtasks) — the fuzzy cases stay
covered by fixes 2 (call cache) and 3 (UI dedup).

## Acceptance criteria

1. `_dedupe_subtasks` collapses same-app + normalized-title duplicates (case/whitespace/trailing
   punctuation insensitive), rewires a dependency on a dropped twin to the kept id, and is a no-op
   otherwise — unit-tested.
2. `parse_plan` returns the de-duplicated, still-valid (unique ids, valid deps, DAG) plan — a plan
   with a duplicate subtask parses to one fewer subtask — unit-tested.
3. `make verify` PASS, and the decomposition eval stays 16/16 (this change is a no-op on distinct
   subtasks).

## Plan

- validation.py: `_norm_title` + `_dedupe_subtasks` (keep first, drop later twins, rewire deps);
  call it in `parse_plan` right after parsing subtasks and before the id/dep/DAG checks.

## Done

Proof commit: (this commit)   Proof fingerprint: 7b5de058e573   Auditor verdict: <pending>   Docs updated: STATE.md

Decomposition eval (tests/eval, run manually as the referee): 17 passed — unchanged by this no-op-on-distinct-subtasks change.
