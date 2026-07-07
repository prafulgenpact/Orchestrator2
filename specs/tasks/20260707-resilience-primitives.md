# Task: resilience-primitives

<!-- Fill Goal/Type/Scope/Acceptance BEFORE any code. This file IS the plan for
     this task; drift_check.py enforces the Scope line mechanically. -->

Status: in progress
Type: feature
Scope: src/orchestrator/resilience.py, tests/unit/test_resilience.py, STATE.md
Phase: Phase 2 — invoke apps (plan-invoke-apps.md, capability block B: B1-B4)

## Goal

A fresh, dependency-light `resilience.py` gives the executor the AC-2 no-hang building blocks:
a hard wall-clock deadline (the real anti-hang guarantee — httpx timeouts are per-chunk, not
total), an error classifier (retry/fatal/auth), exponential backoff with jitter, a bounded
async-retry helper that retries only transient errors, and a per-key circuit breaker so a dead
app is skipped rather than hammered.

## Acceptance criteria

Each one names the test that proves it.

1. B1 wall-clock deadline: `run_with_deadline` returns fast ops and raises `DeadlineExceeded` on
   a hung op within the timeout — proven by
   `tests/unit/test_resilience.py::test_deadline_fires_on_hang` and `::test_deadline_returns_value`.
2. B2 classifier: `classify_error` returns auth for 401/403, retry for timeouts/conn/5xx/408/429,
   fatal for 4xx and ValueError/TypeError/KeyError — proven by
   `tests/unit/test_resilience.py::test_classify_*`.
3. B3 backoff: `backoff_delay` grows exponentially and stays within the jitter band; `retry_async`
   retries only transient errors, respects `transient_max`, and re-raises fatal/auth immediately —
   proven by `tests/unit/test_resilience.py::test_backoff_*` and `::test_retry_async_*`.
4. B4 circuit breaker: `CircuitBreaker` opens after N consecutive failures, resets on success —
   proven by `tests/unit/test_resilience.py::test_circuit_breaker_*`.
5. `make verify` PASS (>=90% coverage; new module fully covered; e2e replay still green).

## Plan (before coding)

1. New `src/orchestrator/resilience.py` (stdlib only; asyncio + random): `DeadlineExceeded`,
   `run_with_deadline`, `classify_error` (duck-types HTTP status via `exc.response.status_code` /
   `exc.status_code`, no httpx import), `backoff_delay`, `retry_async` (injectable `sleep`),
   `CircuitBreaker`.
2. New `tests/unit/test_resilience.py` — drive async code via `asyncio.run` (no pytest-asyncio);
   inject a fake sleep so no test actually waits; cover every branch.
3. `make verify` green; update STATE.md; mark task Done with the sealed proof.

## Failure analysis

<!-- MANDATORY when the same check fails 3x (doom-loop protocol). -->

## Done

All 5 acceptance criteria met. `make verify` PASS — new `resilience.py` at 100% coverage
(158 unit tests total; e2e replay still green). Provides `run_with_deadline` (hard wall-clock
cap — the AC-2 anti-hang guarantee), `classify_error`, `backoff_delay`, `retry_async`
(transient-only, bounded, injectable sleep), and `CircuitBreaker`. Kept decoupled from the
registry (takes plain numbers, not RetrySpec) so it stays pure and testable.

Proof commit: auto-sealed by `make verify` (AUTOSEAL) on branch Orchestrator2   Auditor verdict: (not yet run)   Docs updated: yes
