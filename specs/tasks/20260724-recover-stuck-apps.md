# Task: recover-stuck-apps

Status: in progress
Type: bugfix
Scope: src/orchestrator/launcher.py, src/orchestrator/app_caller.py, registry/apps.json, tests/unit/**, STATE.md
Phase: Phase 2 — Fix 4 of the web-fallback deep-dive (plan: ~/.claude/plans/before-going-to-solutions-modular-lampson.md)

## Goal

A hung-but-listening app (the 6-day ArXiv case: process up, answering nothing, port held so a
fresh start can't bind) is automatically recovered at run start — the stale process is killed and
the app relaunched — instead of silently timing out into web fallback every run. Health checks
become honest: teach-me's SPA page (HTML 200 on any path, incl. its /models health route) no
longer counts as "healthy", so a broken teach-me is detected (and recovered) rather than trusted.

## Acceptance criteria

Each one names the test that proves it.

1. A health response that is the SPA HTML fallback (200 text/html) is NOT healthy; a real 2xx
   JSON is — proven by `tests/unit/test_launcher.py::test_html_response_is_not_healthy` and
   `::test_json_2xx_is_healthy`.
2. teach-me's registry health path is a real JSON API route (/topics), not the SPA /models —
   proven by `tests/unit/test_registry.py::test_teach_me_health_is_real_api_route`.
3. A stale process that matches THIS app's launch signature (uvicorn + entrypoint + backend
   folder) squatting the port is reaped; a non-matching process is NEVER killed — proven by
   `tests/unit/test_launcher.py::test_reap_kills_only_matching_process` and
   `::test_reap_spares_unrelated_process`.
4. ensure_started is health-first (already-healthy app → no spawn, no reap) and, when unhealthy,
   reaps then respawns — proven by `tests/unit/test_launcher.py::test_ensure_started_healthy_skips_spawn`
   and `::test_ensure_started_reaps_then_respawns`.
5. `make verify` PASS; decomposition eval unchanged.
6. Live (user acceptance): with the real ArXiv process hung on 8002, a run that routes to ArXiv
   recovers it (kill + relaunch) and returns a real ArXiv answer — no web fallback, no 6-day hang.

## Plan (before coding)

1. launcher.py:
   - `is_healthy_response(status, content_type)` (pure): 2xx AND not text/html. Use in `_health_ok`.
   - `_pids_on_port` (lsof), `_cmdline` (ps), `_kill` (SIGTERM→SIGKILL): real-syscall helpers,
     `# pragma: no cover`, each injectable.
   - `reap_stale_listeners(port, spec, *, list_pids, cmdline, kill)` (pure orchestration): kills
     only processes whose cmdline contains uvicorn AND spec.entrypoint AND spec.folder — the
     positive-identification safety rule (never kill by port alone). Returns killed PIDs.
   - `ensure_started`: health-first return; else reap → spawn → poll (add `reap` param, injectable).
2. app_caller.py `_is_healthy`: use the same `is_healthy_response` (import from launcher).
3. registry/apps.json: teach-me health `/models` → `/topics`.
4. tests: launcher (health-response, reap safety, ensure_started flows with fakes), registry
   (teach-me health route). `make verify`; user live-tests ArXiv recovery (criterion 6).

## Notes / decisions

- Scoped to health-honesty + stale-process reaping (the "stuck for days" fix). Circuit-breaker
  cooldown/half-open recovery (deep-dive R5) is a separate, later task — kept out to stay reviewable.
- github-learnings /api/repos/ is a REAL JSON route (live-probed: 200 JSON, bogus paths 404) —
  honest already, left unchanged. Only teach-me was false-healthy (SPA HTML on every path).
- Reap safety: a process is killed ONLY if positively identified as this app's own uvicorn
  (entrypoint + backend folder in cmdline). Anything unidentifiable is left alone.

## Failure analysis

(none — clean run)

## Done

launcher/app_caller/registry + tests. make verify PASS (fingerprint f0ebf1a3b500). Unit: health
verdict rejects SPA HTML + non-2xx; reap kills only positively-identified same-app uvicorn and
spares everything else; ensure_started is health-first then reap+respawn. teach-me health moved
/models -> /topics. Live ArXiv recovery observed via PID-change (see live run).

Proof commit: <this commit>   Auditor verdict: <pending>   Docs updated: STATE.md
