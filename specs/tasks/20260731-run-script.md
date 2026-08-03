# Task: run-script

Status: Done
Type: chore
Scope: run.sh, docs/RUNBOOK.md, STATE.md
Phase: tooling / DX

## Goal

One command starts the whole Orchestrator app for the user and opens it in the browser. In this
architecture the connector (`python -m orchestrator.web`) IS both the "backend" (orchestration +
SSE) and the "frontend" (it serves the Atelier UI), and it launches the 11 sibling apps on demand
— so there is one server to start, not two.

## Acceptance criteria

1. `./run.sh` loads `.env`, frees the port of any stale connector, starts the connector, waits for
   it to answer, and opens `http://127.0.0.1:$PORT/`; Ctrl-C stops it cleanly — verified by
   actually running it and hitting the served page.
2. Port is configurable (`ATELIER_PORT` or first arg); browser-open is skippable (`NO_OPEN=1`).
3. `make verify` PASS (script is not in the enforcement layer; lives at repo root, not `scripts/`).

## Notes

- Freeing the port first is deliberate: it guarantees you always run the current code and avoids
  the stale-long-running-process class of bug.
- Sibling apps (ports 8001–8011) cold-start on demand during the first run; no separate command.

## Done

Proof commit: (this commit)   Proof fingerprint: d5dcfb95407a   Auditor verdict: <pending>   Docs updated: RUNBOOK.md
