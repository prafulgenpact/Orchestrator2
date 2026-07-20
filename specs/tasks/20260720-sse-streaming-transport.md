# Task: sse-streaming-transport

Status: DONE
Type: feature
Scope: src/orchestrator/**, registry/apps.json, tests/unit/**, STATE.md
Phase: Phase 2 — capability coverage (final 100%: wire the streaming endpoints)

## Goal

The orchestrator reaches 100% of every app's non-internal endpoints, including the streaming
(Server-Sent-Events) ones. Adds a generic SSE transport so an op flagged `stream: "sse"` is consumed
to completion and assembled into a result (`text` + any structured `events`), then wires the 7 SSE
endpoints + the 1 JSON events endpoint that were previously deferred.

## Acceptance criteria

1. `AppOperation` carries `stream` (default None), parsed from the registry — proven by the
   registry round-trip tests + the SSE op assertion in `tests/unit/test_sse.py::_sse_op`.
2. The SSE consumer assembles token frames (both dialects) and collects structured events, stopping
   at `[DONE]` — proven by `tests/unit/test_sse.py::test_sse_call_assembles_tokens_and_events` and
   `::test_sse_text_handles_both_dialects_and_events`.
3. A streamed endpoint that errors is a clean failure, never a raise — proven by
   `tests/unit/test_sse.py::test_sse_call_error_status_is_clean_failure`.
4. 100% of non-internal endpoints are wired (deferred set now empty) — proven by
   `tests/unit/test_registry_coverage.py::test_all_non_streaming_endpoints_wired`.
5. `make verify` passes; decomposition eval stays 16/16. (Live-smoked `post_build_suggest` against
   the real github app: assembled 11k+ chars of streamed text.)

## Plan (before coding)

1. `registry.py`: add `stream: str | None = None` to `AppOperation` (+ to_dict + parse).
2. `app_caller.py`: `_sse_text` (frame -> text or None) + `_consume_sse` (stream via
   `client.stream`, accumulate text, collect events, stop at `[DONE]`, bounded by the op deadline);
   branch in `call_operation` when `op.stream == "sse"`.
3. `registry/apps.json`: wire 7 SSE ops (`stream:"sse"`) + `get_runs_events` (plain JSON — it is
   `application/json`, not a stream, despite living among the "streaming" group).
4. Flip `tests/unit/test_registry_coverage.py` deferred set to empty -> demands 100%.
5. Tests + live smoke + `make verify`.

## Failure analysis

## Done

Registry 207 -> 215 ops (7 SSE + 1 JSON). 100% of non-internal endpoints across all 11 apps now
exposed (WebSocket kernel is outside the OpenAPI denominator). make verify PASS; eval 16/16.

Proof commit: <this commit>   Auditor verdict: <pending>   Docs updated: STATE.md
