# Task: env-local-resolution

Status: in progress
Type: feature
Scope: src/orchestrator/llm/foundry.py, tests/unit/test_foundry.py, .env, STATE.md
Phase: Phase 2 — depth (enables live `--execute` runs of the depth/synthesis demo; serves AC-1/AC-4 tooling)

## Goal

The orchestrator resolves Foundry credentials from a project-local `.env` (created in this task,
at the repo root) **automatically**, with no `ORCHESTRATOR_FALLBACK_ENV` export. Resolution order
becomes: process env → project `.env` → sibling `Blogs Playground/backend/.env` (unchanged
fallback). An explicit `ORCHESTRATOR_FALLBACK_ENV` still wins and remains the sole fallback file
(opt-out preserved), so every existing test — all of which set that override — is unaffected.

## Acceptance criteria

Each one names the test that proves it.

1. With no override set, credentials resolve from the project `.env` — proven by
   `tests/unit/test_foundry.py::test_resolve_from_project_env`.
2. The project `.env` outranks the sibling fallback (project wins on a key both define) — proven by
   `tests/unit/test_foundry.py::test_project_env_beats_sibling_default`.
3. An explicit `ORCHESTRATOR_FALLBACK_ENV` is still the sole fallback — the project `.env` is NOT
   consulted (opt-out) — proven by
   `tests/unit/test_foundry.py::test_explicit_override_ignores_project_env`.
4. `make verify` PASS (>=90% coverage; e2e replay unchanged; all prior foundry tests still green).

## Plan (before coding)

1. `.env` (gitignored) at repo root with the two Foundry keys copied from the sibling app's `.env`
   (`ANTHROPIC_FOUNDRY_API_KEY`, `ANTHROPIC_FOUNDRY_BASE_URL`).
2. foundry.py: add `PROJECT_ENV = parents[3] / ".env"`. In `resolve_credentials`, when
   `ORCHESTRATOR_FALLBACK_ENV` is set use `[that]` (as today); otherwise use
   `[PROJECT_ENV, DEFAULT_FALLBACK_ENV]`, merged so the project `.env` outranks the sibling.
   `pick()` keeps process-env-wins.
3. test_foundry.py: three new tests (above), each patching `PROJECT_ENV` to a tmp file so the real
   `.env` is never read.
4. `make verify`, commit (feat), `make seal`.

## Failure analysis

## Done

Proof commit: <sha>   Auditor verdict: <pending>   Docs updated: yes/no
