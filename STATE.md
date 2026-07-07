# Project State — A multi agent orchestrator system calling relevant apps basis intent recognition

Last updated: 2026-07-07 (resilience-primitives task)

## Done (most recent first)

- 2026-07-07 resilience-primitives (Phase 2, B1-B4): new `resilience.py` — `run_with_deadline` (hard wall-clock cap via asyncio.wait_for = the AC-2 anti-hang guarantee), `classify_error` (retry/fatal/auth, duck-types HTTP status), `backoff_delay` (exponential + jitter), `retry_async` (bounded, transient-only, injectable sleep), and `CircuitBreaker`. Decoupled from the registry (plain numbers, not RetrySpec). 40 new unit tests, 100% coverage. make verify PASS.
- 2026-07-07 app-contracts-registry (Phase 2, A1+A2): the registry now carries a real, source-derived HTTP call-spec per non-fallback app — `port`, `health`, and `operations` (method/path/timeout/retry/destructive/idempotency/request_fields). Contracts for all 11 apps (44 operations) were derived from each backend + the live launcher, not guessed; `to_prompt_dict` is unchanged so the Phase-1 e2e fixture still replays. make verify PASS (118 unit tests, 100% coverage).
- 2026-07-06 dry-run-orchestrator: `python -m orchestrator "task"` recognizes intent, decomposes into a subtask DAG (parallel/sequential), and reports the app per subtask with rationale/confidence — dry run, no invocation. 12 src modules, 93 unit tests + 2 e2e replay scenarios, 100% coverage. Completes the Phase-1 walking slice of AC-1.
- 2026-07-03 baseline-green: fixed scaffold artifacts (COVERAGE_MIN `90%`→`90`, accepted low-severity pytest CVE, excluded vendored scripts/ from ruff), first PASS proof sealed (commit 22796a8, proof dbb04d8)
- 2026-07-03 project initialized: objective written (4 ACs), e2e kit installed (agent)

## In progress

- (nothing yet)

## Next up

- Phase 2 continue (see plan-invoke-apps.md): C app-caller (health/cold-start + single grounded HTTP call, composing resilience.py), D executor (DAG waves, budget, partial results, web fallback), E grounded synthesis + verbatim voice (AC-4), F trace/observability, G CLI --execute + hermetic e2e.

## Known issues / parked

- (none)

## Key decisions

- 2026-07-03 — scaffold + verification contract adopted (see PLAYBOOK.md)
- 2026-07-07 — invocation approach: orchestrator calls each app directly over its existing FastAPI HTTP API (native tool-use), not MCP; build fresh (no code reused from prior attempts). Ports are launcher-assigned (8001–8011); the executor confirms the live port via the launcher + health at call time (blogs/research self-declare 8787/8789 standalone). See plan-invoke-apps.md.
