# Task: phase1-app-fixes

Status: in progress
Type: feature
Scope: registry/apps.json, src/orchestrator/registry.py, src/orchestrator/executor.py, tests/unit/test_registry.py, tests/unit/test_executor.py, tests/e2e/fixtures/, STATE.md
Phase: Phase 2 — depth (all-11-apps plan, Phase 1 hardening; serves AC-1 routing accuracy + AC-2 no-hang)

## Goal

Two additive accuracy fixes found by end-to-end verification (no existing behavior overwritten):

1. **Routing.** Code-execution tasks were routed to Coding Playground, which has no REST op to run
   code (execution is WebSocket-only, arriving in Phase 3) — so the call could never succeed.
   Trim Coding Playground's registry `capabilities`/`example_tasks`/`description` to reflect only
   its real REST surface (kernel control + dataset browse/preview), so "run code" routes to
   Simulated Learning instead. (Code-execution capability returns in Phase 3 with the WS transport.)

2. **Required inputs (skip, don't 422).** Add an optional per-operation `required_fields` to the
   contract. When the selector cannot supply a required field, the executor SKIPS the operation
   (no HTTP call) with a clear reason, instead of firing a doomed request. Statistics Teacher's
   `ask_question` declares `module_id`/`module_title`/`module_part` required; since a free-form
   question has no module context (and the app has no module-discovery endpoint), Stats Teacher is
   now skipped cleanly rather than returning HTTP 422. (Decision: accuracy-safe — never invent a
   module, which could yield module-mismatched answers.)

## Acceptance criteria

Each one names the test that proves it.

1. `AppOperation` parses `required_fields` (list of strings; default empty) — proven by
   `tests/unit/test_registry.py::test_operation_required_fields_parsed`.
2. The executor skips an op (status "skipped", no HTTP call) when a required field is absent/blank
   in the selected args — proven by `tests/unit/test_executor.py::test_skips_when_required_field_missing`.
3. The shipped registry marks Stats Teacher `ask_question`'s module fields required, and Coding
   Playground no longer advertises code execution — proven by
   `tests/unit/test_registry.py::test_stats_requires_module_context` and
   `tests/unit/test_registry.py::test_coding_playground_is_rest_only`.
4. `make verify` PASS (>=90% coverage; e2e replay unchanged). Live re-check: "run this Python …"
   routes to Simulated Learning; a bare stats question skips Stats Teacher instead of 422.

## Plan (before coding)

1. registry.py: add `required_fields` to `AppOperation` (+ `to_dict`, + `_parse_operation`).
2. apps.json: Coding Playground capabilities/example_tasks/description → REST reality; Stats Teacher
   `ask_question` gets `"required_fields": ["module_id","module_title","module_part"]`.
3. executor.py: in `_run_subtask`, after `select_operation`, skip when any `op.required_fields` is
   missing/blank in args (return a "skipped" SubtaskResult; no `call_operation`).
4. Tests (above) + `make verify`, commit, seal. Live re-verify the two behaviors.

## Failure analysis

## Done

Proof commit: <sha>   Auditor verdict: <pending>   Docs updated: yes/no
