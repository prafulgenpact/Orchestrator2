# Task: datastore-bring-up

Status: Done
Type: chore
Scope: datastores.sh, docs/RUNBOOK.md, STATE.md
Phase: tooling / DX

## Goal

Provide a one-command way to bring up the local datastores the sibling apps need, so the DB-backed
apps actually run. Investigation showed only ONE app hard-requires a datastore today: ArXiv Paper
Guide needs PostgreSQL on :5432 with a database named `arxiv_explorer` (Coding/Blogs Playground boot
fine without MySQL/Redis — those are optional/lazy). ArXiv creates its own tables on startup
(`Base.metadata.create_all` in its lifespan), so it only needs Postgres up + the empty DB present.

## Acceptance criteria

1. `./datastores.sh` starts Postgres (Homebrew `postgresql@16`, already installed) and creates the
   `arxiv_explorer` database if missing — idempotent (safe to re-run).
2. After running it, ArXiv Paper Guide boots and is healthy — verified: `python -m orchestrator.doctor`
   shows `ArXiv Paper Guide UP`.
3. `make verify` PASS (script lives at repo root, not the enforcement layer; no src change).

## Plan

- `datastores.sh`: ensure `postgresql@16` (install if absent), `brew services start` it, wait for
  `pg_isready`, `createdb arxiv_explorer` if missing. Uses the formula's bin (not on PATH).
- Note the Docker alternative (daemon currently off) and that MySQL/Redis aren't required today.
- RUNBOOK: document `./datastores.sh` alongside `./run.sh`.

## Done

Proof commit: (this commit)   Proof fingerprint: 780a00edff25   Auditor verdict: <pending>   Docs updated: RUNBOOK.md

Live-verified: ./datastores.sh -> Postgres up on :5432 + arxiv_explorer present; ArXiv ensure_started True; doctor shows ArXiv Paper Guide UP :8002. Fixed a stale postmaster.pid (recorded PID had been recycled to a non-postgres process).
