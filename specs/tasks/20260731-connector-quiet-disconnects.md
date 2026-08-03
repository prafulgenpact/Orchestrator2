# Task: connector-quiet-disconnects

Status: Done
Type: fix
Scope: src/orchestrator/web.py, tests/unit/test_web.py, STATE.md
Phase: Whole-app UI — connector

## Goal

Stop the connector from dumping a scary traceback when a browser closes a socket early
(preconnect, refresh, navigating away mid-SSE). These `ConnectionResetError`/`BrokenPipeError`
raise in the base handler's request-line read — before our handler — so `_serve_run`'s existing
try/except never sees them, and the default `handle_error` prints a full traceback. It's harmless
(the server keeps serving), just noisy.

## Root cause (from the report)

`ConnectionResetError: [Errno 54] Connection reset by peer` in
`http.server.handle_one_request -> readline`, surfaced by `ThreadingHTTPServer.handle_error`.

## Fix

- Pure `_is_benign_disconnect(exc)` predicate (ConnectionReset/BrokenPipe/ConnectionAborted).
- A `ThreadingHTTPServer` subclass whose `handle_error` swallows those and defers to the base for
  everything else; `serve()` uses it.

## Acceptance criteria

1. `_is_benign_disconnect` is True for ConnectionResetError/BrokenPipeError/ConnectionAbortedError
   and False for other exceptions / None — unit-tested.
2. `make verify` PASS. Manually: a browser refresh no longer prints a traceback (socket shell is
   `# pragma: no cover`).

## Done

Proof commit: (this commit)   Proof fingerprint: 287602906c05   Auditor verdict: <pending>   Docs updated: STATE.md

Live-verified: 3 forced RST disconnects -> connector log clean, no traceback.
