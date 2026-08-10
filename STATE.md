# Project State — A multi agent orchestrator system calling relevant apps basis intent recognition

Last updated: 2026-08-10 (route-graph-work-to-coding-playground task)

## Next — agreed with the user 2026-08-04 (RCA: CLT-graphs run failed silently)

1. ~~**route-graph-work-to-coding-playground**~~ DONE 2026-08-10 — see In progress below.
2. **step-status-honesty** (executor fix, bugfix-first). An app reply that itself says it failed
   (`success: false` / error-only body) must mark the step "error" (carrying the app's message),
   not "ok" — trace badge, feed, run record, synthesis all follow. Failing test first.
   Optional follow-up: one retry on the correct app when a step errors this way.

   Agreed e2e proof for both: failing unit tests first → decomposition eval green → `make verify` →
   restart connector, re-run the user's exact failing prompt ("Create graphs and charts illustrating
   CLT concepts") headless: graph step routed to coding-playground, chart drawn on step + final
   cards, 0 JS errors, run recorded; plus a live negative case (import of a missing module) showing
   an Error badge. User runs it themselves before push.

## In progress

- 2026-08-10 route-graph-work-to-coding-playground (registry fix, 1 of the 2 agreed CLT-RCA fixes).
  Simulated Learning's card now says plainly it CANNOT make charts/graphs (no plotting library,
  text output only; when_not points chart work at coding-playground), and Coding Playground's
  when_not no longer redirects code snippets to simulated-learning (that line caused the live
  CLT-graphs misroute; the card's WS run_code op renders matplotlib, so the line was wrong).
  Bugfix-first proof: new eval case clt-graphs-to-coding-playground recorded against the OLD
  registry FAILED (planner chose simulated-learning for the chart step, claiming it could draw
  matplotlib); after the card fix, all 17 fixtures re-recorded (registry text is in the request
  hash) + the 2 e2e dry-run fixtures: eval 17/17 + wellformed, 0 skips — old baseline intact,
  incl. run-code-to-simulated-not-coding-playground (plain snippets still go to
  simulated-learning). `make verify` PASS. Still owed for full close-out (with task 2): restart
  connector + live headless CLT re-run routed to coding-playground with charts drawn, then user
  runs it before push.

- 2026-08-07 conversational-feed (user request, with reference screenshots). The left task panel now
  talks like an agent instead of showing only a checklist. 1) Plan bubble (UI-only, no new LLM
  calls): on the `plan` event the panel shows a Master-Agent chat bubble — the recognized intent +
  a numbered list of the steps' plain-English descriptions — above the live step checklist.
  2) Live step narration: new `narrator.py` (+ `prompts/narrator_system.md`) makes ONE small LLM
  call per finished step, turning that step's REAL output into 1–2 grounded sentences (real
  numbers, honest failures; never invents); `web.py` fires it on a side daemon thread per result
  and emits a new `narrate` SSE event (worker joins narrators before the sentinel so no narrate
  lands after `done`); the UI appends each as a Master-Agent bubble, plus a plain-code closing
  bubble on `final`. Narration is garnish by contract: `narrate_result` never raises, a failure
  just means no bubble, and the run/answer path is untouched. 28 unit tests (6 new narrator, 2 new
  web); `make verify` PASS; live headless proof: p-value task → 2 `narrate` events interleaved
  after their `result` events with real numbers from the run ("The computed p-value is 0.0215…"),
  `final` + `done` intact, UI JS syntax-checked. Also gitignored the user's `.vscode/` (scope
  widened consciously — drift check flagged their debug config). Follow-up (user, after seeing it
  live): the old per-step Progress checklist is gone — the feed now shows only a live "Working
  on: …" spinner line per currently-running step (bubbles land on finish; without this a long
  step would look frozen), the "Progress" header stays hidden; and the final-answer card now has
  a RESERVED top-left canvas spot (`ANSWER_X/ANSWER_W`; intermediates masonry into 2 columns to
  its right) with a smooth scroll-to-top when it appears — no scrolling to find the answer.
  UI-file-only; `make verify` PASS. Awaiting user's browser check before seal/push.

- 2026-08-04 web-charts-and-run-logging (two user-reported web-connector parity gaps). 1) Spec-based
  charts now render in the UI: `web.py` renders each known-shape chart artifact to inline SVG with
  the existing `render_chart_svg` (`_chart_svg`/`_result_payload`), and the `final` event carries
  `charts` (`_collect_chart_svgs`, deduped/capped at 8) next to the kernel-PNG `images`; the Atelier
  page draws artifact SVGs on step cards (skipping the raw key/value dump when the chart IS the
  output) and in the answer card's Charts section. 2) Every web run is now logged: `run_events`
  calls `record_run` (same trail as the CLI — runs/<id>.json, sqlite, hash-chained events.jsonl)
  with exit_code 0/1; planning failures have no plan to record; recording is wrapped so a bad disk
  never breaks the SSE stream. 20/20 web unit tests; live-verified in headless Chrome (Titanic
  correlation heatmap SVG on step + final cards, 0 JS errors) with the run recorded as events.jsonl
  seq 4. `make verify` PASS.

- 2026-08-04 blog-embed-charts (chart fix 3/3 — completes the chart set). The published blog can now
  carry its charts. Added `AppOperation.embed_images` (a request-field name; parsed + round-tripped)
  and `executor._embed_upstream_images`, which appends upstream chart images (base64 PNGs) into that
  field as markdown data-URIs — deduped, capped by count (4) and a size budget (180k, the content
  cap), a no-op without charts. `_run_app_op` calls it before the request. `registry/apps.json`:
  `post_blog_import` carries `embed_images: "content"`. Best-effort + honest caveats (import path
  only; needs the blog subtask to depend on the chart step; display depends on the app rendering
  data-URI images; large charts skipped) — the charts always show on the Atelier answer card
  regardless (fix 2). New registry + executor tests. `make verify` PASS. This completes chart fixes
  1–3 (inline display, final-card charts, blog embed).

- 2026-08-04 final-answer-charts (chart fix 2/3). The final deliverable (the blog) now shows the
  charts made during the run. `web.py`: pure `_collect_images(plan_result)` gathers base64 PNGs from
  ok steps' `output['images']` (deduped, capped at 8), and the connector's `final` event now carries
  `images`. `atelier-workspace.html`: the answer card has an `.answer-charts` section that
  `finalizeAnswer` fills with the chart images. Unit tests for `_collect_images`; live-verified in
  headless Chrome (answer card renders the chart <img>s + the blog markdown, 0 errors). `make verify`
  PASS. Remaining: 3) embed charts into the published Blogs Playground post.

- 2026-08-04 codegen-inline-charts (chart fix 1/3). Intermediate charts now render. Root cause: the
  Coding Playground kernel captures a figure only when the code DISPLAYS it inline (`plt.show()` ->
  a `display_data` image frame the executor already turns into `output.images`); the model's code
  was `savefig`-ing to disk and printing "chart saved", so no image frames came back and the card
  showed only text. Fix: the operation-select prompt now requires code that produces charts to call
  `plt.show()` per figure and forbids `savefig`/file backends; prompt `version:` bumped 3->4. Guard
  test added. Selector prompt only (planner/eval untouched — the eval fixtures are the separate
  planner prompt). `make verify` PASS.
  Remaining chart fixes: 2) carry chart images to the final-answer card, 3) embed charts in the blog.

- 2026-08-04 plan-dedup-subtasks (fix 5/5 of the RCA set — the last one). Redundant decomposition is
  now collapsed at the source: `validation.parse_plan` runs `_dedupe_subtasks`, which merges
  subtasks that are exact duplicates — same app AND normalized title (case/whitespace/trailing
  punctuation insensitive) — keeping the first, dropping later twins, and rewiring any dependency on
  a dropped twin to the kept id. Deterministic and conservative (title-exact), so it's a no-op on
  the decomposition eval's distinct scenarios (verified: eval still 16/16) — the fuzzy cases stay
  covered by fix 2 (call cache) and fix 3 (UI dedup). New tests in test_validation. `make verify`
  PASS. This completes the 5-fix RCA set (2 RCAs: duplicate outputs + "only 1 paper").

- 2026-08-04 multi-paper-summarize (fix 4/5 of the RCA set). "Summarize the papers" now covers more
  than one. ArXiv's `analyze_paper` is single-paper and the executor runs one op per subtask, so a
  summarize step analyzed only 1 of the found papers. Added a contract-driven fan-out:
  `AppOperation.fan_out` (`{arg, source, max, title_from?}`, parsed + validated + round-tripped) and,
  in `_run_app_op`, when the op declares `fan_out` and upstream yields >=2 distinct items, the
  executor calls the op once per top-N item (deduped, reusing the fix-2 call cache) and aggregates
  into ONE ok result — a list of `{arxiv_id, title, content}` entries the existing UI renders as
  titled per-paper summaries. Fewer than 2 items keeps the single-call path. `registry/apps.json`:
  `analyze_paper` carries `fan_out {arg: arxiv_id, source: arxiv_id, title_from: title, max: 3}`.
  New tests: registry parse/validation, `_collect_fan_items` (dedupe+cap), `_run_fan_out`
  (analyzes each / all-fail=error), and an execute_plan integration proving both papers summarized.
  Routing untouched; eval unchanged. `make verify` PASS.
  Remaining: 5) plan-level dedup of overlapping subtasks (riskiest — touches the planner/eval).

- 2026-08-04 ui-dedup-identical-cards (fix 3/5 of the RCA set). Intermediate output cards are now
  unique. `web/atelier-workspace.html` only: `addResultCard` computes a signature
  `app | operation | status | JSON(output/error)` and, using a per-run `seenResultSigs` Set (reset
  in `runTask`), skips creating a second canvas card when an identical one already exists — the
  duplicate step is still enriched onto its trace step and the feed/trace re-render, so the
  technical view stays honest (one node per subtask). Live-verified in headless Chrome: three
  result events (two identical + one different) → 2 canvas cards but 3 trace nodes, deduped step
  still enriched, 0 JS errors. Together with fix 2 (which removes the duplicate WORK), a redundant
  decomposition no longer produces duplicate visible outputs. `make verify` PASS.
  Remaining: 4) multi-paper summarize, 5) plan-level dedup of overlapping subtasks.

- 2026-08-04 within-run-call-cache (fix 2/5 of the RCA set). When two subtasks resolve to the exact
  same app call (same app, operation, args) — the redundant-decomposition case behind the duplicate
  ArXiv cards — the executor now issues that call ONCE and shares the result instead of hitting the
  app twice. A per-run `call_cache` of in-flight `asyncio.Task`s (created in `execute_plan`, threaded
  to `_run_subtask`/`_run_app_op`) coalesces by `(app_id, op_name, json(args))`; the crucial case is
  the two duplicate "find" subtasks that run CONCURRENTLY in the same wave — they await the SAME task
  because there's no await between the cache get and set. Only idempotent, non-destructive ops are
  coalesced; a not-ok result is evicted so a later identical call can retry; `call_cache=None` (the
  default for direct callers) disables it. New tests in test_executor (concurrent + sequential dedup,
  non-idempotent/destructive skip, failure eviction, None-off). This removes the duplicate WORK; the
  duplicate CARD is fix 3 (UI dedup, next). `make verify` PASS; eval unchanged.
  Remaining: 3) UI dedup of identical cards, 4) multi-paper summarize, 5) plan-level subtask dedup.

- 2026-08-04 search-count-floor (fix 1/5 of the RCA set). A vague "find some good papers" no longer
  collapses to 1 result. The paper count is the LLM selector's `max_results`, previously with no
  floor. Added `AppOperation.arg_min` (a numeric floor map, parsed + round-tripped) and
  `selector._enforce_arg_floors`, which — after type coercion — raises any present numeric arg below
  its floor UP to it (honors larger explicit counts; leaves omitted args alone so the app default
  applies; ignores bools/non-numbers). `registry/apps.json`: the two ArXiv search ops
  (`search_papers_by_query`, `search_papers_by_topic`) carry `arg_min: {max_results: 5}`. Verified:
  a selection returning `max_results: 1` yields `5`. New tests in test_registry + test_selector.
  Value-level guard only (no routing change; eval unchanged). `make verify` PASS.
  Remaining RCA fixes (in order): 2) within-run duplicate-call cache, 3) UI dedup of identical
  cards, 4) multi-paper summarize, 5) plan-level dedup of overlapping subtasks.

- 2026-07-31 connector-quiet-disconnects (Whole-app UI — connector). The connector no longer dumps
  a traceback when a browser closes a socket early (preconnect / refresh / navigating away
  mid-SSE). Those `ConnectionResetError`/`BrokenPipeError` raise in the base handler's request-line
  read — before our handler — so `_serve_run`'s try/except never saw them and the default
  `handle_error` printed a full traceback (harmless but alarming). Fix in `web.py`: pure
  `_is_benign_disconnect(exc)` + a `ThreadingHTTPServer` subclass whose `handle_error` swallows
  those and defers to the base for real errors; `serve()` uses it. Live-verified: 3 forced RST
  disconnects → clean log, no traceback. Unit tests for the predicate. `make verify` PASS.
  (Restart the connector — re-run `./run.sh` — to pick up the fix.)

- 2026-07-31 datastore-bring-up (tooling/DX). Added `./datastores.sh` — one idempotent command
  brings up the only datastore an app hard-requires today: PostgreSQL on :5432 with the
  `arxiv_explorer` DB, which ArXiv Paper Guide needs (it auto-creates its own tables on boot via
  `Base.metadata.create_all`). The script installs/starts Homebrew `postgresql@16`, waits for
  `pg_isready`, creates the DB if missing, and self-heals a stale `postmaster.pid` (only when the
  recorded PID is not a live postgres — the exact failure hit here: the OS had recycled the PID).
  Docker is installed but its daemon was off, so native Homebrew Postgres is the path; script notes
  the Docker alternative and that Coding/Blogs' MySQL/Redis are optional. Live-verified: ran the
  script → Postgres up + DB present → ArXiv `ensure_started` True → `orchestrator.doctor` shows
  `ArXiv Paper Guide UP :8002`. RUNBOOK documents `./datastores.sh` + `./run.sh --check`.
  `make verify` PASS.

- 2026-07-31 app-startup-diagnostics (Phase 2 — resilience/diagnosability). App-startup failures
  are now diagnosable across ALL apps, not just ArXiv. Root of the pain: the launcher spawned apps
  with stdout/stderr → /dev/null, so a boot crash (a down DB, a missing key, an import error)
  collapsed into an opaque "health check failed". Now: `_spawn_uvicorn` captures each app's startup
  output to `logs/apps/<id>.log` (gitignored); `read_startup_error`/`_extract_startup_error` pull
  the salient crash line; `call_operation` appends that reason to the health-fail error so the
  trace shows the real cause. New `orchestrator/doctor.py` — `python -m orchestrator.doctor` (and
  `./run.sh --check`) prints per-app readiness and the reason for each down app. Live-verified: the
  doctor reports 10/11 up with `ArXiv Paper Guide DOWN — OSError: Connect call failed (:5432)`
  (Postgres). Also learned Coding/Blogs boot fine despite MySQL/Redis refs (optional/lazy); only
  ArXiv hard-requires its DB. No planner/routing change; eval unchanged. `make verify` PASS.
  NEXT (approved, separate task): provide a datastore bring-up so ArXiv's Postgres (and any needed
  MySQL/Redis) can be started locally.

- 2026-07-31 run-script (tooling/DX). Added `./run.sh` — one command starts the whole app and opens
  it. In this architecture the connector (`python -m orchestrator.web`) is both backend
  (orchestration + SSE) and frontend (serves the Atelier UI) and cold-starts the sibling apps on
  demand, so there's one server, not two. The script loads `.env`, frees the port of any stale
  connector (guarantees current code — kills the stale-process class of bug), starts the connector,
  waits until it answers, opens `http://127.0.0.1:$PORT/`, and stops cleanly on Ctrl-C. Port via arg
  or `ATELIER_PORT`; `NO_OPEN=1` skips the browser. RUNBOOK documents it. Verified by running it
  (port 8099): loaded .env, served the Atelier UI HTML, freed the port on stop. `make verify` PASS.

- 2026-07-31 blog-import-reliable-publish (Phase 2 — app contracts). Blogs Playground now PUBLISHES
  reliably instead of erroring at the deadline. Root cause: `POST /api/blog/import` runs an inline
  StyleCritic+Verifier (~30–60s+, two Opus calls) when `run_critique=true`, which the app model
  defaults True; the orchestrator never set it, so every import took the slow path and blew the hard
  60s deadline (recorded `retry: operation exceeded 60.0s deadline`, transient class but
  transient_max=0 so no retry). Fix in `registry/apps.json` (op `post_blog_import`): default
  `run_critique=false` (selector setdefault → sent in the POST body → instant publish path), remove
  `run_critique` from model-filled `request_fields` so it can't be turned back on, and raise
  `timeout_s` 60→120 as an anti-hang backstop. The blog text was always model-authored (the
  `content` arg); only the publish failed — now it succeeds and the app holds the blog. New
  regression test `test_blog_import_publishes_fast_without_inline_critique`. `make verify` PASS.

- 2026-07-31 trace-code-authoring-substep (Whole-app UI — polish). `web/atelier-workspace.html`
  only, no backend change. When a step's input carries model-authored code (`args.code`), the
  Agent Trace now renders TWO honest nodes: a "Wrote the code" node attributed to the Orchestrator's
  model (Output = the code) followed by the app-execution node (method + output). Extracted a
  `traceNode(opts)` builder to render each collapsible node. This resolves the "one method shown"
  complaint truthfully: Simulated Learning exposes no write API (only `execute_code`/`ask_question`),
  so the code authoring is attributed to the orchestrator, not faked as an app call. User explicitly
  chose this over a backend write→execute split (which isn't possible without a write endpoint).
  Live-verified in headless Chrome: code step → 2 nodes, non-code step → 1 node, 0 JS errors.
  `make verify` PASS.

- 2026-07-31 faithful-output-and-feed-descriptions (Whole-app UI — polish). `web/
  atelier-workspace.html` only, no backend change. (1) String outputs now route through
  `looksLikeMarkdown`/`renderText`: true markdown (blog, summaries, lessons) renders rich; plain
  or console-style reports (e.g. Simulated Learning's `====`-boxed p-value demo, which the earlier
  markdown pass mangled into stray rules) render faithfully in a monospace `.report` block that
  preserves the app's own layout. (2) The left Progress feed is now conversational — it shows each
  step's plain-English description — while the Agent Trace keeps the short technical title + app +
  method, so the two views no longer duplicate each other. Live-verified in headless Chrome:
  box-report → `<pre class="report">` with no stray `<hr>`; blog → markdown; feed shows
  descriptions and trace shows titles (feed ≠ trace); 0 JS errors. `make verify` PASS.
  NEXT (separate backend task, plan-first): user chose to split code apps into write→execute as
  two real trace steps — a planner/executor change that affects the decomposition eval.

- 2026-07-31 output-format-and-trace-detail (Whole-app UI — polish). `web/atelier-workspace.html`
  only, no backend change. (1) `mdToHtml` now joins wrapped lines within a paragraph with `<br>`
  (not a space), so plain multi-line tool reports (e.g. Simulated Learning's p-value demo) keep
  their structure instead of collapsing into one cluttered blob; report-style `=== Title ===` /
  `--- Title ---` lines render as `<h3>` sections and bare rules as `<hr>`. (2) The agent trace
  detail now shows App / Method / Input / Output / Status per step — `addResultCard` stores each
  result's operation, args, and output on the step; `renderTrace` renders them (Output truncated
  via `trunc`, args compacted via `argsText`). Live-verified in headless Chrome: p-value report →
  `<h3>` sections + `<br>` lines; trace keys = App/Method/Input/Output/Status populated; 0 JS
  errors. `make verify` PASS.

- 2026-07-31 rich-output-rendering (Whole-app UI — polish). Result cards + the final answer now
  render app outputs as readable, well-formatted content instead of raw JSON / raw markdown source,
  and copy as clean plain text. `web/atelier-workspace.html` only, no backend change. Added a small
  self-contained markdown renderer (`mdToHtml`/`mdInline`: headings, bold/italic, inline + fenced
  code, ul/ol, blockquote, hr, links, paragraphs — escape-first, CSP-safe) and a shape-aware value
  dispatcher (`renderValue` → `renderPaper`/`renderKV`): strings and text-bearing dicts (content /
  chat `messages`) render as markdown; ArXiv paper lists render as title/authors/meta/abstract/link
  items; base64 images as <img>; unknown shapes as a clean key/value view. The streamed answer
  accumulates raw and re-renders markdown per delta. Copy payloads (`valueToText`/`paperToText`)
  give markdown source for prose and a readable list for papers. Live-verified in a headless
  browser: answer renders <h1>/<h2>/<strong>/<ul> with zero stray `#`; ArXiv shows readable paper
  titles/links with no JSON noise; paper Copy yields title/authors/abstract/link. `make verify` PASS.

  Earlier this session — ui-blank-start-clean-copy (Whole-app UI — polish, commit 798915d). Three UI fixes to
  `web/atelier-workspace.html`, no backend change so routing is untouched: (1) a fresh load is now
  a clean slate — the 5 sample result cards were removed from the canvas, the user message + the
  "Progress" header stay hidden until a real run, and the trace summary starts empty (all of it
  fills live from the run's own events); (2) the "System Telemetry" block under the Agent Trace
  (active-apps / tokens / latency chart) was removed entirely, HTML + its dead CSS; (3) every
  result card and the final answer card now carry a structured `data-copy` plain-text payload
  (label -> output/JSON -> note -> sources; the streaming answer keeps it in sync), so the Copy
  button yields clean, paste-ready text instead of scraped screen text. `make verify` PASS.

## Done (most recent first)

- 2026-07-30 web-connector-live-run (Whole-app UI — Phase 1; commit ecdde05). A live web connector
  joins the Atelier UI to the running orchestrator. New `src/orchestrator/web.py`: a pure
  `run_events` generator relays the existing `plan -> execute(progress) -> synthesize(on_delta)`
  pipeline to the browser as an ordered Server-Sent-Events stream (status/plan/progress/result/
  answer/final/error/done), behind a thin `ThreadingHTTPServer` (`python -m orchestrator.web`,
  `$ATELIER_PORT`, `$ATELIER_UI`). `web/atelier-workspace.html` drives the feed, trace, and result
  cards from an `EventSource`. `execute_plan` gained an optional `on_result` callback fired the
  moment each subtask finishes, so intermediate app outputs appear as each app completes rather than
  after the whole run. No planner/synthesis change; decomposition eval unchanged; make verify PASS.

- 2026-07-28 observability-report-command (Observability — one-command live report). One command
  now runs a real task and prints the whole observability picture with real numbers:
  `PYTHONPATH=src python3 -m orchestrator --execute --report "<task>"`. New `render_report(...)`
  composes a single terminal report — summary KPIs (success rate, latency p50/p95/p99), cost +
  tokens per model, quality, health alerts, per-app table, recent runs, and this run's per-step
  drill-down — from the read service built earlier. `render_kpis` was hoisted into observability so
  the `--kpis` view and the report share one renderer. CLI: a `--report` flag on the run (best-
  effort; a report failure never changes the exit code or hides the answer) and a standalone
  `orchestrator runs report [--run-id X] [--json]`. RUNBOOK documents the one-command flow. No
  LLM/executor change; make verify PASS; eval 16/16. Observability plan complete through the
  backend + CLI; only the visual dashboard (Step E) remains, pending the whole-app UI.

- 2026-07-28 observability-cost-tokens (Observability — cost & token accounting). Each run now
  records the tokens it used and its dollar cost, rolled up per run and per model. Capture: a new
  TokenUsage (llm/base.py); FoundryClient accumulates one per call in complete_stream and
  drain_usage() returns+clears them; ReplayClient drains to [] and RecordingClient delegates. The
  CLI drains the (single, shared) client once at record time and passes usage to record_run — usage
  is NOT in the request hash, so replay fixtures and eval (16/16) are untouched and complete()'s
  return type is unchanged. Cost: cost_of() sums non-overlapping token buckets × a configurable
  per-MTok price table (_DEFAULT_PRICES, override via ORCHESTRATOR_PRICES JSON); tokens are exact,
  and an unknown model keeps its tokens but is listed in unpriced_models rather than getting a
  fabricated cost. Persisted as runs.input_tokens/output_tokens/total_tokens/cost_usd (column
  migration) + a `cost` block on the record; surfaced in list_runs, kpis (`cost`: total_usd,
  total_tokens, by_model), the KPI view, and run detail. make verify PASS; eval 16/16. This closes
  the last deferred observability piece; only the visual dashboard (Step E) remains, pending the
  whole-app UI design.

- 2026-07-28 observability-quality-alerts (Observability Step D). Runs now carry a quality score,
  the store tracks quality over time, and threshold breaches surface as alerts. (a) Quality: each
  executed run record gets a `quality` block (score = clean-ok steps / executed steps, where a
  clean-ok step returned data and was NOT flagged by the advisory relevance judge; dry runs →
  None). Persisted as `runs.quality_score` (added to the DDL; an idempotent ALTER migrates
  pre-existing local DBs on open) and surfaced in list_runs + kpis (`quality`: avg_score, by_day,
  scored_runs). (b) Alerts: alerts(root, thresholds) returns one entry per breached threshold —
  error rate, no-match rate, fallback rate, p95 latency, an absolute quality floor, and a
  recent-vs-older quality-drop — with warning/critical levels; record_run also logs a per-run
  WARNING when a run has failed steps or low quality. (c) CLI: `orchestrator runs alerts` (+ --json)
  and quality shown in `runs list --kpis`. All derived from data already captured — no LLM/executor
  change — so make verify PASS and eval 16/16. DEFERRED: `promote <run_id>` into the eval dataset
  (mutates the 16/16 release gate — its own task) and accurate cost/token capture (needs an
  LLMClient contract change).

- 2026-07-28 observability-runs-cli (Observability Step C). Saved runs are now browsable without a
  UI. observability.py gains a UI-agnostic read service — list_runs(root, limit, status) (recent
  runs, newest first) and kpis(root) (totals, status counts, run-latency p50/p95/p99, per-app
  usage, avg routing confidence, fallback/no-match rates; empty store → zeros) — plus text
  renderers. The CLI gains an offline `orchestrator runs list` (with --kpis/--limit/--status/--json)
  and `runs show <id>` (full per-step drill-down; exit 5 on unknown id), routed at the top of main
  before any registry/client/network so it works with no LLM and never records. Also fixed test
  hygiene: an autouse conftest fixture points ORCHESTRATOR_OBS_ROOT at a per-test tmp dir, so the
  suite no longer litters the repo root with runs/logs/observability.db (a side effect introduced
  when Step A wired recording into the CLI). make verify PASS; eval 16/16. The read service is the
  stable contract the deferred Step E dashboard will bind to.

- 2026-07-28 observability-audit-trail (Observability Step B, part 1). The saved audit trail is now
  defensible. (a) Tamper-evidence: logs/events.jsonl is a hash chain — each line carries seq +
  prev_hash + hash = sha256(prev_hash + seq + canonical(payload)), chained from a fixed genesis;
  verify_chain(root) recomputes the chain and returns (False, seq) at the first edited or deleted
  past record (tail truncation is the one undetectable case, documented). (b) Redaction: redact()
  recursively masks emails, sk-/AKIA keys, and bearer tokens in nested dicts/lists/strings before
  anything is written, so a credential embedded in an app's output/args is never persisted;
  disable with ORCHESTRATOR_OBS_REDACT=0. Both live entirely in observability.py — no LLM-path
  change — so make verify PASS and eval 16/16. FOLLOW-UP: accurate cost/token capture is deferred
  to its own task because it needs an LLMClient contract change (complete() returns only str today;
  message.usage is available in foundry.complete_stream but discarded) and must not disturb replay
  fixtures.

- 2026-07-28 observability-save-runs (Observability Step A). Every run is now saved durably in the
  standard trace/step shape (a run is one trace; each subtask a nested step — the shape Langfuse /
  Phoenix / OpenTelemetry GenAI use), so history, audit, and a later dashboard are possible. New
  `src/orchestrator/observability.py` exposes a reusable `record_run(...)` entry point (the CLI uses
  it now; a future UI backend reuses it unchanged) that writes three sinks: `runs/<run_id>.json`
  (full detail incl. per-step inputs/outputs/timing and the routing rationale+confidence — the "why
  this app?" provenance), a `runs`+`steps` summary in `observability.db` (SQLite, for fast KPIs),
  and an append-only `logs/events.jsonl`. Recording is best-effort: every sink is wrapped so a disk
  failure is logged and swallowed — it never changes a run's answer or exit code — and nothing
  touches the planner/selector/judge, so LLM request hashes and eval fixtures are unaffected. CLI
  gains `--no-record` and `--run-id`. All new deps are stdlib (uuid/sqlite3/json/logging). make
  verify PASS; eval 16/16. Next: Step B (cost/tokens + tamper-evident hash chain + redaction).

- 2026-07-27 determinism-and-visibility (Fix 5 of the web-fallback deep-dive). Three
  determinism/visibility improvements. (a) Determinism: LLMRequest gains `temperature: float = 0.0`
  and FoundryClient passes it — every planner/selector/judge/synthesis call now runs at temp 0, so
  the same task behaves the same way run-to-run (was the SDK default 1.0). temperature is
  deliberately EXCLUDED from `to_dict()`/request_hash so recorded replay fixtures still resolve (it
  doesn't change a replay). (b) Web labelling: render surfaces "Answered from a web search (no
  specialized app covered this)" for any ok result with operation == "web_search" — a planner-routed
  web answer is no longer indistinguishable from an app answer. (c) Auditability: SubtaskResult
  carries `args` (the exact arguments sent to the app), threaded from the executor and printed under
  `--verbose` — a guessed/defaulted input is now visible. make verify PASS; eval 16/16.

- 2026-07-27 judge-warns-not-discards (Fix 3 of the web-fallback deep-dive). The relevance judge is
  now ADVISORY, not a deleter. Previously an LLM FAIL verdict dropped an app's output to no_match
  (pre-Fix-2: → web; post-Fix-2: → honest failure) — but the judge is a single stochastic opinion
  and a wrong discard is itself an inaccuracy, and the apps are tuned to the user (AC-4). Now: a
  FAIL on NON-EMPTY output KEEPS the app's answer (status ok, output preserved) with a visible
  caution note ("the relevance check flagged this may not fully match the task (...)"), surfaced as
  a heads-up under the answer. Genuinely blank output stays the one hard FAIL (no_match). grounding
  exposes `is_blank` (was `_is_blank`) so the executor tells empty apart from off-topic-with-content;
  check_relevance's (bool, reason) contract is unchanged. make verify PASS; eval 16/16.

- 2026-07-27 recover-stuck-apps (Fix 4 of the web-fallback deep-dive). A hung-but-listening app
  (the 6-day ArXiv case: process up, answering nothing, port held so a fresh start can't bind) is
  now auto-recovered at run start. Three parts: (a) honest health — `is_healthy_response` requires
  a 2xx that is NOT text/html, so teach-me's SPA page (200 HTML on any path) no longer reads as
  healthy; teach-me health path moved /models -> /topics (real JSON route). (b) stale-process
  reaping — `reap_stale_listeners` kills a process squatting the app's port ONLY when positively
  identified as this app's own uvicorn (token match on uvicorn + entrypoint + port; folder/cwd is
  not in argv, so the first attempt that matched on folder never fired — caught live, fixed to
  match on port). (c) `ensure_started` is health-first (a live app is never duplicate-spawned),
  then reap -> respawn -> poll when unhealthy. app_caller shares the same honest health verdict.
  make verify PASS; eval 16/16. Reap helpers (lsof/ps/kill) are injected so logic is unit-tested
  with no real processes. Circuit-breaker cooldown (deep-dive R5) deferred to a later task.

- 2026-07-24 fallback-only-when-no-app (Fix 2 of the web-fallback deep-dive). Removed the runtime
  "safety net" in executor._run_subtask that silently answered from the web whenever a CHOSEN app
  failed/skipped/returned no_match. Web is now used ONLY when the planner routes a subtask to the
  web-search app (no app fits) — the objective's one sanctioned web path. A chosen app that fails
  is reported honestly: synthesis builds a grounded per-app failure answer ("This task could not
  be completed by the selected apps: - <app> <reason>") instead of the bland none-line, and
  render surfaces failures as a "⚠ Some parts of the task could not be completed" heads-up right
  under the answer. Inverted the 4 web-safety-net executor tests (skip/error/no_match/selection
  error now stay failed even with web available); kept the 4 planner-fallback tests. Live: "2022
  World Cup final" still answered via web (planner route intact). make verify PASS; eval 16/16.

- 2026-07-24 selector-schema-safety (Fix 1 of the web-fallback deep-dive). Root cause of "legit
  task -> 422 -> web fallback": the selector saw field NAMES only, so it filled a typed field with
  a wrongly-typed value (live proof: word_count_target="short" for an integer field) and the app
  422'd into web. Fix: (a) OpenAPI slim snapshots now carry a `types` map per endpoint
  (contract.slim_from_openapi, resolving Optional[...] anyOf); (b) the selector's operation view
  shows "field: type" and a new value gate (selector._enforce_field_types) coerces safe cases
  ("5"->5, "true"->True) and DROPS the uncoercible — an optional field then uses the app default, a
  required field trips the honest missing-input skip instead of a garbage call; (c) removed the two
  unsafe sync blog-generate duplicates (post_blog_generate, post_blog_generate_streaming) so the
  trimmed generate_blog_async is the only generate path (no more per-run op lottery). make verify
  PASS; eval 16/16; live: short-blog produced BY Blogs Playground, no fallback. Supersedes
  20260713-async-payload-fix.

- 2026-07-20 render-charts-images (Phase 2 — make chart/plot outputs viewable, UI-ready). Two
  mechanisms. (a) Spec charts: added a line/curve renderer to artifacts.py — ROC/PR `{curves:[...]}`
  as multi-line (+ chance diagonal), learning-curve `{train_sizes,train_mean,val_mean}` as two lines,
  classification `{confusion_matrix,classes}` as a heatmap — and flagged the 8 `post_viz_*` ops
  `produces:"chart"`, so they now render to openable HTML instead of returning raw JSON. (b) Image
  charts: `Artifact(kind="image")` carries a base64 PNG; the executor promotes any `data["images"]`
  (e.g. run_code's matplotlib output) to image artifacts, and save_artifacts writes them as openable
  `.png`. Artifacts carry the source data (spec/PNG), so a future UI renders inline with no backend
  change (SVG -> DOM, PNG -> <img>). Renamed `_chart_artifacts` -> `_result_artifacts`. Live-smoked:
  real ROC -> HTML with the curve; real kernel plot -> a valid 534x435 PNG. make verify PASS; eval
  16/16.


- 2026-07-20 ws-kernel-transport (Phase 2 — the last capability). Added a WebSocket transport so the
  orchestrator can run arbitrary Python in coding-playground's live Jupyter kernel: op flagged
  `stream: "ws"` sends an execute request over `websockets` and assembles frames into
  `{text, images, error}` (stdout/result text, base64-PNG matplotlib images, tracebacks), stopping
  at `execute_reply`, bounded by the op deadline (no hang). `WS` added to allowed methods; wired
  `coding-playground.run_code` (path /api/kernel/ws). WS ops are exempt from the HTTP contract check
  (not in any /openapi.json). Declared the `websockets` dependency. Live-smoked run_code against the
  real kernel (stdout + a rendered PNG). make verify PASS; decomposition eval 16/16. This closes the
  capability gap: every HTTP endpoint (215/215) plus the one WebSocket capability are now exposed.


- 2026-07-20 sse-streaming-transport (Phase 2 — final 100% capability coverage). Added a generic
  Server-Sent-Events transport: an op flagged `stream: "sse"` is consumed to completion via
  `client.stream` and assembled into `{text, events}` (handles both frame dialects — `{"token":..}`
  and `{"type":"token","content":..}` — stops at `[DONE]`, bounded by the op deadline = no hang).
  New `stream` field on `AppOperation`. Wired the 7 SSE endpoints (github chat/repo·code·cross-repo,
  build/suggest, compare; blogs generate/streaming; research stream) + `get_runs_events` (actually
  JSON). Registry 207 -> 215 ops. Coverage ratchet's deferred set is now EMPTY -> the test demands
  100%. Live-smoked `post_build_suggest` against the real github app (11k+ chars assembled). Every
  non-internal endpoint of all 11 apps is now exposed (the WebSocket kernel is outside the OpenAPI
  denominator). make verify PASS; decomposition eval 16/16.


- 2026-07-20 expose-all-capabilities (Phase 2 — capability coverage). Wired every non-internal,
  non-streaming endpoint of all 11 apps as a registry operation, generated directly from each app's
  live OpenAPI (accurate method/path/fields; DELETE marked destructive; heavy paths given longer
  timeouts). Registry grew 53 -> 207 ops (+154). Now every plain-JSON capability is exposed; the
  only remaining gaps are 8 deferred streaming endpoints (SSE/WS, need transport code — follow-on
  tasks). New coverage ratchet `tests/unit/test_registry_coverage.py` asserts no non-streaming
  endpoint is left unwired (fails if a refreshed snapshot adds one). All 154 new ops pass the
  contract guardrail (they were generated from the same OpenAPI it validates against). make verify
  PASS; decomposition eval still 16/16 (app-level routing unaffected).


- 2026-07-20 api-contract-guardrail (Phase 2 — guardrail #8: registry vs live app APIs). Wiring a
  registry op with a wrong method/path/field can no longer be sealed. New `contract.py`
  (`check_op`/`slim_from_openapi`, pure) validates every op against committed slim OpenAPI snapshots
  in `tests/contract/openapi/<app>.json`; `tools/refresh_openapi.py` re-fetches live `/openapi.json`
  to update them (live-reconciliation step, like re-recording fixtures). Enforced as a unit test
  (`tests/unit/test_api_contract.py`) so it rides `py-unit` in `make verify` WITHOUT touching the
  enforcement layer (rule 8). On its FIRST run it caught real drift record/replay never could:
  `teach-me.create_topic`/`send_user_message` declared a `model` request-field the API rejects
  (removed both). A third flag (`upload_corpus_document` `file`) was a false positive from the
  extractor ignoring `multipart/form-data` bodies — fixed in the extractor. Snapshots seeded for all
  11 apps (all reachable). make verify PASS; decomposition eval still 16/16; unit 379→488.

- 2026-07-20 eda-charts (Phase 2 — capability coverage: the orchestrator can plot/analyze a

- 2026-07-20 eda-charts (Phase 2 — capability coverage: the orchestrator can plot/analyze a
  dataset). Wired coding-playground's 7 EDA endpoints (summary, dtypes-missing, distribution,
  correlation, scatter, target-distribution, outliers) as HTTP operations. Added a declarative
  `produces: str | None` field to `AppOperation` (registry.py) so an op can announce it emits a
  chart; the executor's `_chart_artifacts` keeps a `produces == "chart"` op's error-free dict output
  as a first-class `Artifact(kind="chart")` (rendered to an openable HTML file by last task's
  artifacts.py, which also handles the `{labels, counts}` spec as bars for target-distribution).
  distribution/correlation/scatter/target-distribution are flagged `produces: "chart"`. Proven
  test-first (registry parses produces; chart-op attaches artifact, non-chart op does not;
  labels+counts renders bars). The registry edit re-keyed every replay fixture, so all 16 eval
  fixtures + the e2e fixture were re-recorded (16 orphaned old fixtures removed). Task Scope widened
  to cover tests/e2e/fixtures/**, tests/eval/fixtures/**, .gitignore (RESUME.md + orchestrator-output/
  ignored as scratch). make verify PASS; decomposition eval still 16/16.

- 2026-07-16 stream-answer (Phase 2 — UX: the answer appears as it is written). The final answer
  now streams to stdout token-by-token instead of appearing only after the whole run.
  `FoundryClient.complete_stream(request, on_delta)` streams text deltas and returns the assembled
  text; `complete` is now just `complete_stream` with a no-op sink (one path, same inactivity
  bound + max_retries=0). `synthesize(..., on_delta=)` feeds the answer to the sink — streamed on
  the LLM-fusion path when the client supports it, emitted whole for the pass-through modes;
  clients without complete_stream (Replay/Recording) transparently fall back, so determinism +
  fixtures are untouched. `render_execution(include_answer=False)` lets the CLI print the streamed
  answer itself without duplication; the CLI prints "Answer:", streams the answer, then Sources,
  then the plan/results below. Proven test-first (foundry deltas, synthesis stream + fallback +
  pass-through emit, render omit-answer, CLI single-emit-no-duplication). make verify PASS;
  decomposition eval still 16/16. Completes the sequenced performance/UX set. The optional 6th item
  (in-run LLM memoization) was assessed and DROPPED: within one run there are no duplicate LLM
  requests (planner retries carry different error feedback; selector/relevance/synthesis each run
  once per distinct subtask), so an in-run cache would never hit; a cross-run disk cache was
  declined on accuracy grounds ("no guesswork"). Net of the 5 shipped changes: real parallel waves
  (~slowest-app not sum), progress-based LLM calls (no blind stopwatch; ~9-min hang gone), no
  duplicate poll-time health pings, live progress + heartbeats, and a streamed answer.

- 2026-07-16 live-progress (Phase 2 — UX: never looks stuck; reinforces AC-2 slow != hung). The
  user saw nothing between the readiness note and the final result. Added an injectable `progress`
  callback (default silent) threaded through execute_plan/_run_subtask/_run_app_op/_run_async: a
  live per-subtask start line ("-> title") and finish line ("[status] title (Xs)"), plus a
  heartbeat every 3rd successful poll during a long async job ("... still working: app (N polls,
  responding)"). The CLI prints these to STDERR (a "Starting apps..." line before the preflight),
  so stdout stays clean for the answer / --json. No change to results, ordering, or exit codes.
  Proven test-first (executor progress events, poll heartbeat, CLI stdout/stderr split). make
  verify PASS; decomposition eval still 16/16.

- 2026-07-16 cache-endpoint-per-run (Phase 2 — UX/efficiency; keeps AC-2 safety). Every
  `call_operation` re-issued `GET /api/apps` (launcher resolve) + `GET {health}` before the real
  request; on the async poll path `_run_async` calls `call_operation` for the start AND every poll,
  so a long job paid ~2 wasted round-trips per poll (~1800 on an hour-long run). New `AppEndpoints`
  cache (app_caller.py) resolves the base URL + confirms health ONCE per app per run (auto-starting
  a down app on first miss, as before) and reuses both; `call_operation` gained
  `endpoints=None` (default = old per-call behaviour) and `execute_plan` threads one instance
  through `_run_subtask`/`_run_app_op`/`_run_async`. Safety intact: app confirmed alive once, later
  death still surfaces on the real call (circuit breaker / clean error). Proven test-first: shared
  cache dedupes resolve+health across calls; a real N-poll run pings launcher+health once each; the
  no-cache path is unchanged. make verify PASS; decomposition eval still 16/16.

- 2026-07-16 progress-based-llm (Phase 2 — AC-2: nothing may hang, without capping genuine work).
  Directly resolves the FOLLOW-UP the llm-call-deadline task left below. `FoundryClient.complete`
  now streams (`messages.stream`) instead of one blocking `messages.create`, which changes what the
  existing `timeout` MEANS: many small reads → it is now a per-token *inactivity* limit, not a total
  stopwatch. A call that keeps emitting tokens runs as long as it needs (slow ≠ hung); only true
  silence for `resolve_llm_timeout()` seconds fails. Total length is still bounded by `max_tokens`,
  so a runaway can't hang either. Also dropped the SDK self-retry (`max_retries` 2→0) so a stall
  can't compound to ~9 min; failures still surface cleanly (selection→web, relevance→fail-open,
  planner/synthesis→exit 4). Record/replay + request hashing unchanged (streaming is internal to
  complete). Proven test-first with an injected fake `anthropic` SDK (3 tests: text stream, tool-use
  JSON from the assembled message, max_retries=0 + timeout wiring); the network path is now covered
  (pragma removed). This is also the streaming plumbing the "stream the answer to the user" task
  (Change 5) will reuse. make verify PASS; decomposition eval still 16/16.

- 2026-07-16 concurrent-waves (Phase 2 — UX: responses faster; serves AC-2 too). The executor
  advertised "(parallel)" waves but ran every subtask serially, and the synchronous Foundry call
  froze the event loop so nothing could overlap anyway. Fix (executor.py): each dependency wave now
  runs its independent subtasks via `asyncio.gather`, bounded by a per-run `asyncio.Semaphore`
  (`ORCHESTRATOR_MAX_CONCURRENCY`, default 5); the two blocking LLM calls (`select_operation`,
  `check_relevance`) are offloaded off the loop with `asyncio.to_thread` so the coroutines genuinely
  overlap. Waves stay sequential, so upstream→downstream data-flow is unchanged. A wave of N
  independent subtasks now finishes in ~1× the per-subtask time, not N×. Proven test-first: 2 new
  tests measure peak concurrency (1→3 unbounded; held at 2 under a cap of 2). make verify PASS;
  decomposition eval still 16/16 (execution-layer change, planner untouched). First of a sequenced
  performance/UX set (next: progress-based AI-call handling, per-run health cache, live progress,
  streamed answer).

- 2026-07-16 llm-call-deadline (Phase 2 — AC-2: nothing may hang). Found live: a
  `--execute` run blocked ~86 min at 0% CPU on a wedged Foundry call. The hard no-hang deadline
  covered app HTTP calls + the async poll loop but NOT the LLM calls (planner/selector/relevance/
  synthesis), which hit the SDK with only its ~10-min default timeout — a hang in practice. Fix:
  `foundry.resolve_llm_timeout()` (default 180 s, override `ORCHESTRATOR_LLM_TIMEOUT_S`) is now
  passed as `timeout=` to the `AnthropicFoundry` client, so a stall raises within a bounded time →
  handled cleanly (selection→web safety net, relevance→fail-open, planner/synthesis→exit 4) instead
  of hanging. Independent of model/credential resolution → record/replay hashes unchanged, no
  fixtures re-recorded. make verify PASS (3 new foundry tests). Also cleared the live mess: killed
  the stuck run (pid 95242) and the wedged arxiv-papers backend (pid 20227), relaunched arxiv on
  :8002 (healthy). FOLLOW-UP for the human: a stalled planner/synthesis call still ends the whole
  run (exit 4) rather than degrading — acceptable (no hang), improvable later via streaming +
  inactivity timeout for true slow≠hung on LLM calls too.

- 2026-07-15 reduce-unwarranted-web-fallbacks (Phase 2 — fewer web fallbacks when the RIGHT app was
  chosen but execution failed; serves AC-1/AC-2). Diagnosis first: live probing showed the planner
  ROUTES well (14/15 messy tasks → correct specialist; only a genuinely-general task → web), so the
  "unexpected web fallbacks" are EXECUTION-stage — the web safety net silently substitutes for a
  chosen app that failed. Three fixes: (1) Relevance guard no longer discards correct answers —
  `grounding.check_relevance` judges the app's FULL output (dropped the 1500-char `_summarize`
  truncation that showed the judge ~5% of a 33 KB dataset preview) under explicit PASS/FAIL rules
  (`relevance_system.md` v2, "Be strict" removed), with a deterministic empty gate (blank output =
  FAIL, no LLM call) and fail-open on any parse/LLM error and on an unknown verdict. (2) Slow ≠ hung:
  `_run_async` no longer gives up on a fixed 600s budget — it keeps polling while the app answers
  (progress), stops early only when the app goes SILENT (`_ASYNC_MAX_SILENT_POLLS`=5 failed polls in
  a row = no progress, a blip is tolerated), and keeps only a generous env-tunable
  `ORCHESTRATOR_ASYNC_MAX_WAIT_S` (default 3600s) as the AC-2 anti-hang backstop; Teach Me
  create_topic/send_user_message sync timeouts raised (180→600, 120→300) since that app exposes no
  status endpoint to poll. (3) Start-all preflight: `launcher.start_all` starts + health-confirms
  every non-fallback app concurrently at the outset (wired into `cli._execute`), printing a
  readiness line (e.g. "Apps ready: 9/11 — unavailable: … will fall back to web") so a dead app is
  never silently invoked. (4) Selector empty-args bug: live, a blog subtask that DEPENDS on an
  upstream step (Teach Me) made the selector return `arguments: {}` (no `topic`) → the blog app
  422'd → web fallback; reproduced deterministically (with-upstream → {}, no-upstream → correct
  topic). Fix: `operation_select_system.md` v3 tells the model to ALWAYS fill the operation's
  primary input from the subtask and treat UPSTREAM as id-only (never a reason to leave the field
  blank); verified live the args flip {} → a real topic. Defense-in-depth: the async start ops now
  declare `required_fields` (generate→[topic], iterate→[blog_id,instruction], start_research→
  [topic]) so a future miss SKIPS with a clear reason instead of a cryptic 422. make verify PASS
  (10 new tests across grounding/executor/launcher/cli/selector).
  VERIFIED LIVE: p-value → Stats Teacher status=ok (no fallback) under the new relevance path.
  NOTE for the human: NOT sealed/pushed — awaiting your review. Deeper follow-ups still open:
  the safety-net still relabels a failed specialist's result app_id as "web-search" (observability),
  and there's no alternate-specialist retry before web.

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
