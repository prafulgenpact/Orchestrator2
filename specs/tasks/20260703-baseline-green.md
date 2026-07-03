# Task: baseline-green

Status: DONE
Type: chore
Scope: verify.config, pyproject.toml, tests/**
Phase: Phase 1 (walking skeleton) — establishes the green baseline it builds on

## Goal

Make `make verify` produce a PASS proof on the freshly scaffolded project, so the
first real feature starts from a sealed, green baseline instead of a red one. Fixes
the wizard/scaffold artifacts that make verification fail out of the box.

## Acceptance criteria

Each one names the check that proves it (all in `proofs/latest.json`).

1. py-unit runs (no `--cov-fail-under` crash) and passes ≥90% — proven by the `py-unit` check going green.
2. py-lint and py-format pass — proven by the `py-lint` / `py-format` checks going green.
3. dep-audit passes with the low-severity pytest CVE accepted+documented — proven by the `dep-audit` check going green.
4. Overall proof result is PASS and auto-sealed — proven by `proofs/latest.json` `"result": "PASS"`.

## Plan (before coding)

1. `verify.config`: `COVERAGE_MIN=90%` → `90` (the `%` crashes `pytest --cov-fail-under`).
2. `verify.config`: accept GHSA-6w46-j5rx-g56g via `DEP_AUDIT_ARGS` (documented; fix needs a pytest 8→9 major bump).
3. `pyproject.toml`: `extend-exclude=["scripts"]` + `force-exclude=true` — vendored harness tooling is not this project's code; lint only src/ + tests/.
4. `ruff --fix`/`format` the 2 remaining issues in tests/ (my code).
5. Commit the initial scaffold + fixes, then `make verify` → PASS → auto-seal.

## Failure analysis

<!-- none yet -->

## Done

Proof commit: dbb04d8 (verified 22796a8, fingerprint 87eb21cfc27d)   Auditor verdict: n-a   Docs updated: yes (STATE.md)
