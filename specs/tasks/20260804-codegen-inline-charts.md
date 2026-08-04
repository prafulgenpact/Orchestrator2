# Task: codegen-inline-charts

Status: Done
Type: fix
Scope: src/orchestrator/prompts/operation_select_system.md, tests/unit/test_selector.py, STATE.md
Phase: Phase 2 — selector

## Goal (chart fix 1 of 3)

Intermediate charts must render. The kernel captures a figure only when the code DISPLAYS it
inline (`plt.show()` -> a `display_data` image frame). The model's generated code was saving
figures to disk (`savefig`) and printing "chart saved", so no image frames came back and the card
showed only text. Instruct the code-gen to display charts inline, never savefig.

## Acceptance criteria

1. The operation-select prompt tells the model that code producing charts must call `plt.show()`
   for each figure and must NOT `savefig`/write files — asserted by a unit test.
2. `make verify` PASS; decomposition eval unchanged (this is the selector prompt, not the planner).

## Plan

- Add the rule to `operation_select_system.md`; bump its `version:` 3 -> 4.
- Guard test in test_selector asserting the prompt mentions plt.show() + no savefig.

## Done

Proof commit: (this commit)   Proof fingerprint: 6dd93f331708   Auditor verdict: <pending>   Docs updated: STATE.md
