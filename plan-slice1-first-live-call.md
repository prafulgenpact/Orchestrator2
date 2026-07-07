# Plan: Slice 1 — first live, grounded end-to-end call

## Goal

Type a task and get a REAL answer from a REAL app. The thinnest full loop:
task → plan → call one live app → grounded answer. Proves the hardest bridge (actually
calling an app) works end-to-end.

## Demo target

**ArXiv Paper Guide** — it is already running (port 8002) and needs no app API key for search.
Example: `find recent papers on mixture-of-experts` → orchestrator calls the real arXiv search →
shows real papers (title + link).

## Steps (each = code → `make verify` → commit)

1. **App-caller** (`app_caller.py`): find the app's live port via the launcher (`/api/apps`),
   health-check it, then make one HTTP call wrapped in the block-B safety layer (deadline +
   retry + circuit breaker). Returns the app's real result + where it came from. Tested against
   a local fake app (no network in CI).
2. **Executor** (`executor.py`, minimal): run the plan's subtasks in order. For each, one small
   structured LLM call picks which operation to call and its arguments (grounded in the app's
   real operations — no guessing), then calls it via the app-caller. Collects the results.
3. **CLI `--execute`** + hermetic test: add `--execute` (dry-run stays the default). One
   end-to-end replay test (recorded LLM + recorded arXiv response) so `make verify` stays
   key-free.

## Kept in (thin) — the core promise

- Grounded: the answer is the app's real output, shown with its source. No made-up content.
- No-hang: every call uses the block-B deadline/retry/breaker.

## Deferred (later slices)

Full multi-app synthesis + voice (E), observability dashboard (F), web-search fallback,
the trickier apps (WebSocket kernel, SSE, async-poll), security/scaling.

## How you'll test it

```bash
# live (needs Foundry key for planner+selector; arXiv app already running):
PYTHONPATH=src python3 -m orchestrator --execute "find recent papers on mixture-of-experts"

# hermetic (no key, proves it in CI):
make verify
```
