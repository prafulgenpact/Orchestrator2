# Task: chosen-app-answers

Status: in progress
Type: feature
Scope: src/orchestrator/registry.py, src/orchestrator/selector.py, registry/apps.json, tests/unit/test_registry.py, tests/unit/test_selector.py, tests/unit/test_executor.py, STATE.md
Phase: Phase 2 — depth (mini-task T3 of the 3 user asks; user CONFIRMED: use the relevant app, web only when none fits)

## Goal

When a relevant app exists, it answers — the orchestrator does not quietly fall back to the web.
The concrete gap: Statistics Teacher requires a course module, so a plain "what is a p-value?"
skipped it and the web answered. Fix: operations can declare `defaults` (values the selector fills
for any request field the model didn't provide). Statistics Teacher's `ask_question` gets a default
general module, so stats intent is served by Statistics Teacher, not the web. General, additive
mechanism (any op can carry defaults); web fallback now fires only when no app can genuinely serve.

## Acceptance criteria

Each one names the test that proves it.

1. `AppOperation` parses `defaults` (a JSON object; default empty), included in `to_dict` — proven
   by `tests/unit/test_registry.py::test_operation_defaults_parsed`.
2. The selector fills a missing request field from `defaults` but never overrides a value the model
   supplied — proven by `tests/unit/test_selector.py::test_select_applies_defaults` and
   `::test_select_defaults_do_not_override_model`.
3. The shipped Statistics Teacher `ask_question` carries a default module so it is no longer skipped
   for a plain question — proven by `tests/unit/test_registry.py::test_stats_has_module_defaults`.
4. `make verify` PASS (>=90% cov; dry-run e2e unchanged). Live: "what is a p-value?" is answered by
   Statistics Teacher (no web fallback banner).

## Plan (before coding)

1. registry.py: add `defaults: dict[str, Any]` to `AppOperation` (+ parse: must be an object; +
   to_dict).
2. selector.py: after grounding args, `args.setdefault(k, v)` for each `op.defaults` item.
3. apps.json: Statistics Teacher `ask_question` gets
   `"defaults": {"module_id": 1, "module_title": "General Statistics", "module_part": "Overview"}`.
4. tests: registry (defaults parsed + to_dict + Stats defaults), selector (fills missing / keeps
   model value); adjust the executor required-field skip test (module_title/part are now defaulted,
   so a blank module_id is the residual skip). `make verify`, commit, seal, push. Live-verify.

## Failure analysis

## Done

Proof commit: <sha>   Auditor verdict: <pending>   Docs updated: yes/no
