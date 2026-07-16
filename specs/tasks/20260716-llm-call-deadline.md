# Task: llm-call-deadline

<!-- Fill Goal/Type/Scope/Acceptance BEFORE any code. This file IS the plan for
     this task; drift_check.py enforces the Scope line mechanically. -->

Status: in progress
Type: bugfix
Scope: src/orchestrator/**, tests/unit/**, registry/**
Phase: Phase 2 — accuracy/robustness (AC-2: nothing may hang)

<!-- Scope includes registry/** because this working tree also carries the prior, still-uncommitted
     reduce-unwarranted-web-fallbacks changes (async required_fields + Teach Me timeouts) that the
     human is reviewing together with this fix as one unit. -->


## Goal

Every live LLM/Foundry call is bounded by a hard, env-tunable per-request timeout, so a stalled
Foundry request fails within seconds→minutes (raising LLMError) instead of hanging the whole run
indefinitely. AC-2 ("nothing may hang") previously covered app HTTP calls and the async poll loop
but NOT the LLM calls (planner / selector / relevance / synthesis), which called the SDK with no
explicit wall-clock bound — a real run was observed blocked ~86 min at 0% CPU on a wedged call.

Before: `FoundryClient.complete` built the client with only `max_retries=2`; a stalled request
relied on the SDK's very long default timeout (~10 min/attempt × retries), i.e. effectively a hang.
After: the client is built with an explicit `timeout=resolve_llm_timeout()` (default 180 s,
override `ORCHESTRATOR_LLM_TIMEOUT_S`); a stall raises, which the existing handlers turn into a
clean outcome — selection→web safety net, relevance→fail-open, planner/synthesis→clean exit 4.

## Acceptance criteria

Each one names the test that proves it.

1. `resolve_llm_timeout()` returns the default when the env var is unset/blank/non-numeric/≤0, and
   the overridden value otherwise — proven by
   `tests/unit/test_foundry.py::test_resolve_llm_timeout_default` and
   `::test_resolve_llm_timeout_override` and `::test_resolve_llm_timeout_rejects_bad_values`.
2. The timeout is independent of model/credential resolution, so request hashing (record/replay) is
   unaffected — no fixtures re-recorded; existing foundry + eval tests stay green (make verify).

## Plan (before coding)

1. `foundry.py`: add `DEFAULT_LLM_TIMEOUT_S` + `resolve_llm_timeout()`; pass `timeout=` into the
   `AnthropicFoundry(...)` construction in `complete()` (the network line stays `# pragma: no cover`).
2. `tests/unit/test_foundry.py`: unit-test `resolve_llm_timeout` (default / override / bad values).
3. `make verify`.

## Failure analysis

<!-- MANDATORY when the same check fails 3x (doom-loop protocol). -->

## Done

Proof commit: <sha>   Auditor verdict: <ON_TRACK/...>   Docs updated: yes/no/n-a
