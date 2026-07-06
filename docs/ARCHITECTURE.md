# Architecture

<!-- Keep current — the auditor and every new joiner reads this. Update in the
     same PR as any structural change (the constitution requires it). -->

## System overview

The dry-run orchestrator turns a natural-language task into a plan and reports which
of the pre-built apps would handle each part — without invoking any app.

```
task ─▶ cli ─▶ planner ──(LLMRequest)──▶ LLM client ─▶ Anthropic Foundry
                  │                          │  (replay: recorded fixture)
                  ▼                          ▼
             registry (apps.json)      validation (JSON→Plan, DAG + app checks)
                  │                          │
                  └──────────▶ render (human waves / JSON) ─▶ stdout
```

One LLM call does both decomposition and app selection. The response is validated
into an immutable `Plan`; the renderer groups subtasks into dependency "waves" so
parallel vs sequential steps are visible. Nothing calls an app (AC-1 walking slice).

## Components

| Component | Responsibility | Entry point | Depends on |
|---|---|---|---|
| CLI | parse args, wire everything, exit codes | `src/orchestrator/cli.py` | llm, planner, registry, render |
| Planner | one model call + bounded validation retries | `src/orchestrator/planner.py` | llm.base, validation, registry, models |
| Validation | JSON → `Plan`; schema, DAG (no cycles), app_id checks | `src/orchestrator/validation.py` | models, registry |
| Registry | load/validate the app catalog | `src/orchestrator/registry.py` + `registry/apps.json` | — |
| Models | immutable `Plan`/`Subtask`/`AppSelection` | `src/orchestrator/models.py` | — |
| LLM layer | `LLMClient` protocol; Foundry, replay, record | `src/orchestrator/llm/` | anthropic (live only) |
| Render | human dependency-wave view + JSON | `src/orchestrator/render.py` | models |

## Key flows

1. **Plan a task** (`cli.main`): load registry → `get_client(mode)` → `plan_task`
   builds one `LLMRequest` (system prompt + registry JSON + task) → client returns
   text → `parse_plan` validates into a `Plan` (retrying on invalid) → render.
2. **Determinism / replay**: `request_hash` (canonical JSON → sha256) keys a fixture
   under `tests/e2e/fixtures/`. `RecordingClient` writes it on a live call;
   `ReplayClient` serves it — so tests, e2e, and CI run with no network and no key.
   The request model is resolved independently of credentials so record and replay
   hash identically.

## External services & integrations

Anthropic Foundry (LLM). Auth: `ANTHROPIC_FOUNDRY_API_KEY` + `ANTHROPIC_FOUNDRY_BASE_URL`
from the environment, falling back to `../Blogs Playground/backend/.env`
(override with `ORCHESTRATOR_FALLBACK_ENV`). Only `live`/`record` modes call it;
missing credentials raise a clear error and exit 3. The SDK is imported lazily.

## Decisions

- Single provider (Anthropic Foundry), single structured call, client-side
  validation + retry (Foundry structured-output support is not relied upon).
- Self-contained `registry/apps.json` (no runtime coupling to the launcher).
