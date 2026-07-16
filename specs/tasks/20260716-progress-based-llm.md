# Task: progress-based-llm

<!-- Fill Goal/Type/Scope/Acceptance BEFORE any code. This file IS the plan for
     this task; drift_check.py enforces the Scope line mechanically. -->

Status: DONE
Type: refactor
Scope: src/orchestrator/llm/foundry.py, tests/unit/test_foundry.py
Phase: Phase 2 — accuracy/robustness (AC-2: nothing may hang, without capping genuine work)

## Goal

A live LLM call is judged by **progress, not a total stopwatch** — the same "slow is not hung" rule
the app-poll loop already uses. `FoundryClient.complete` switches from `messages.create` (one big
blocking read, so the `timeout` was effectively a total cap on generation) to `messages.stream`
(incremental reads, so the same `timeout` becomes a per-token *inactivity* limit): a call that keeps
emitting tokens runs as long as it needs; only a genuinely silent/stalled call fails, after
`resolve_llm_timeout()` seconds with no output. Total length is still bounded by `max_tokens`, so a
runaway never hangs either. Also drop the SDK's silent self-retry (`max_retries` 2 → 0) so a stall
can't compound into ~3×180s ≈ 9 min; a failure surfaces cleanly and the existing handlers cope
(selection→web safety net, relevance→fail-open, planner/synthesis→exit 4). Record/replay is
unaffected — streaming is internal to `complete`; the recorded string and request hash are unchanged.

This directly addresses the FOLLOW-UP left in STATE.md by the llm-call-deadline task ("improvable
later via streaming + inactivity timeout for true slow≠hung on LLM calls too").

## Acceptance criteria

Each one names the test that proves it.

1. `complete` consumes a streamed response and returns the assembled text — proven by
   `tests/unit/test_foundry.py::test_complete_streams_text_response`.
2. Tool-use (forced structured output) still returns canonical JSON from the final assembled
   message — proven by `tests/unit/test_foundry.py::test_complete_streams_tool_use_json`.
3. The SDK client is built with `max_retries=0` (no silent self-retry) and `timeout` =
   `resolve_llm_timeout()` (now an inactivity bound) — proven by
   `tests/unit/test_foundry.py::test_complete_disables_self_retry_and_sets_timeout`.
4. `resolve_llm_timeout` behaviour + request-hash stability are unchanged — existing
   `test_foundry.py::test_resolve_llm_timeout_*` and the eval fixtures stay green (make verify).

## Plan (before coding)

1. `foundry.py`: in `complete`, replace `client.messages.create(**kwargs)` with a
   `with client.messages.stream(**kwargs) as stream:` block that drives the event iterator to
   completion (each event is a read → resets the inactivity clock) then `stream.get_final_message()`;
   pass that message to the unchanged `_extract_text`. Build the client with `max_retries=0`. Update
   the docstring/comments to describe the inactivity (progress-based) semantics + max_tokens bound.
2. `tests/unit/test_foundry.py`: add a minimal fake `anthropic` module (injected via
   `sys.modules`) whose `AnthropicFoundry` captures construction kwargs and whose `messages.stream`
   returns a fake stream (iterable of events + `get_final_message`). Exercise `complete` for text and
   tool-use, and assert the construction kwargs. Remove the `# pragma: no cover` from `complete`.
3. `make verify` (+ confirm the decomposition eval stays 16/16).

## Failure analysis

<!-- MANDATORY when the same check fails 3x (doom-loop protocol). -->

## Done

Proof commit: sealed via `make push`   Auditor verdict: <pending>   Docs updated: STATE.md
