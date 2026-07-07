# Plan: Invoke the Apps (Phase 2)

## What we're building

Today the orchestrator only *plans* — it decomposes a task, picks the right app per subtask, and
stops ("DRY RUN — no apps were invoked."). This phase makes it **actually call the apps**, combine
their answers, and hand you a grounded result — while guaranteeing it can never hang and never
makes anything up.

Same command, new `--execute` flag:

```
$ python3 -m orchestrator --execute "summarize the latest mixture-of-experts papers and draft a blog"

Intent: Find recent MoE papers, then draft a blog post about them.

Step 1 (parallel):
  [t1] Find recent MoE papers        -> ArXiv Paper Guide   (0.91)   ✓ 2.3s  (5 papers)
  [t2] Pull latest AI news on MoE    -> AI Intelligence Deck (0.74)  ✓ 1.1s
Step 2:
  [t3] Draft blog from t1+t2         -> Blogs Playground     (0.88)  ✓ 41s   (streamed)

Answer:
  <Blogs Playground's draft, passed through verbatim in your voice>

Sources: arXiv:2401.xxxxx, arXiv:2312.xxxxx, … (every claim traces to an app result)
Trace:   runs/2026-07-07T…/run.sqlite   (full lineage, auditable)
```

If an app is slow or down, that subtask times out cleanly ("app X timed out — continuing") and the
run still finishes with partial results. It never blocks.

## How it works

- **Calling the apps — direct HTTP, not MCP.** The 11 apps are already FastAPI backends
  (ports 8001–8011) with OpenAPI specs. The orchestrator calls those HTTP endpoints directly
  through one small "app-caller" layer, and exposes each app to Claude as a native tool. This is
  the simplest, most reliable, most controllable option for a fixed, local set of apps — we get
  full control over timeouts, grounding, and provenance. (MCP would only pay off if you wanted
  outside clients like Claude Desktop to call these apps; if that ever comes up we'd auto-generate
  MCP from the OpenAPI specs, never hand-write it.)
- **Never hangs.** Every app/LLM call is wrapped in a hard wall-clock deadline (`asyncio.wait_for`)
  — because plain HTTP timeouts are per-chunk, not total, so they *don't* stop a slow trickle.
  On top: classify errors → bounded retry with backoff+jitter → per-app circuit breaker → an
  overall run budget that cancels stragglers and returns partial results.
- **Never makes things up.** The final answer is built **only** from what the apps and web search
  actually returned. Each app's answer is passed through **verbatim** (they're already tuned to
  your voice — we don't rewrite them), and failures are reported honestly, never papered over.
  Every claim carries provenance.
- **Fully traceable.** Every run writes an append-only SQLite event log (which app, which model,
  prompt hash, timings, sources) — the data source for the leadership dashboard in the next phase.
- **Built fresh.** No code is copied from the old `All Apps` / `Orchestrator` attempts — those had
  standards debt. We reuse only the *running apps' HTTP APIs*. Everything in the orchestrator is
  written clean to this repo's standards and lands under `make verify`.
- **Brain:** upgraded to `claude-opus-4-8` (from 4.6), adaptive thinking + effort, streaming for
  long generations. Tests still replay recorded responses — no network/keys in CI.

## Steps (small capabilities — each is edit → `make verify` → commit)

**A. Registry & app contracts**
- **A1** — Add a per-capability call-spec to the registry (`method`, `path`, `port`, `health`,
  `timeout_s`, `retry`, `destructive`, `idempotency`).
- **A2** — Fill in accurate contracts for all 11 apps from each app's live `/openapi.json`
  (never guessed), including the quirky ones (odd health paths, SSE, WebSocket kernel).

**B. Reliability primitives — new `resilience.py`, built fresh (AC-2)**
- **B1** — Wall-clock deadline on every call + a forced-hang test that proves it fires.
- **B2** — Error classifier → retry / fatal / auth.
- **B3** — Bounded retry (≤2) with exponential backoff + jitter (retry-class only).
- **B4** — Per-app circuit breaker (a dead app is skipped and reported, not hammered).

**C. Calling one app — new `app_caller.py`**
- **C1** — Bounded health check + cold-start (fail-fast; can't wedge a run).
- **C2** — A single grounded app call (composes B1–B4 + idempotency key), returning a typed
  result with provenance. Tested against a local mock FastAPI.

**D. Executing a plan — new `executor.py`**
- **D1** — Immutable `PlanResult` / `SubtaskResult` models.
- **D2** — Sequential DAG execution in dependency order (reuses existing wave logic).
- **D3** — Intra-wave concurrency under a cap.
- **D4** — Total-run budget → cancel + return partial results (never hangs).
- **D5** — Web-search fallback (native citations) for subtasks no app covers.

**E. Grounding & voice — new `synthesis.py` (accuracy + AC-4)**
- **E1** — Strictly-grounded synthesis (answer only from sources; test asserts no ungrounded text).
- **E2** — Verbatim passthrough of each app's tuned answer, attributed.
- **E3** — Honest surfacing of failed / empty / refused calls.
- **E4** — A minimal in-repo voice profile (you provide the content) for the orchestrator's own
  connective text.

**F. Observability — new `trace.py`**
- **F1** — Append-only SQLite event log with full provenance per run/subtask/call.
- **F2** — JSON trace export (feeds the next-phase leadership dashboard).

**G. Wire-up & proof**
- **G1** — Model + streaming upgrade (`claude-opus-4-8`, adaptive thinking/effort).
- **G2** — CLI `--execute` path (dry-run stays the default, so the sealed Phase-1 proof is safe).
- **G3** — Hermetic end-to-end scenarios: data app (ArXiv), long-running LLM app (Blogs), grounded
  tutor (Stanford/Stats), forced-timeout, web-fallback.
- **G4** — Live smoke run against real apps + docs update (ARCHITECTURE.md, STATE.md, RUNBOOK.md).

## How you'll verify it

```bash
make verify                                   # all checks green, ≥90% coverage, PASS proof
python3 -m orchestrator --execute "…"         # real run: apps called, grounded answer, sources
# inspect runs/<ts>/run.sqlite                # full, auditable lineage of the run
```

- **No-hang proof:** a forced-timeout scenario shows the run completes with "app X timed out —
  continuing" inside the deadline.
- **Accuracy proof:** tests assert app outputs appear verbatim + attributed, and every synthesis
  claim maps to a recorded source (no ungrounded text).
- **Right-app proof:** replay scenarios show the correct app invoked per subtask; web-search used
  only when no app fits.

## Notes

- Each capability is its own task file + proof (small steps, per the constitution).
- `--execute` is opt-in; dry-run remains the default so Phase-1's sealed behaviour is untouched.
- CI stays hermetic (mock app / recorded fixtures); live apps need their own LLM keys and are only
  touched in G4.
- Nothing is reused from prior attempts' code — clean build to this repo's standards.
