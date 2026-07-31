# Task: web-connector-live-run

Status: Done
Type: feature
Scope: src/orchestrator/executor.py, src/orchestrator/web.py, web/atelier-workspace.html, tests/unit/test_executor.py, tests/unit/test_web.py, STATE.md
Phase: Whole-app UI — Phase 1 (live connector between the web UI and the running orchestrator)

## Goal

A user can type a task in the Atelier web UI, press send, and watch the REAL run stream live —
the progress feed and agent trace light up from the orchestrator's own messages, real app results
appear as cards, and the final synthesized answer streams in. Delivered as a small web connector
that serves the page and relays the orchestrator's existing `plan -> execute(progress) ->
synthesize(on_delta)` output to the browser over Server-Sent Events (SSE). No planner/executor/
synthesis change, so the decomposition eval stays 16/16.

## Acceptance criteria

Each one names the test that proves it.

1. `run_events(task, client, registry, model)` yields the run as an ordered event stream —
   `status` -> `plan` -> `progress`* -> `result`* -> `answer`* -> `final` -> `done` — driven by the
   real backend calls, and turns any failure into a single `error` event instead of raising —
   proven by `tests/unit/test_web.py::test_run_events_order` and `::test_run_events_error`.
2. `sse(event, data)` serialises one event to the SSE wire format
   (`event: <name>\ndata: <json>\n\n`) — proven by `tests/unit/test_web.py::test_sse_format`.
3. `ui_path()` resolves the served HTML from `$ATELIER_UI` or the bundled `web/` default —
   proven by `tests/unit/test_web.py::test_ui_path_env_override`.
4. `execute_plan(on_result=...)` streams each subtask's result the moment it finishes (not after
   the whole run), and the connector relays them live so intermediate app outputs appear as each
   app completes — proven by `tests/unit/test_executor.py::test_execute_streams_each_result` and
   `tests/unit/test_web.py::test_run_events_order` (a `result` event precedes the `answer` events).
5. `make verify` PASS (lint/format/types/unit >=90% cov/e2e/secrets); decomposition eval 16/16.

Live end-to-end (manual, recorded in the task): start the connector, open the page, type a task,
observe feed + trace animate live from real messages, cards appear, answer streams. The socket/
asyncio I/O shell (HTTP handler, `serve`, live execute wrapper) is exercised here, not by unit
tests, and is marked `# pragma: no cover`.

## Plan (before coding)

1. `src/orchestrator/web.py`: pure `run_events` generator (plan -> threaded execute+synthesize,
   callbacks pushed onto a queue and yielded live) + `sse`/`ui_path` helpers + a thin
   `ThreadingHTTPServer` handler and `serve()` entrypoint (`python -m orchestrator.web`).
2. `web/atelier-workspace.html`: the finalised UI, with the canned demo script replaced by an
   `EventSource` that drives the feed, trace, and cards from the live SSE events.
3. `tests/unit/test_web.py`: unit-test the generator's event order, error path, SSE format, and
   ui_path — backend calls monkeypatched, so no network/key.
4. `make verify`; update STATE.md; mark this task Done with the sealed proof commit.

## Failure analysis

<!-- MANDATORY when the same check fails 3x (doom-loop protocol). -->

## Done

Proof commit: <sha>   Auditor verdict: <pending>   Docs updated: n-a
