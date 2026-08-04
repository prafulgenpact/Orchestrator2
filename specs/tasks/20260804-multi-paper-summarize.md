# Task: multi-paper-summarize

Status: Done
Type: feature
Scope: src/orchestrator/registry.py, src/orchestrator/executor.py, registry/apps.json, tests/unit/test_registry.py, tests/unit/test_executor.py, STATE.md
Phase: Phase 2 — executor

## Goal (fix 4 of the RCA set)

"Summarize the papers" must cover more than one. ArXiv's `analyze_paper` is single-paper and the
executor runs one op per subtask, so a summarize step analyzed only 1 of the found papers. Add a
contract-driven fan-out: when an op declares `fan_out`, the executor calls it once per top-N item
from upstream (the found papers) and aggregates the analyses into one result.

## Acceptance criteria

1. `AppOperation.fan_out` parses from the contract (arg/source/max, optional title_from; validated)
   and round-trips — unit-tested in test_registry.
2. When a subtask's op has `fan_out` and upstream carries a list of items, the executor calls the op
   once per id (top `max`, deduped, reusing the call cache) and returns ONE `ok` SubtaskResult whose
   output is a list of per-paper entries (`title`/`arxiv_id`/`content`) — unit-tested end-to-end
   with the HTTP call stubbed (assert N calls, aggregated output). Fewer than 2 ids -> single call
   path unchanged.
3. `registry/apps.json`: `analyze_paper` carries `fan_out: {arg: arxiv_id, source: arxiv_id,
   title_from: title, max: 3}`.
4. `make verify` PASS; decomposition eval unchanged (routing untouched). Live: a find+summarize task
   yields a summarize card covering multiple papers.

## Plan

- registry.py: `fan_out: dict | None` + `_parse_fan_out` (validate arg/source str, max int>=1,
  title_from optional str) + wire + to_dict.
- executor.py: in `_run_app_op`, after the required-field check, if `op.fan_out` and upstream yields
  >=2 ids, run `_run_fan_out` (loop `_call_cached` over ids; aggregate to a paper-shaped list so the
  existing UI renders each as a titled markdown summary). Non-poll only.
- apps.json: add the `fan_out` spec to `analyze_paper`.

## Done

Proof commit: (this commit)   Proof fingerprint: 4c3766de1b6f   Auditor verdict: <pending>   Docs updated: STATE.md

Live-verified: "find + summarize CLT papers" -> search found 10, summarize (fan-out) covered 3 papers, each with title + arxiv_id + a real summary (was 1).
