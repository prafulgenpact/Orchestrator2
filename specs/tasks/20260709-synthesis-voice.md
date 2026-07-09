# Task: synthesis-voice

Status: in progress
Type: feature
Scope: src/orchestrator/synthesis.py, src/orchestrator/prompts/synthesis_system.md, src/orchestrator/cli.py, src/orchestrator/render.py, tests/unit/test_synthesis.py, tests/unit/test_cli.py, tests/unit/test_render.py, STATE.md
Phase: Phase 2 — depth (plan-depth-orchestration.md Task 2 — serves AC-4)

## Goal

`--execute` ends with ONE grounded answer on top (an "Answer" section), not just a list of
per-app blobs. The answer is grounded strictly in the apps' results (with their source URLs) and
written in the user's voice. When exactly one app produced a prose answer, that text is passed
through VERBATIM (the apps are already tuned to the user's voice — re-writing would drift from
AC-4). When several apps contribute (or the lone result is structured data), one LLM call fuses
them into a single answer using ONLY those results. Per-step detail stays below the answer.

## Acceptance criteria

Each one names the test that proves it.

1. A single prose result is passed through verbatim (no LLM call, mode="verbatim") — proven by
   `tests/unit/test_synthesis.py::test_single_prose_result_is_verbatim`.
2. Multiple successful results are fused into one answer via one grounded LLM call
   (mode="synthesized"), and sources are collected from the results in code (not the model) —
   proven by `tests/unit/test_synthesis.py::test_multiple_results_are_synthesized` and
   `::test_sources_collected_from_results`.
3. When no app produced a grounded result, synthesis says so (mode="none") and makes no LLM call —
   proven by `tests/unit/test_synthesis.py::test_no_ok_results_is_none`.
4. `--execute` renders the Answer section on top with sources; per-step detail remains below —
   proven by `tests/unit/test_render.py::test_execution_renders_answer_section` and
   `tests/unit/test_cli.py::test_execute_shows_answer`.
5. `make verify` PASS (>=90% coverage; e2e replay unchanged).

## Plan (before coding)

1. `synthesis.py`: `Synthesis` dataclass (answer, mode, sources, `to_dict`) + `synthesize(client,
   plan_result, *, model) -> Synthesis`. Logic: collect status=="ok" results; 0 -> none; exactly
   1 with a non-empty string output -> verbatim; else -> one LLM call over a content-preserving
   view of each ok result. Sources = unique `source` URLs of the ok results (code, not model).
2. `prompts/synthesis_system.md`: grounded-only, user-voice, plain-prose system prompt.
3. `render.py`: `render_execution(plan, result, synthesis=None, *, verbose=False)` — optional 3rd
   arg (existing callers unaffected); when present, emit "Answer:" + indented text + "Sources:"
   above the existing Plan/Results.
4. `cli.py`: after `execute_plan`, call `synthesize(...)` (wrapped so an LLM error still returns 4)
   and pass it into `render_execution`.
5. Tests: new test_synthesis.py; add Answer-section tests to test_render.py; update the two
   --execute tests in test_cli.py (extra synthesis response) + assert the Answer section.
6. `make verify`, commit (feat), seal. Live demo: the MoE 2-step task returns ONE answer.

## Failure analysis

## Done

Proof commit: <sha>   Auditor verdict: <pending>   Docs updated: yes/no
