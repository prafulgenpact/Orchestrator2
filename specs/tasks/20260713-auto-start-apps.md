# Task: auto-start-apps

Status: in progress
Type: feature
Scope: src/orchestrator/launcher.py, src/orchestrator/app_caller.py, tests/unit/test_launcher.py, tests/unit/test_app_caller.py, STATE.md
Phase: Phase 2 — depth (mini-task T2 of the 3 user asks; the user must never start apps by hand)

## Goal

When the orchestrator needs an app that isn't running, it starts that app's backend itself, waits
until it is healthy, then proceeds — the user never launches apps by hand. New `launcher.py` holds a
per-app launch spec (sibling folder, uvicorn entrypoint, extra env) and `ensure_started(app)`:
spawn the backend (detached, so it survives the short-lived CLI and is reused next run) on the
registry port, then poll health until ready or a bounded timeout. `call_operation` calls it when
the first health check fails, then re-checks — so a down app is auto-started instead of erroring.
If there is no launch spec or the start fails, behavior is unchanged (clean error, no hang).

## Acceptance criteria

Each one names the test that proves it.

1. `ensure_started` spawns via the injected spawner and returns True once health passes; returns
   False if there is no spec, the spawner fails, or health never comes up within the budget —
   proven by `tests/unit/test_launcher.py::test_ensure_started_*`.
2. Every non-fallback registry app has a launch spec whose backend dir + venv python exist —
   proven by `tests/unit/test_launcher.py::test_launch_specs_cover_all_apps`.
3. `call_operation` auto-starts a down app then succeeds (health fails once, ensure_started brings
   it up, call proceeds); if ensure_started fails it still errors cleanly — proven by
   `tests/unit/test_app_caller.py::test_call_auto_starts_down_app` and
   `::test_call_errors_when_autostart_fails`.
4. `make verify` PASS (>=90% cov). Live: a task needing a down app starts it and completes.

## Plan (before coding)

1. launcher.py: `LaunchSpec(folder, entrypoint, env)`, `LAUNCH_SPECS` (all 11 apps), `_SIBLING_ROOT`
   (repo parents[4]); `ensure_started(app, client, *, spawn=_spawn_uvicorn, sleep=asyncio.sleep,
   timeout_s, interval_s)` — spawn (detached uvicorn on app.port), then poll health (<500) until up.
   `_spawn_uvicorn` uses subprocess.Popen(start_new_session=True); returns False if venv missing.
2. app_caller.py: in `call_operation`, if the first `_is_healthy` fails, `await ensure_started(app,
   client)`; re-check health; only then raise if still down.
3. tests: test_launcher.py (injected spawner + MockTransport health); update/add app_caller tests
   for the auto-start path (inject a fake ensure_started).
4. `make verify`, commit, seal, push. Live-verify against a stopped app.

## Failure analysis

## Done

Proof commit: <sha>   Auditor verdict: <pending>   Docs updated: yes/no
