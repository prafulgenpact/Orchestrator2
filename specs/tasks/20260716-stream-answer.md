# Task: stream-answer

<!-- Fill Goal/Type/Scope/Acceptance BEFORE any code. This file IS the plan for
     this task; drift_check.py enforces the Scope line mechanically. -->

Status: DONE
Type: feature
Scope: src/orchestrator/llm/foundry.py, src/orchestrator/synthesis.py, src/orchestrator/render.py, src/orchestrator/cli.py, tests/unit/test_foundry.py, tests/unit/test_synthesis.py, tests/unit/test_render.py, tests/unit/test_cli.py
Phase: Phase 2 — UX (world-class): the answer appears as it is written, not all at once at the end

## Goal

The final answer streams to the user token-by-token (like a chat reply) instead of appearing only
after the whole run finishes. Reuses the streaming plumbing from progress-based-llm.

- `FoundryClient.complete_stream(request, on_delta)` streams text deltas to `on_delta` and returns
  the full assembled text; `complete` becomes `complete_stream(request, no-op)` (same inactivity
  bound + max_retries=0 as today — DRY, no behaviour change).
- `synthesize(..., on_delta=None)` feeds the answer to `on_delta`: on the LLM-fusion path it uses
  `complete_stream` when the client supports it (else falls back to `complete` + one whole-string
  emit); the pass-through modes (verbatim / final-step / none) emit their known answer once. Clients
  without `complete_stream` (Replay/Recording in tests/CI) transparently use the fallback, so
  determinism + fixtures are untouched.
- `render_execution(..., include_answer=False)` skips the Answer/Sources block so the CLI can print
  it itself (streamed) without duplication.
- CLI `--execute`: print "Answer:", stream the answer to stdout via `on_delta`, print Sources, then
  the rest via `render_execution(include_answer=False)`. Progress stays on stderr; `--json`/dry-run
  unchanged.

## Acceptance criteria

Each one names the test that proves it.

1. `complete_stream` emits text deltas in order and returns the assembled text; `complete` still
   returns the full text via the same path — `tests/unit/test_foundry.py::test_complete_stream_emits_deltas`.
2. `synthesize` on the fusion path streams deltas through `on_delta` when the client supports it,
   and falls back to a single emit otherwise —
   `tests/unit/test_synthesis.py::test_synthesize_streams_when_supported` and
   `::test_synthesize_falls_back_to_single_emit`.
3. `render_execution(include_answer=False)` omits the Answer/Sources block but keeps plan + results —
   `tests/unit/test_render.py::test_render_execution_can_omit_answer`.
4. CLI `--execute` streams the answer to stdout (answer text present, not duplicated) —
   `tests/unit/test_cli.py::test_execute_streams_answer_to_stdout`; existing execute tests stay green.
5. All existing tests + eval stay green (make verify; decomposition eval 16/16).

## Plan (before coding)

1. `foundry.py`: add `complete_stream` (iterate `stream.text_stream` → `on_delta`, then
   `get_final_message` → `_extract_text`); `complete` delegates with a no-op delta.
2. `synthesis.py`: add `on_delta` param + `_emit` helper; `_synthesize_llm` uses `complete_stream`
   when available.
3. `render.py`: add `include_answer: bool = True`; guard the Answer/Sources block.
4. `cli.py`: stream the answer in `main` (print header, on_delta→stdout, print sources), then
   `render_execution(include_answer=False)`.
5. Tests as named; then `make verify`.

## Failure analysis

<!-- MANDATORY when the same check fails 3x (doom-loop protocol). -->

## Done

Proof commit: sealed via `make push`   Auditor verdict: <pending>   Docs updated: STATE.md
