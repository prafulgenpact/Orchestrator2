# Task: ws-kernel-transport

Status: DONE
Type: feature
Scope: src/orchestrator/**, registry/apps.json, tests/unit/**, pyproject.toml, requirements-dev.txt, STATE.md
Phase: Phase 2 — capability coverage (the last capability: live Jupyter kernel over WebSocket)

## Goal

The orchestrator can run arbitrary Python in coding-playground's live kernel and get back stdout,
result reprs, and rendered matplotlib images (base64 PNG) — the one capability not reachable over
HTTP. Adds a WebSocket transport (`stream: "ws"`) and wires a `run_code` operation.

## Acceptance criteria

1. `AppOperation` accepts method `WS` (added to the allowed set) — proven by
   `tests/unit/test_registry.py` round-trip + the run_code op loading in `test_ws.py`.
2. The WS transport sends an execute request and assembles frames into `{text, images, error}`,
   stopping at `execute_reply`, bounded by the op deadline — proven by
   `tests/unit/test_ws.py::test_ws_run_assembles_text_and_images` and `::test_ws_run_reports_error`.
3. A `stream:"ws"` op is exempt from the HTTP contract check (it is not in any `/openapi.json`) —
   proven by `tests/unit/test_api_contract.py` staying green with the WS op present.
4. `make verify` passes; decomposition eval stays 16/16. Live-smoke run_code against the real kernel.

## Plan (before coding)

1. `registry.py`: add `WS` to `_ALLOWED_METHODS`.
2. `app_caller.py`: `_consume_ws(base_url, op, args, timeout)` — http→ws URL, connect, send
   `{"type":"execute","code": ...}`, collect frames (stream/execute_result → text; display_data
   image → images; error → error; execute_reply → stop); branch in `call_operation` on
   `op.stream == "ws"`. Wrapped in `run_with_deadline` (no hang).
3. `contract.py`: `check_op` returns [] for `stream == "ws"` (not an HTTP endpoint).
4. `registry/apps.json`: add coding-playground `run_code` (method WS, path /api/kernel/ws,
   stream "ws", request_fields ["code"], required ["code"]).
5. `pyproject.toml` + `requirements-dev.txt`: declare `websockets` (already installed, v12).
6. `tests/unit/test_ws.py`: monkeypatch `websockets.connect` with a scripted fake ws; cover the
   text+image happy path and the error path.
7. Live smoke + `make verify`.

## Notes

- Images come back as base64 PNG under `data["images"]`; rendering them to openable files is a
  possible later enhancement (reuse the artifact pipeline), out of scope here.
- run_code executes in the app's live kernel; kernel lifecycle (start/restart) is already wired.

## Failure analysis

## Done

WS transport added; `run_code` wired on coding-playground. Live-smoked against the real kernel
(stdout `42` + a 22KB base64 PNG). All 4 acceptance criteria met; make verify PASS; eval 16/16.
Every HTTP endpoint (215/215) + the one WebSocket capability now exposed.

Proof commit: <this commit>   Auditor verdict: <pending>   Docs updated: STATE.md
