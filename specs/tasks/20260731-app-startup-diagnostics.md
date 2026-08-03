# Task: app-startup-diagnostics

Status: Done
Type: feature
Scope: src/orchestrator/launcher.py, src/orchestrator/app_caller.py, src/orchestrator/doctor.py, tests/unit/test_launcher.py, tests/unit/test_app_caller.py, tests/unit/test_doctor.py, run.sh, STATE.md
Phase: Phase 2 — resilience / diagnosability

## Goal

Make every app-startup failure diagnosable (covers the whole class, not just ArXiv/Postgres):

1. Capture each sibling app's startup stdout/stderr to a per-app log (today it goes to /dev/null,
   so crashes are invisible).
2. When a health check fails after a (re)start attempt, surface the REAL reason (the app's own
   error, e.g. "Connect call failed ('127.0.0.1', 5432)") in the error the orchestrator records —
   so the trace shows the cause instead of a generic "health check failed".
3. A preflight "doctor": `python -m orchestrator.doctor` (and `./run.sh --check`) lists each app's
   readiness and, for down apps, the captured reason.

## Acceptance criteria

1. `_extract_startup_error(text)` pulls the salient crash line from a captured uvicorn log
   (exception / Errno / "startup failed") — unit-tested with a real Postgres-refused sample and an
   empty log.
2. On a failed start, the surfaced error string includes the captured reason — unit test drives
   `call_operation`'s health-fail path with a stubbed `read_startup_error`.
3. `diagnose(...)` returns per-app up/down + reason (health monkeypatched); `render_doctor(...)`
   formats a readable table — both unit-tested.
4. `make verify` PASS; decomposition eval unchanged. Live: `python -m orchestrator.doctor` reports
   arxiv-papers DOWN with the Postgres reason.

## Plan

- launcher.py: `app_log_path(app_id)` under `logs/apps/`; `_spawn_uvicorn` writes stdout+stderr
  there (truncate per attempt); pure `_extract_startup_error(text)` + `read_startup_error(app_id)`.
- app_caller.py: enrich the health-fail `ConnectionError` with `read_startup_error(app.id)`.
- doctor.py: `diagnose(registry, client)` + `render_doctor(results)` + `main()` entrypoint
  (socket/asyncio shell `# pragma: no cover`).
- run.sh: `--check` short-circuit that runs the doctor and exits.

## Done

Proof commit: (this commit)   Proof fingerprint: 9939d340c689   Auditor verdict: <pending>   Docs updated: STATE.md

Live-verified: python -m orchestrator.doctor -> 10/11 up; "ArXiv Paper Guide DOWN — OSError: Connect call failed (:5432)". read_startup_error captured the Postgres crash from logs/apps/arxiv-papers.log.
