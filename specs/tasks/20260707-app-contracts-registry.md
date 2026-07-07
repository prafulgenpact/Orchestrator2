# Task: app-contracts-registry

<!-- Fill Goal/Type/Scope/Acceptance BEFORE any code. This file IS the plan for
     this task; drift_check.py enforces the Scope line mechanically. -->

Status: DONE
Type: feature
Scope: src/orchestrator/registry.py, registry/apps.json, tests/unit/test_registry.py, plan-invoke-apps.md, STATE.md
Phase: Phase 2 — invoke apps (plan-invoke-apps.md, capabilities A1 + A2)

## Goal

The registry carries, per non-fallback app, an accurate machine-readable call-spec so a later
executor can invoke it over HTTP: an app-level `port` + `health` path, plus one or more
`operations` (each with `method`, `path`, `timeout_s`, `retry`, `destructive`, `idempotency`,
and the notable `request_fields`). Contracts are derived from each app's real backend
(OpenAPI/source), never guessed. The planner-facing view (`to_prompt_dict`) is unchanged, so the
sealed Phase-1 planner request hash and e2e replay fixture stay valid.

## Acceptance criteria

Each one names the test that proves it.

1. `AppEntry` exposes `port`, `health`, `operations` (tuple of `AppOperation`) with a `RetrySpec`;
   the loader parses and validates them — proven by
   `tests/unit/test_registry.py::test_operation_fields_parsed` and error-branch tests.
2. Non-fallback apps MUST have `port`, `health`, and >=1 valid operation; the fallback MUST NOT
   declare operations — proven by
   `tests/unit/test_registry.py::test_non_fallback_requires_call_spec` and
   `::test_fallback_must_not_declare_operations`.
3. `to_prompt_dict()` still returns exactly the 6 planner keys (no call-spec leakage) — proven by
   the existing `tests/unit/test_registry.py::test_to_prompt_dict_is_compact`.
4. The shipped `registry/apps.json` gives every one of the 11 non-fallback apps a complete,
   real call-spec — proven by `tests/unit/test_registry.py::test_real_registry_call_specs_complete`.
5. The sealed e2e replay still passes (planner request unchanged) — proven by
   `tests/e2e/test_scenarios.py` under `make verify`.

## Plan (before coding)

1. Add `RetrySpec`, `AppOperation` frozen dataclasses; extend `AppEntry` with `port`, `health`,
   `operations` (defaults `None/None/()`, appended after existing positional fields).
2. Extend the loader: parse/validate operations + app-level fields; enforce the non-fallback
   completeness rule and the fallback exclusion rule; keep `to_prompt_dict` unchanged.
3. Populate `registry/apps.json` for all 11 apps with contracts derived from each backend's
   OpenAPI/source (arxiv anchored to the live `:8002/openapi.json`).
4. Update/extend `tests/unit/test_registry.py`: enrich the synthetic apps for existing
   error-branch tests, add new tests for the operation schema, completeness rules, and a
   real-registry completeness check. Keep >=90% coverage.
5. `make verify` green; update STATE.md; mark this task Done with the proof commit.

## Failure analysis

<!-- MANDATORY when the same check fails 3x (doom-loop protocol). -->

## Done

All 5 acceptance criteria met. `make verify` PASS — lint, format, types, unit (118 tests, 100%
coverage), e2e replay (2 scenarios, planner request hash unchanged), secrets, gitleaks, dep-audit,
diff-cover all green. Registry now carries real, source-derived call-specs for all 11 apps
(44 operations); `to_prompt_dict` unchanged so Phase-1 fixture still replays.

Proof commit: auto-sealed by `make verify` (AUTOSEAL) on branch Orchestrator2   Auditor verdict: (not yet run)   Docs updated: yes
