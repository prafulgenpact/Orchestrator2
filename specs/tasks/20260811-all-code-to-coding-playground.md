# Task: all-code-to-coding-playground

Status: DONE (all 6 acceptance criteria met, incl. the live HR re-run)
Type: bugfix
Scope: registry/apps.json, src/orchestrator/prompts/operation_select_system.md, tests/unit/test_selector.py, tests/eval/cases.json, tests/eval/fixtures/**, tests/e2e/fixtures/**, STATE.md
Phase: Phase 3 — routing accuracy / honest output

## Goal

Two user rules from 2026-08-11, and the fix for what the live HR re-run exposed:

1. ALL coding/analysis/modelling work goes to Coding Playground. Simulated Learning is for
   LEARNING ONLY and must never be routed code execution.
2. The code-writer is told what each app actually has installed, so it stops reaching for
   absent libraries (it asked for `requests`, which is not installed AND was never needed —
   pandas reads a URL directly).
3. The code-writer must NEVER invent stand-in data. In the HR re-run the chart step generated
   1,000 random rows, labelled them "the same representative IBM HR Attrition dataset", drew six
   charts from noise and reported success — so a step can fabricate while looking green. If the
   real data is not available, the step must fail honestly instead of simulating it.

## Acceptance criteria

Each one names the test that proves it.

1. Code/analysis tasks route to coding-playground, never simulated-learning — proven by the
   decomposition eval with THREE existing cases flipped to the new rule
   (`run-code-to-coding-playground` — renamed from `run-code-to-simulated-not-coding-playground`,
   `explain-plus-code-gradient-descent`, `multiask-llm-explain-code-blog`) plus the existing
   `clt-graphs-to-coding-playground`; recorded against the OLD registry they fail.
2. A learning/lesson task still routes to simulated-learning (its real purpose is not destroyed) —
   proven by a new eval case `lesson-practice-to-simulated-learning`.
3. The whole eval stays green after re-recording every fixture — 18 cases + wellformed, 0 skips.
4. The selector prompt carries the never-invent-data rule and the use-only-installed-libraries
   rule — proven by `tests/unit/test_selector.py::test_prompt_forbids_inventing_data` and
   `::test_prompt_requires_declared_libraries`.
5. `make verify` PASS.
6. Live proof: restart the connector, re-run the HR task; the modelling step goes to
   coding-playground (not simulated-learning) and no step generates random stand-in data.

## Plan (before coding)

1. Flip/add the eval cases; record against the CURRENT registry; show them FAIL (bugfix-first).
2. Add the two selector-prompt tests; show them FAIL.
3. `registry/apps.json`:
   - simulated-learning: learning-only; when_not says never route code execution / data analysis /
     modelling here (use coding-playground); state its sandbox has numpy + sklearn only.
   - coding-playground: it is THE app for running code; state what is installed (pandas, numpy,
     matplotlib, seaborn, scikit-learn) and that `requests` is absent — read URLs with pandas.
4. `operation_select_system.md` (bump version): never invent/simulate/generate stand-in data;
   use only the libraries the app declares.
5. Re-record ALL fixtures (eval + e2e) — registry AND prompt text are inside the request hash.
6. `make verify`, then the live HR re-run.

## Failure analysis

<!-- MANDATORY when the same check fails 3x (doom-loop protocol). -->

## Done

Proof commit: 4cd2f9e (see git log)   Auditor verdict: pending   Docs updated: STATE.md

Live proof (run 39c3bcb9, 2026-08-11): both code steps routed to coding-playground (none to
simulated-learning); NO step generated stand-in data — the EDA step declined to write code
rather than fabricating, where the previous run had produced 1,000 np.random rows; and fix 1
fired for the first time in the wild (t3, t4 skipped: "every step it depends on failed").

FOLLOW-UP FOUND BY THIS RUN (new task, not this one): the FINAL ANSWER still fabricates. With
t1 (web search) ok and t2-t4 skipped, `synthesize()` passes ONLY the ok results to the LLM
(`_synthesize_llm(client, task, ok, ...)`, synthesis.py:232) — the failed/skipped steps are used
only in the `if not ok:` branch. So the synthesiser is asked to answer the whole task, is never
told anything failed, and writes a full EDA + modelling narrative from the web blurb without
once saying 3 of 4 steps were skipped. Also: the run is recorded status "ok" (quality 0.25)
though only 1 of 4 steps produced anything, and t2's skip reason ("missing required input:
code") does not say the real cause (no data available to write code against).
