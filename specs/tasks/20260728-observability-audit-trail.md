# Task: observability-audit-trail

Status: DONE
Type: feature
Scope: src/orchestrator/observability.py, tests/unit/test_observability.py, STATE.md
Phase: Observability Step B (part 1) — tamper-evidence + redaction (plan: ~/.claude/plans/i-need-to-build-validated-prism.md)

## Goal

The saved audit trail becomes defensible: (1) the append-only event log is a hash chain, so any
later edit or deletion of a past record is detectable; (2) secrets (API keys, bearer tokens,
emails) are masked before anything is written to disk, so run data can be kept without storing
credentials. Both live entirely in observability.py — no LLM-path change — so eval stays 16/16.
(Accurate cost/token capture needs an LLMClient contract change and is a separate follow-up task.)

## Acceptance criteria

Each one names the test that proves it.

1. Each `logs/events.jsonl` line carries `seq` (incrementing), `prev_hash`, and
   `hash = sha256(prev_hash + seq + canonical(payload))`; the first line chains from a fixed
   genesis hash — proven by `tests/unit/test_observability.py::test_event_chain_links`.
2. `verify_chain(root)` returns `(True, None)` for an intact log and `(False, <seq>)` when a past
   line is edited or deleted — proven by `::test_verify_chain_detects_tamper` and
   `::test_verify_chain_detects_deletion`.
3. `redact(...)` masks emails, `sk-` keys, `AKIA` keys, and bearer tokens inside nested
   dicts/lists/strings, leaving other text intact — proven by `::test_redact_masks_secrets`.
4. A saved run's JSON and event line contain no unmasked secret that was present in a step's
   output/args; redaction can be disabled via `ORCHESTRATOR_OBS_REDACT=0` — proven by
   `::test_saved_run_is_redacted` and `::test_redaction_can_be_disabled`.
5. `make verify` PASS; decomposition eval unchanged at 16/16.
6. Live: save two runs, hand-edit the first event line, and `verify_chain` reports the break at
   that seq; a run whose output embeds a fake `sk-...` key is stored masked.

## Plan (before coding)

1. observability.py — tamper-evidence:
   - `_GENESIS_HASH`, `_canonical(obj)` (json sort_keys, compact, default=str),
     `_chain_hash(prev_hash, seq, payload)` (sha256).
   - `_append_event`: read the last line to get `(seq, hash)`; write a line
     `{seq, prev_hash, hash, **payload}` chained from it (genesis if the file is empty/missing).
   - `verify_chain(root)`: recompute each line's hash from its predecessor; return `(ok, broken_seq)`.
2. observability.py — redaction:
   - `redact(value)` recurses dict/list/str; `_redact_str` applies a small regex pack
     (email, `sk-[A-Za-z0-9_-]{16,}`, `AKIA[0-9A-Z]{16}`, `(?i)bearer\s+\S+`) → `[REDACTED]`.
   - `_redaction_enabled()` reads `ORCHESTRATOR_OBS_REDACT` (default on).
   - `save_run`: write the redacted record to the JSON + event sinks (DB stores only summary fields,
     no raw content, so it is unaffected).
3. Tests in test_observability.py (offline, tmp_path).
4. STATE.md: record the task; note the cost/token follow-up.

## Failure analysis

<!-- MANDATORY when the same check fails 3x (doom-loop protocol). -->

## Done

Proof commit: <sha>   Auditor verdict: <>   Docs updated: <>
