# Task: api-contract-guardrail

Status: DONE
Type: feature
Scope: src/orchestrator/**, tools/**, tests/unit/**, tests/contract/**, registry/apps.json, tests/eval/fixtures/**, tests/e2e/fixtures/**, STATE.md
Phase: Phase 2 — capability coverage (guardrail #8: registry vs live app APIs)

## Goal

Wiring a registry op with a wrong method, path, or field name becomes impossible to seal. A
deterministic contract test asserts every registry operation maps to a real endpoint on its app —
validated against committed OpenAPI snapshots, so it runs offline in CI (via `py-unit`, already in
`make verify`) with no enforcement-layer edit. A refresh tool re-fetches live `/openapi.json` to
update the snapshots (the live-reconciliation moment, same pattern as fixture re-recording).

## Acceptance criteria

Each one names the test that proves it.

1. Every registry op (method + path) exists in its app's committed OpenAPI snapshot — proven by
   `tests/unit/test_api_contract.py::test_every_op_path_and_method_exists`.
2. Every registry op's `required_fields` and `request_fields` are real params/body fields of that
   endpoint (catches typos / stale fields) — proven by
   `tests/unit/test_api_contract.py::test_op_fields_exist_in_schema`.
3. A registry op with a bogus path/method/field fails the contract test (the guardrail actually
   bites) — proven by `tests/unit/test_api_contract.py::test_bogus_op_is_rejected` (uses a synthetic
   op + snapshot fixture, not the real registry).
4. `make verify` passes with the new test green; decomposition eval stays 16/16.

## Plan (before coding)

1. `tests/contract/openapi/<app_id>.json` — committed SLIM snapshots per non-fallback app, shape:
   `{ "<path>": { "<METHOD>": { "params": [...], "required": [...] } } }`. Derived from each app's
   live `/openapi.json` (path params + query params + requestBody `$ref` properties, with the
   `required` set resolved from the component schema). Keeps diffs small + reviewable.
2. `tools/refresh_openapi.py` (NOT in scripts/ — enforcement layer is off-limits) — fetches each
   app's live `/openapi.json` (base URL via registry `port`, reusing the resolve pattern), writes
   the slim snapshot. Unreachable app → skip + warn, keep existing snapshot. Run: `python -m
   tools.refresh_openapi`.
3. `src/orchestrator/contract.py` — pure helpers: `load_snapshot(path)`, and
   `check_op(op, snapshot) -> list[str]` returning human-readable mismatches (missing path, wrong
   method, unknown field). Pure + I/O-free core so it is fully unit-testable.
4. `tests/unit/test_api_contract.py`:
   - parametrized over the real registry × snapshots: assert 0 mismatches (criteria 1–2). Apps with
     no snapshot committed SKIP (never error) — same philosophy as the eval's missing-fixture skip.
   - a self-contained negative test with a synthetic op + tiny snapshot proving a bogus op is caught
     (criterion 3), so the guardrail's teeth are proven without depending on a live app.
5. Seed snapshots for the apps reachable now (8001,8003,8004,8005,8007,8008,8011); note which are
   down (8002,8006,8009,8010) as SKIP so it is explicit, not silent.
6. `make verify`; confirm eval 16/16.

## Design notes / decisions

- **Why snapshots, not live-at-verify:** CI / the sealed proof must be deterministic and offline.
  Snapshots make the check reproducible; `refresh_openapi` is the deliberate step that reconciles
  with live reality and surfaces real API drift as a reviewable snapshot diff.
- **Why a unit test, not a `verify.sh` step:** rule 8 forbids touching the enforcement layer.
  `py-unit` already runs `tests/unit`, so a test file is enforced automatically — no Makefile edit.
- **Skip-when-missing** keeps the build green before a snapshot exists (bootstrap), exactly like the
  decomposition eval skips a case with no fixture. Coverage grows as snapshots are added.
- Slim snapshots (not raw openapi) keep the committed footprint small and the diffs readable.

## Drift found on first run (the guardrail working as intended)

The contract test caught 2 real registry mismatches record/replay never could:
- `teach-me.create_topic` and `teach-me.send_user_message` declared a `request_fields` entry `model`
  that the teach-me API does not accept (TopicCreate={title}, MessageCreate={content}). It was a
  hint-only field (not required), silently ignored by the app. Removed both — the contract test is
  the failing-test-first (rule 5). Scope widened to `registry/apps.json` (+ fixtures, in case the
  edit re-keys them).
- (A third flag, `research-assistant.upload_corpus_document` field `file`, was a false positive from
  the extractor ignoring `multipart/form-data` bodies — fixed in `contract.py`, not a registry bug.)

## Failure analysis

## Done

All 4 acceptance criteria met; `make verify` PASS (see `proofs/latest.json`); decomposition eval
16/16; unit 379→488. Guardrail caught + fixed 2 real registry-drift fields on first run. Snapshots
committed for all 11 apps.

Proof commit: <this commit>   Auditor verdict: <pending>   Docs updated: STATE.md
