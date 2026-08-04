# Task: search-count-floor

Status: Done
Type: fix
Scope: src/orchestrator/registry.py, src/orchestrator/selector.py, registry/apps.json, tests/unit/test_registry.py, tests/unit/test_selector.py, STATE.md
Phase: Phase 2 — selector/contracts

## Goal (fix 1 of the RCA set)

A vague "find some good papers" must never collapse to 1 result. The paper count is chosen by the
LLM selector (`max_results`) with no floor, so it can under-set to 1. Add a per-operation numeric
floor the selector clamps UP to — honoring larger explicit counts, only raising the too-small ones.

## Acceptance criteria

1. `AppOperation.arg_min` parses from the contract (numbers only; non-number rejected) and
   round-trips in `to_dict` — unit-tested in test_registry.
2. `_enforce_arg_floors` raises a present numeric arg below the floor up to it, keeps larger values,
   and ignores bools/non-numbers and omitted args — unit-tested in test_selector.
3. `search_papers_by_query` and `search_papers_by_topic` carry `arg_min: {max_results: 5}`; a
   selection that returns `max_results: 1` yields `5` after selection — unit-tested end-to-end.
4. `make verify` PASS; decomposition eval unchanged (this is a value-level guard, not routing).

## Plan

- registry.py: `arg_min: dict[str, float]` field + `_parse_arg_min` + wire in `_parse_operation` +
  `to_dict`.
- selector.py: `_enforce_arg_floors(op, args)` called after `_enforce_field_types` (so "1" is a 1).
- apps.json: add `arg_min: {max_results: 5}` to the two ArXiv search ops.

## Done

Proof commit: (this commit)   Proof fingerprint: 578a11ffcfa1   Auditor verdict: <pending>   Docs updated: STATE.md
