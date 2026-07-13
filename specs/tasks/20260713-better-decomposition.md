# Task: better-decomposition

Status: in progress
Type: fix
Scope: src/orchestrator/prompts/planner_system.md, src/orchestrator/planner.py, tests/e2e/fixtures/, STATE.md
Phase: Phase 2 — depth (fix under-decomposition + keyword-routing found live; serves AC-1)

## Goal

The planner decomposes a multi-part task into the distinct sub-goals the user actually asked for
and routes each to the best TOPICAL app — instead of collapsing everything into one subtask and
keyword-matching. Live failure: "explain LLM pre-training … teach me … show code … write a blog"
became just 2 subtasks (Teach Me + Blogs), missed Stanford LLM (the on-topic specialist), and made
no code subtask. Fix is a planner-prompt rewrite (v2): (1) one subtask per distinct ask/deliverable
— explanation, runnable code, and a written artifact are separate; (2) route by subject matter,
preferring the most topically-relevant specialist over a generic app or a word match (e.g. an
LLM/transformers question → the Transformers/LLM course app even if the user says "teach me");
(3) more than one app may be used when each adds distinct value; (4) drop the "smallest/minimal"
bias (typically 2–5 subtasks, up to 6).

## Acceptance criteria

1. Planner prompt v2 still starts with `version:`, still says the output is JSON, and PROMPT_VERSION
   is bumped to "2" — proven by `tests/unit/test_planner.py` (existing tests green, incl.
   `test_load_system_prompt_mentions_json` and the PROMPT_VERSION-based assertions).
2. `make verify` PASS (>=90% cov). The dry-run e2e fixture is re-recorded for the new prompt.
3. Live dry-run of the LLM task decomposes into distinct subtasks that INCLUDE Stanford LLM and a
   code step (not a single Teach-Me subtask); the CLT task still decomposes sensibly. (Recorded in
   the task Done notes — routing is model-driven, so this is a judgement check, not a unit assert.)

## Plan (before coding)

1. planner_system.md → v2 with the decomposition + topical-routing + multi-app rules above.
2. planner.py: `PROMPT_VERSION = "2"`.
3. Re-record the dry-run fixture: `AGENT_LLM_MODE=record python -m orchestrator "plan my week of
   learning transformers"`; delete the stale fixture.
4. `make verify`, commit, seal, push. Dry-run the LLM + CLT tasks and record the observed plans.

## Failure analysis

## Done

Proof commit: <sha>   Auditor verdict: <pending>   Docs updated: yes/no
