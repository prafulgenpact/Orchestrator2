# Task: slice1-live-call

<!-- Fill Goal/Type/Scope/Acceptance BEFORE any code. This file IS the plan for
     this task; drift_check.py enforces the Scope line mechanically. -->

Status: in progress
Type: feature
Scope: src/orchestrator/app_caller.py, src/orchestrator/selector.py, src/orchestrator/executor.py, src/orchestrator/models.py, src/orchestrator/render.py, src/orchestrator/cli.py, src/orchestrator/prompts/operation_select_system.md, tests/unit/test_app_caller.py, tests/unit/test_selector.py, tests/unit/test_executor.py, tests/unit/test_cli.py, tests/unit/test_render.py, tests/unit/test_models.py, pyproject.toml, requirements-dev.txt, STATE.md, plan-slice1-first-live-call.md
Phase: Phase 2 — invoke apps (plan-slice1-first-live-call.md; thinnest end-to-end slice)

## Goal

`python -m orchestrator --execute "<task>"` runs the full loop: plan -> for each subtask pick the
app operation + arguments -> call the REAL app over HTTP (with block-B no-hang safety) -> return
the app's real output, attributed to its source. Dry-run stays the default so the sealed Phase-1
behaviour is untouched. Proves the hardest bridge (actually calling a live app) end-to-end.

## Acceptance criteria

Each one names the test that proves it.

1. app-caller makes a real HTTP call and returns a grounded result; times out cleanly on a hang;
   circuit-breaker skips a repeatedly-failing app — proven by `tests/unit/test_app_caller.py`
   (httpx MockTransport; `::test_call_success`, `::test_call_times_out`, `::test_breaker_skips`).
2. selector turns (app operations + subtask) into a validated {operation, arguments}, grounded in
   the app's real operations — proven by `tests/unit/test_selector.py`.
3. executor runs a plan's subtasks, calls each app, collects PlanResult, skips the fallback, and
   isolates one subtask's failure — proven by `tests/unit/test_executor.py`.
4. `--execute` renders per-subtask app + real result + source; dry-run unchanged — proven by
   `tests/unit/test_cli.py` and `tests/unit/test_render.py`.
5. `make verify` PASS (>=90% coverage; e2e replay still green; dep-audit clean with httpx added).

## Plan (before coding)

1. Add `httpx` to pyproject dependencies + requirements-dev.txt (already installed 0.28.1).
2. `models.py`: `SubtaskResult` + `PlanResult` (frozen).
3. `app_caller.py`: resolve live base_url (launcher `/api/apps`, fall back to registry port),
   health-check, one HTTP call wrapped in resilience (deadline + retry + circuit breaker); returns
   a `CallResult` (never raises). httpx.AsyncClient injected for hermetic tests (MockTransport).
4. `selector.py` + `prompts/operation_select_system.md`: one structured LLM call -> {operation,
   arguments}; validate operation exists, args grounded in request_fields.
5. `executor.py`: run subtasks in dependency order; select+call each; fallback skipped (deferred);
   per-run CircuitBreaker; per-call deadline is the anti-hang.
6. `cli.py` `--execute` (asyncio.run the executor) + `render.py` render_execution.
7. Unit tests for every module (hermetic: MockTransport + FakeLLM). `make verify` green; update
   STATE.md; mark Done with the sealed proof.

## Deferred (later slices)

Multi-app synthesis + voice (E), observability/trace (F), web-search fallback execution, launcher
cold-start/auto-start, the trickier apps (WebSocket kernel, SSE, async-poll), full-loop hermetic
e2e (needs app-HTTP record/replay).

## Failure analysis

<!-- MANDATORY when the same check fails 3x (doom-loop protocol). -->

## Done

All 5 acceptance criteria met. `make verify` PASS — 198 unit tests, 100% coverage, e2e replay
green (planner request unchanged). New modules: app_caller (health-check + block-B deadline/retry/
circuit-breaker HTTP call), selector (grounded operation+args LLM call), executor (per-subtask run,
fallback skipped, failures isolated); PlanResult/SubtaskResult; render_execution; `--execute` flag
(dry-run stays default); httpx added as a dependency.

**Verified LIVE end-to-end:** `python -m orchestrator --execute "find recent papers on
mixture-of-experts"` planned → selected `search_papers_by_query` → called the real arXiv app
(:8002) → returned real papers with the source URL in ~3.2s. No hang; fully grounded.

Proof commit: auto-sealed by `make verify` (AUTOSEAL) on branch Orchestrator2   Auditor verdict: (not yet run)   Docs updated: yes
