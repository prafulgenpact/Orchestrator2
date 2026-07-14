# Project State — A multi agent orchestrator system calling relevant apps basis intent recognition

Last updated: 2026-07-14 (selection-structured-output task)

## Done (most recent first)

- 2026-07-14 selection-structured-output (Phase 2, robustness — fixes a live web-fallback; serves
  AC-1). Live, a code-heavy step ("code blocks for all sections") routed to Simulated Learning but
  the selector's LLM authored a big `code` value as hand-written JSON that overflowed
  `max_tokens=2000` and truncated mid-string (`Unterminated string ... char 52`); all 3 retries
  truncated identically → web fallback. Fix: the selection call is now FORCED tool-use (one
  `select_operation` tool → `{operation, arguments}`), so the Foundry client returns
  `json.dumps(tool_use.input)` — always-valid JSON, no fence/raw-newline breakage even for a large
  multi-line code arg; `_MAX_TOKENS` 2000→8000 for headroom; a `max_tokens` truncation is detected
  in a pure `_extract_text` helper and raised as a clear `LLMError`, which the executor catches at
  the selection site (alongside `SelectionError`) → clean error → existing web safety net answers
  WITH disclosure (no crash, no silent fallback). `LLMRequest` gained optional `tools`/`tool_choice`
  serialized by `to_dict` ONLY when set, so planner/grounding/synthesis request hashes are
  byte-identical → NO fixtures re-recorded; decomposition eval untouched (still 16/16). 316 unit
  tests (9 new). make verify PASS. VERIFIED LIVE: the five-stage training-script task now executes
  on Simulated Learning (`op=execute_code status=ok 0.07s`, real stdout, source :8001/api/execute) —
  no web fallback. NEXT: Fix #2 — concurrent waves for slow async apps (blog/research 600s timeout).

- 2026-07-14 app-card-boundaries (Phase 2, richer app cards — serves AC-1). Every non-fallback
  app card now carries a `when_not` boundary (where it is the WRONG choice + the better app);
  loader parses it, `to_prompt_dict` exposes it, planner prompt → v3 with a rule to honour it
  (`PROMPT_VERSION="3"`). This is the "detailed description" investment aimed at the collisions
  (teach-me/stanford-llm/stats-teacher, news/social, blogs/research, code/coding-playground).
  Re-recorded the eval + e2e dry-run fixtures for prompt v3. Scored on the decomposition eval:
  **16/16, no regression** (v2 was already 16/16, so no measurable gain on THIS set — value is
  robustness + insurance for harder queries/new apps; a harder A/B set is a follow-up).
  make verify PASS. Bundled with the still-unsealed decomposition-eval deliverable (push together).

- 2026-07-14 decomposition-eval (Phase 2, measurement — serves AC-1). Added an offline
  decomposition test set so planner accuracy is a NUMBER, not an eyeball of one task.
  `tests/eval/cases.json` (16 labelled cases across the known app collisions + shape),
  `tests/eval/test_decomposition.py` (replays `plan_task` per case; asserts must-include /
  must-not-include apps + subtask-count range; SKIPS on a missing fixture so verify stays green),
  `tests/eval/record.sh` + README (record fixtures via the sanctioned dry-run CLI; hashes match
  the test's request). Baseline on prompt v2: **16/16 pass** — every collision routes right and
  the multi-ask case fans out correctly. make verify PASS (coverage counts only src, gate
  unmoved). NEXT: use this as the referee for the app-card "when NOT to use" boundaries.

- 2026-07-13 better-decomposition (Phase 2, planner prompt v2 — fixes under-decomposition +
  keyword-routing). Live, "explain LLM pre-training … teach me … show code … blog" collapsed to 2
  subtasks (Teach Me + Blogs), missed Stanford LLM, made no code step. Rewrote planner_system.md to
  v2: one subtask per distinct ask (explanation / code / written artifact are separate); route by
  SUBJECT MATTER not keywords ("teach me" ≠ Teach Me app); allow multiple relevant apps; dropped the
  "smallest/minimal" bias (typically 2–5). PROMPT_VERSION→"2"; re-recorded the dry-run e2e fixture.
  VERIFIED (dry-run): the LLM task now → Stanford LLM + Teach Me (parallel) + Simulated Learning
  (code) + Blogs (4 subtasks); CLT still correct. make verify PASS. NEXT: async-handle for
  Blogs/Research long jobs (user chose start→return→collect-later; removes the >cap web fallback).

- 2026-07-13 synthesis-no-truncate (Phase 2, fix a truncated multi-app answer found live). A 4-app
  CLT run (explain+repos+code+blog) truncated mid-code because synthesis re-fused everything into a
  1500-token answer. Two fixes: (1) `synthesize` now takes `subtask_deps` and, when there's a single
  terminal step (nothing depends on it; it depends on other ok steps) with prose output, passes THAT
  through (mode "final-step") — it already consumed the upstream, so re-fusing is redundant/lossy;
  sources still come from all ok results. cli passes the deps. (2) `_MAX_TOKENS` 1500→4000 so genuine
  fusions aren't cut. New synthesis tests (terminal pass-through / no-terminal fuse / non-prose /
  consumed-nothing / budget). make verify PASS.

- 2026-07-13 async-wait-cap (Phase 2, follow-on). Raised `_ASYNC_MAX_WAIT_S` 300s→600s: real blog
  jobs run longer than 300s (measured a real blog at 415s producing a genuine 6004-char article at
  result.content, title "Zero Changed Everything…"), so they were timing out and disclosing a web
  fallback. 600s lets them finish while staying bounded (no hang). Trade-off: a multi-minute
  synchronous CLI wait; a fire-and-return-handle async UX is a later option for the human. Confirmed
  result.content is the correct extraction path (the earlier "# Untitled Draft" was a degenerate
  result for the vague "test zero" topic). make verify PASS.

- 2026-07-13 async-payload-fix (Phase 2, follow-on to async-poll). Live blog test revealed the async
  START calls 422'd: the selector filled type-risky OPTIONAL fields with guessed values ("short
  blog" → word_count_target="short" → 422 int_parsing). Confirmed minimal {topic} → 200. Fix: trim
  the async start ops' request_fields to the safe minimal set (generate→[topic];
  iterate→[blog_id,instruction]; start_research→[topic]); the app defaults the rest, so the start
  succeeds and the T4 poller runs the app to completion. NOTE: T1 + web safety net worked perfectly
  on that run (delivered a web blog AND disclosed the Blogs 422). make verify PASS. (Richer
  type-validated optional passing is a later hardening.)

- 2026-07-13 async-poll (Phase 2, mini-task T4). Start-then-poll async operations are now driven to
  completion, so Blogs Playground writes the blog and Research Assistant runs the research instead
  of returning a bare run id (then falling back to web). New `AsyncSpec` on an operation contract
  (poll_op, run_id_field/arg, status_path, done/failed values, result_path — dotted paths that index
  lists, e.g. `versions.-1.output_md`); executor `_run_async` starts the job, reads the run id, and
  polls the run op until a terminal status, bounded by `_ASYNC_MAX_WAIT_S` (300s, no hang);
  `_run_app_op` routes to it when `op.poll` is set. Blogs `generate_blog_async`/`iterate_blog_async`
  and Research `start_research` got poll specs. `_dig` resolves the result paths. New registry +
  executor tests (start/poll monkeypatched, interval→0). make verify PASS. All THREE user asks (T1
  announce, T2 auto-start, T3 use-the-app) plus T4 async are now complete.

- 2026-07-13 chosen-app-answers (Phase 2, mini-task T3 of the 3 user asks; user CONFIRMED "use the
  relevant app, web only when none fits"). Operations can now declare `defaults` — values the
  selector fills for any request field the model omitted (never overriding a model-supplied value).
  Statistics Teacher `ask_question` got a default general module, so a plain "what is a p-value?" is
  now answered BY Statistics Teacher instead of skipping to the web. General/additive mechanism
  (registry parse + to_dict + selector setdefault). New registry/selector tests; executor
  required-field skip test adjusted (title/part now defaulted, blank module_id is the residual
  skip). VERIFIED LIVE: "what is a p-value?" -> Statistics Teacher (source :8007/api/qa), no web
  fallback. make verify PASS. REMAINING: T4 (Blogs/Research async-poll so those apps do the work).

- 2026-07-13 auto-start-apps (Phase 2, mini-task T2 of the 3 user asks). The orchestrator now
  starts an app's backend itself when it is needed but not running — the user never launches apps by
  hand. New `launcher.py`: `LAUNCH_SPECS` (all 11 apps: sibling folder, uvicorn entrypoint, extra
  env) + `ensure_started(app, client)` which spawns the backend detached (survives the CLI, reused
  next run) on the registry port and polls health until ready or a bounded timeout. `call_operation`
  calls it when the first health check fails, then re-checks; if there is no spec or the start
  fails, behavior is unchanged (clean error, no hang). Injected spawn+clock keep it unit-testable
  (real spawn is the only pragma-no-cover line). New test_launcher.py + app_caller auto-start tests
  (autouse fixture keeps spawns offline by default). VERIFIED LIVE: stopped Simulated Learning
  (8001), asked for a Fibonacci computation — the orchestrator started 8001 and returned 610.
  make verify PASS. NEXT: T3 (make chosen app answer; web only when no app fits — Stats default
  module); T4 (Blogs/Research async).

- 2026-07-13 announce-fallbacks (Phase 2, transparency — mini-task T1 of the 3 user asks). Every
  web-fallback substitution is now announced explicitly, never silent. `SubtaskResult` gained an
  optional `note`; when the safety net answers a subtask via the web because the chosen app couldn't
  (skip/error/no_match), the executor sets a note naming the bypassed app + reason, and
  `render_execution` prints a "⚠ Heads up — some apps were substituted" block right under the Answer
  (plus the note on the step). VERIFIED LIVE ("what is a p-value?" now shows the Stats-Teacher
  substitution up front). make verify PASS. NEXT: T2 auto-start apps; T3 make the chosen app answer
  (Stats default module; web only when no app fits — user CONFIRMED this reading); T4 Blogs/Research
  async.

- 2026-07-10 web-safety-net (Phase 2, completes the web fallback; serves the "give it any task ->
  answer" goal). When the app the planner chose can't ground a subtask — it skips (missing input),
  errors (down/failed), or returns an irrelevant result (no_match) — the executor now auto-retries
  that subtask via the web fallback (Tavily) and uses the web answer if it succeeds, else preserves
  the original failure (never masked). Refactored the primary app path into `_run_app_op`; the web
  attempt is attributed to the fallback app so Results transparently shows "Web Search (fallback)"
  even though Plan shows the chosen app. VERIFIED LIVE: bare "what is a p-value?" (routes to
  Statistics Teacher, which skips) now returns a grounded, cited web answer. Unit tests offline by
  default (autouse disables the net) + 4 opt-in safety-net tests. make verify PASS.

- 2026-07-10 web-search-fallback (Phase 2, plan-depth Task 4; serves the objective's "no app ->
  fetch from the web"). New `web_search.py`: `search_web` calls Tavily `/search` (include_answer)
  reusing the shared TAVILY_API_KEY, returning a grounded answer + citation URLs; `resolve_search_key`
  reads the key (process env > project .env > sibling). The executor's fallback branch now runs a
  real web search (was: skipped) under the hard deadline — ok with answer+citation, "skipped" if no
  key, "error" on failure. VERIFIED LIVE: "who won the 2022 FIFA World Cup?" routes to Web Search
  (fallback) and returns a cited answer. New test_web_search.py + executor/cli tests; make verify PASS.
  KNOWN GAP (next): the fallback only fires when the planner routes TO it — a task like "what is a
  p-value?" routes to Statistics Teacher (which then skips), so it still gets no answer. Needs a
  safety-net: fall back to web when the CHOSEN app can't ground the subtask (skip/error/no_match).

- 2026-07-10 selector-retry (Phase 2, robustness — serves AC-1). The operation selector now
  self-corrects on malformed JSON, mirroring the planner's bounded retry. Before: `select_operation`
  made ONE call and died on the first bad response — so a task needing code (e.g. execute_code)
  crashed with "operation selection was not valid JSON" when the model emitted multi-line Python
  with raw newlines inside a JSON string value. Now: on a parse/validation error the selector
  re-prompts with the concrete error + an escape hint (\n / \") up to `max_retries` (default 2),
  preserving the original SelectionError if all attempts fail; per-call token budget raised
  1000->2000 so long code args aren't truncated. New `_parse_selection` helper; 2 new selector
  tests; single-shot error tests pin `max_retries=0`. make verify PASS; verified live (a
  statistics-code task now selects + executes cleanly).

- 2026-07-10 phase1-app-fixes (Phase 2, all-11-apps plan — Phase 0 recon + Phase 1 hardening;
  serves AC-1/AC-2). Parallel recon (8 agents) confirmed ALL 11 app registry contracts match their
  live APIs — zero contract changes needed. End-to-end verification (7-app parallel workflow) found
  and fixed two accuracy issues, both additive: (1) code-execution tasks misrouted to Coding
  Playground (no REST execute op — WS-only, Phase 3); trimmed its capabilities/description to its
  real REST surface so code routes to Simulated Learning. (2) New optional `required_fields` on an
  operation contract; the executor now SKIPS a call (no HTTP) when the selector can't ground a
  required input — Statistics Teacher (`ask_question` needs module_id/title/part, no discovery
  endpoint) now skips cleanly instead of HTTP 422 (accuracy-safe; never invents a module). Verified
  working end-to-end via the orchestrator: ArXiv, AI Intelligence Deck, Stanford LLM, Teach Me,
  Github Learnings, Simulated Learning (6); plus Blogs/Research (async-poll) and Coding (WS) mapped
  for Phase 2/3, and Social Media contract-verified. Re-recorded the dry-run e2e fixture (registry
  prompt changed). make verify PASS.

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
