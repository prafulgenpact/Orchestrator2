# Task: expose-all-capabilities

Status: DONE
Type: feature
Scope: registry/apps.json, tests/unit/**, tests/eval/fixtures/**, tests/e2e/fixtures/**, STATE.md
Phase: Phase 2 — capability coverage (wire every non-internal app endpoint)

## Goal

Every non-internal, non-streaming endpoint of all 11 apps is exposed to the orchestrator as a
registry operation, generated directly from each app's live OpenAPI (accurate method/path/fields),
and validated by the contract guardrail. Streaming (SSE) and WebSocket endpoints are explicitly
deferred to follow-on tasks because they need new transport code, not just wiring.

## Acceptance criteria

1. Every non-internal, non-SSE endpoint in each app's committed snapshot is wired — proven by
   `tests/unit/test_registry_coverage.py::test_all_non_streaming_endpoints_wired`.
2. Every wired op matches the live API — proven by the existing
   `tests/unit/test_api_contract.py` (0 mismatches).
3. `make verify` passes; decomposition eval stays 16/16 (app-level routing unaffected).

## Plan (before coding)

1. Generator (scratchpad, one-off) reads each app's snapshot + live OpenAPI summaries, builds op
   dicts for every endpoint that is NOT: internal (health/root/docs/SPA), already wired, SSE, or WS.
   Fields from the schema; description from the OpenAPI summary; DELETE => destructive; GET =>
   idempotency supported + retry, others none; heavy paths (train/generate/research/compare/analyze)
   => longer timeout. Appends to each app's `operations` in apps.json.
2. Add `tests/unit/test_registry_coverage.py` asserting no non-streaming endpoint is left unwired
   (the coverage ratchet — this is what "all exposed" means, tested).
3. Refresh not needed (snapshots current). Run contract test + coverage test + eval + verify;
   fix any grounding/eval regressions.

## Deferred (follow-on tasks, need transport code)

- SSE: github `chat/{repo,code,cross-repo}`, `build/suggest`, `compare/`; blogs `generate/streaming`;
  research `stream/{run_id}`, `runs/{run_id}/events`.
- WebSocket: coding-playground `WS /api/kernel/ws` (live kernel, matplotlib PNG).

## Failure analysis

## Done

Registry 53 -> 207 ops (+154). Every non-internal, non-streaming endpoint of all 11 apps wired +
proven by the coverage ratchet; all pass the contract guardrail. `make verify` PASS; eval 16/16.
Remaining: 8 SSE/WS endpoints (deferred to transport follow-on tasks).

Proof commit: <this commit>   Auditor verdict: <pending>   Docs updated: STATE.md
