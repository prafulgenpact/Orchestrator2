# Task: synthesis-no-truncate

Status: in progress
Type: fix
Scope: src/orchestrator/synthesis.py, src/orchestrator/cli.py, tests/unit/test_synthesis.py, tests/unit/test_cli.py, STATE.md
Phase: Phase 2 — depth (fix the truncated multi-app answer found live on the CLT run)

## Goal

Rich multi-app answers are no longer cut off. Live, a 4-app run (explain + repos + code + blog)
truncated mid-code because synthesis re-fused everything into a 1500-token LLM answer. Two fixes:
(1) when the plan has a single terminal step (nothing depends on it; it depends on other ok steps)
that produced prose, pass THAT through as the answer — it already consumed the upstream results, so
re-fusing is redundant and lossy; (2) raise the fuse budget so genuine multi-result fusions aren't
truncated. Sources are still collected from all ok results.

## Acceptance criteria

Each one names the test that proves it.

1. A single terminal step (depends on others, nothing depends on it) with prose output is passed
   through as the answer (mode "final-step"), with sources from ALL ok results — proven by
   `tests/unit/test_synthesis.py::test_dominant_terminal_passed_through`.
2. Independent parallel results (no single terminal) are still fused (mode "synthesized") — proven
   by `::test_no_terminal_still_fuses`; a non-prose terminal is not passed through — by
   `::test_terminal_must_be_prose`.
3. The fuse budget is raised (>= 4000 tokens) — proven by `::test_synthesis_budget_raised`.
4. `make verify` PASS (>=90% cov). Live: the CLT-style task returns a complete (untruncated) answer.

## Plan (before coding)

1. synthesis.py: `_MAX_TOKENS` 1500 -> 4000; add `_dominant_terminal(ok, subtask_deps)`; `synthesize`
   gains `subtask_deps: dict[str, tuple[str,...]] | None = None` and, before the fuse, returns the
   dominant terminal's prose (mode "final-step") when one exists.
2. cli.py: pass `subtask_deps={s.id: s.depends_on for s in plan.subtasks}` to `synthesize`.
3. tests: synthesis (terminal pass-through / no-terminal fuse / non-prose terminal / budget); cli
   unaffected (small cases). `make verify`, commit, seal, push. Live-verify the CLT task.

## Failure analysis

## Done

Proof commit: <sha>   Auditor verdict: <pending>   Docs updated: yes/no
