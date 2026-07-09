# Project State — A multi agent orchestrator system calling relevant apps basis intent recognition

Last updated: 2026-07-09 (synthesis-voice task)

## Done (most recent first)

- 2026-07-09 synthesis-voice (Phase 2, depth — plan-depth-orchestration.md Task 2; serves AC-4):
  `--execute` now ends with ONE grounded answer on top (an "Answer" section) instead of only a
  list of per-app blobs. New `synthesis.py` + `synthesis_system.md`: collects the successful
  results and either (a) passes a lone prose answer through VERBATIM — preserving the app's own
  voice tuning, no LLM call — or (b) fuses several results into one answer via a single grounded
  LLM call that uses ONLY those results. Sources are collected in code (never from the model), so
  provenance holds. `render_execution` grew an optional `synthesis` arg (Answer + Sources above the
  plan/results); the CLI calls `synthesize` after `execute_plan`. New test_synthesis.py + render/cli
  tests; 239 unit tests, 100% coverage; make verify PASS.
- 2026-07-09 env-local-resolution (Phase 2, tooling — enables live `--execute`): credentials now
  auto-resolve from a project-local `.env` at the repo root (gitignored), so live runs work with no
  `ORCHESTRATOR_FALLBACK_ENV` export. Precedence: process env → project `.env` → sibling
  `Blogs Playground/backend/.env`. An explicit `ORCHESTRATOR_FALLBACK_ENV` still wins and stays the
  sole fallback (opt-out preserved), so all prior tests (which set it) are unaffected. 3 new
  regression tests in test_foundry.py; make verify PASS.
- 2026-07-08 app-caller-timeout (Phase 2, bugfix — serves AC-2; unblocks the depth demo): long,
  legitimately-slow app operations (e.g. arXiv `analyze_paper`, LLM-backed, 90s registry budget)
  were failing after ~5s with a bare `fatal:`. Root cause: `call_operation` set a 90s HARD outer
  deadline via `run_with_deadline` but never passed a per-read `timeout` to httpx, so httpx's 5s
  default fired first (`ReadTimeout('')`). Fix: pass `timeout=op.timeout_s` to the httpx request
  (outer deadline stays the hard anti-hang cap); and render `type(exc).__name__` when the
  exception message is empty. Failing-test-first: 2 new regression tests in test_app_caller.py.
  make verify PASS. VERIFIED LIVE: the MoE demo now runs end-to-end — step 2 analyzes step 1's
  paper (2402.14800) and returns real takeaways.
- 2026-07-08 depth-data-flow (Phase 2, depth — plan-depth-orchestration.md Task 1): the executor
  now threads data **between** steps. Each subtask's operation+arguments are selected WITH the
  outputs of the subtasks it depends on (only successful upstream flows forward), so step 2 can
  lift an id (e.g. an arXiv id) out of step 1's result. `select_operation`/`build_select_message`
  gained an `upstream` param that renders an "UPSTREAM RESULTS" block preserving ids;
  operation_select prompt bumped to v2. This is the leap from N independent calls to a real chain.
  New unit tests in test_selector.py + test_executor.py; make verify PASS (e2e replay unchanged).
- 2026-07-08 relevance-and-list (Phase 2, accuracy): `--execute` now (1) lists all results (count + top titles; full payload behind `--verbose`) and (2) runs a relevance guard (`grounding.check_relevance`, one LLM call) after each successful call — irrelevant results become "no relevant results found — <reason>" with the raw output suppressed. New grounding.py + relevance_system.md; executor + render updated. 217 unit tests, 100% coverage; make verify PASS. Live-verified (MoE lists papers; junk topics filtered/flagged).
- 2026-07-07 execute-clean-output (Phase 2, UX): `--execute` now prints a clean three-part view — input (task + intent), decomposition (subtasks in steps, each with chosen app + confidence + rationale), and output (grounded result + source). Operational detail (operation, status, timing, full payload) moved behind a new `--verbose` flag. 201 unit tests, 100% coverage; make verify PASS.
- 2026-07-07 slice1-live-call (Phase 2, thinnest end-to-end): `python -m orchestrator --execute "<task>"` now runs the full loop — plan → per-subtask operation+args selection (grounded LLM call) → real HTTP call via the app-caller (health-check + block-B deadline/retry/circuit-breaker) → grounded result with source URL. New app_caller.py, selector.py, executor.py; PlanResult/SubtaskResult; render_execution; `--execute` (dry-run stays default); httpx dependency. VERIFIED LIVE against the running arXiv app (real MoE paper returned in ~3s). 198 unit tests, 100% coverage; e2e replay unchanged. make verify PASS.
- 2026-07-07 resilience-primitives (Phase 2, B1-B4): new `resilience.py` — `run_with_deadline` (hard wall-clock cap via asyncio.wait_for = the AC-2 anti-hang guarantee), `classify_error` (retry/fatal/auth, duck-types HTTP status), `backoff_delay` (exponential + jitter), `retry_async` (bounded, transient-only, injectable sleep), and `CircuitBreaker`. Decoupled from the registry (plain numbers, not RetrySpec). 40 new unit tests, 100% coverage. make verify PASS.
- 2026-07-07 app-contracts-registry (Phase 2, A1+A2): the registry now carries a real, source-derived HTTP call-spec per non-fallback app — `port`, `health`, and `operations` (method/path/timeout/retry/destructive/idempotency/request_fields). Contracts for all 11 apps (44 operations) were derived from each backend + the live launcher, not guessed; `to_prompt_dict` is unchanged so the Phase-1 e2e fixture still replays. make verify PASS (118 unit tests, 100% coverage).
- 2026-07-06 dry-run-orchestrator: `python -m orchestrator "task"` recognizes intent, decomposes into a subtask DAG (parallel/sequential), and reports the app per subtask with rationale/confidence — dry run, no invocation. 12 src modules, 93 unit tests + 2 e2e replay scenarios, 100% coverage. Completes the Phase-1 walking slice of AC-1.
- 2026-07-03 baseline-green: fixed scaffold artifacts (COVERAGE_MIN `90%`→`90`, accepted low-severity pytest CVE, excluded vendored scripts/ from ruff), first PASS proof sealed (commit 22796a8, proof dbb04d8)
- 2026-07-03 project initialized: objective written (4 ACs), e2e kit installed (agent)

## In progress

- (nothing — synthesis-voice sealed; the MoE depth demo now returns ONE grounded answer. Next is
  plan-depth-orchestration.md Task 3: a hermetic replay e2e for a 2-step dependent task (records
  the app-HTTP + synthesis calls), so the whole `--execute` loop is proven offline in CI)

## Next up

- Phase 2 thicken (thin end-to-end slice now works — see plan-slice1-first-live-call.md "Deferred"): grounded multi-app synthesis + verbatim voice (AC-4, E), trace/observability (F), web-search fallback execution, launcher cold-start/auto-start, trickier apps (WebSocket kernel, SSE, async-poll: blogs/research/coding), and a full-loop hermetic e2e (needs app-HTTP record/replay). Also: blogs/research self-declare ports 8787/8789 standalone — confirm live-port resolution when those are exercised.

## Known issues / parked

- (fixed 2026-07-08) empty-exception-string rendering ("fatal: " with no detail) — now falls back
  to the exception type name (app-caller-timeout task).
- error classification review (parked): `httpx.ReadTimeout`/timeout exceptions are classed "fatal"
  (not retried) because they are not Python `TimeoutError` subclasses and carry an empty message.
  The per-read-timeout fix makes this moot on the happy path; a broader `classify_error` review
  (treat httpx timeout types as transient) is a separate task if warm-up flakiness resurfaces.

## Key decisions

- 2026-07-03 — scaffold + verification contract adopted (see PLAYBOOK.md)
- 2026-07-07 — invocation approach: orchestrator calls each app directly over its existing FastAPI HTTP API (native tool-use), not MCP; build fresh (no code reused from prior attempts). Ports are launcher-assigned (8001–8011); the executor confirms the live port via the launcher + health at call time (blogs/research self-declare 8787/8789 standalone). See plan-invoke-apps.md.
