# Task: answer-discloses-what-failed

Status: in progress
Type: bugfix
Scope: src/orchestrator/synthesis.py, src/orchestrator/prompts/synthesis_system.md, tests/unit/test_synthesis.py, STATE.md
Phase: Phase 3 — honest output

## Goal

The final answer must never describe work that did not happen, and must say plainly what could
not be done. Today the honest "could not be completed" lines run ONLY when every step fails
(`synthesis.py`, `if not ok:`); when even one step succeeds, `_synthesize_llm` is handed the
successful results ALONE. The answer-writer is therefore never told anything failed, is asked to
answer the whole task, and fills the gaps from general knowledge.

Live proof of the bug (run 39c3bcb9, 2026-08-11): 3 of 4 steps skipped, yet the answer read
"Through EDA across the 35 variables, several patterns emerge…" and "Predictive models like
Gradient Boosting can identify at-risk employees with solid accuracy" — and contained the words
"skipped", "could not" and "unable" exactly zero times.

## Acceptance criteria

Each one names the test that proves it.

1. The failed/skipped steps are put in front of the answer-writer — proven by
   `tests/unit/test_synthesis.py::test_synthesis_message_lists_failed_steps`.
2. When some steps succeeded and others did not, the answer discloses what could not be done,
   naming the app — proven by
   `tests/unit/test_synthesis.py::test_answer_discloses_failures_when_some_succeeded`.
3. Disclosure does not depend on the model complying: the pass-through modes (a single prose
   result, and a terminal step that already folded in the others) disclose too — proven by
   `tests/unit/test_synthesis.py::test_verbatim_answer_still_discloses_failures` and
   `::test_final_step_answer_still_discloses_failures`.
4. A run where everything succeeded is untouched — no disclosure section, byte-for-byte the same
   answer — proven by `tests/unit/test_synthesis.py::test_no_disclosure_when_all_steps_succeeded`.
5. The synthesis prompt states that failed steps are listed and must be reported, never papered
   over — proven by `tests/unit/test_synthesis.py::test_prompt_requires_reporting_failures`.
6. `make verify` PASS, then a live HR re-run whose answer names the steps that did not run.

## Plan (before coding)

1. Write the six tests above (failing first).
2. `build_synthesis_message(task, ok, failed)` — add a "STEPS THAT PRODUCED NOTHING" block.
3. `synthesize()` — compute `failed` once; pass it to `_synthesize_llm`; and append a
   deterministic disclosure section in EVERY mode when failures exist, so honesty is mechanical
   rather than a request the model may ignore.
4. Prompt v1 -> v2: you are told which steps failed; report them plainly; never describe work
   that did not happen.

## Failure analysis

<!-- MANDATORY when the same check fails 3x (doom-loop protocol). -->

## Done

Proof commit: <sha>   Auditor verdict: <ON_TRACK/...>   Docs updated: yes/no/n-a
