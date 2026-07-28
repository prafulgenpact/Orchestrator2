# Task: observability-cost-tokens

Status: DONE
Type: feature
Scope: src/orchestrator/llm/base.py, src/orchestrator/llm/foundry.py, src/orchestrator/llm/replay.py, src/orchestrator/observability.py, src/orchestrator/cli.py, tests/unit/test_foundry.py, tests/unit/test_observability.py, STATE.md
Phase: Observability — cost & token accounting (plan: ~/.claude/plans/i-need-to-build-validated-prism.md)

## Goal

Each run records the tokens it used and its dollar cost, rolled up per run and per model, so cost —
the #1 question for any LLM system — is finally visible and historical. Tokens are ground truth
from the API; cost is computed from a configurable price table (unknown models report tokens with
cost marked unpriced, never a fabricated number). Captured via a usage accumulator on the LLM
client (drained once at record time) — usage is NOT part of the request hash, so replay fixtures
and the decomposition eval (16/16) are untouched, and `complete()`'s return type is unchanged.

## Acceptance criteria

Each one names the test that proves it.

1. `_usage_from_message(msg, model)` maps an Anthropic message's usage into a `TokenUsage`
   (input/output/cache_read/cache_write, model), tolerating missing cache fields — proven by
   `tests/unit/test_foundry.py::test_usage_from_message`.
2. `FoundryClient` accumulates a `TokenUsage` per call and `drain_usage()` returns then clears them;
   `ReplayClient.drain_usage()` is `[]` and `RecordingClient` delegates — proven by
   `tests/unit/test_foundry.py::test_drain_usage_accumulates_and_clears`.
3. `cost_of(usage)` (observability) sums non-overlapping token buckets × per-model prices;
   an unknown model contributes 0 and is listed in `unpriced_models`; `ORCHESTRATOR_PRICES` (JSON
   path) overrides/extends the table — proven by
   `tests/unit/test_observability.py::test_cost_known_model`, `::test_cost_unknown_model`, and
   `::test_cost_price_override`.
4. A run record carries a `cost` block (`tokens`, `cost_usd`, `by_model`, `unpriced_models`);
   `runs.total_tokens`/`cost_usd` are persisted (with column migration) and included in `list_runs`
   and `kpis` (`cost`: total_usd, total_tokens, by_model) — proven by
   `::test_run_record_has_cost` and `::test_kpis_cost_aggregate`.
5. The CLI drains the client's usage at record time and passes it in; a normal replay run records
   zero cost without error — proven by the unchanged CLI tests + `::test_kpis_cost_aggregate`.
6. `make verify` PASS; decomposition eval unchanged at 16/16.
7. Live smoke (replay): `runs list --kpis` shows a Cost line (0 in replay); a synthetic run with
   usage shows real tokens + cost and per-model breakdown.

## Plan (before coding)

1. llm/base.py: add a frozen `TokenUsage` dataclass (+ `to_dict`).
2. llm/foundry.py: `_usage_from_message` (pure, testable); `FoundryClient` keeps `self._usage` and
   appends in `complete_stream`; `drain_usage()` returns dicts + clears.
3. llm/replay.py: `ReplayClient.drain_usage()` → `[]`; `RecordingClient.drain_usage()` delegates.
4. observability.py: `_DEFAULT_PRICES` (per-MTok, documented estimates) + `ORCHESTRATOR_PRICES`
   override; `cost_of(usage)`; `cost` block in `build_run_record(usage=...)`; add
   `input_tokens/output_tokens/total_tokens/cost_usd` columns (via `_ADDED_COLUMNS`) + summary cols;
   extend `kpis` with a `cost` aggregate; show cost in the KPI + run-detail renderers.
5. cli.py: after the run, `usage = client.drain_usage() if hasattr(...) else []`; pass to
   `record_run(..., usage=usage)` on both the execute and dry-run paths.
6. Tests (foundry usage/drain; observability cost/kpis/persistence) + STATE.md.

## Failure analysis

<!-- MANDATORY when the same check fails 3x (doom-loop protocol). -->

## Done

Proof commit: <sha>   Auditor verdict: <>   Docs updated: <>
