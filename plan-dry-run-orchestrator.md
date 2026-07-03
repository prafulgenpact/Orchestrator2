# Plan: Dry-Run Orchestrator (First Feature)

## What we're building

A CLI where you type a task and the orchestrator replies with:
- **Intent** — what it understood you want
- **Subtasks** — the breakdown, showing which run in sequence and which in parallel
- **App per subtask** — which of your 11 apps would be called, with a reason and confidence score
- **No apps are actually invoked** — it ends with "DRY RUN — no apps were invoked."

Example:

```
$ python3 -m orchestrator "plan my week of learning transformers"

Intent: Build a 7-day transformer learning plan.

Step 1 (parallel):
  [t1] Collect course fundamentals      -> Stanford LLM Course  (0.92)
  [t2] Shortlist survey papers          -> ArXiv Paper Guide    (0.88)
Step 2:
  [t3] Hands-on practice (needs t1)     -> Coding Playground    (0.85)

DRY RUN — no apps were invoked.
```

## How it works

- **Brain:** one call to Claude via Anthropic Foundry (same creds your other apps use). Answer comes back as JSON; we validate it and retry up to 2 times if malformed.
- **App knowledge:** a new file `registry/apps.json` inside Orchestrator2 listing your 11 apps + a web-search fallback (descriptions taken from your All Apps setup).
- **Testable without network:** the LLM sits behind a small interface. Tests replay a recorded real response, so `make verify` and CI never need an API key.

## Steps

**Step 1 — Get the scaffold green** (verify currently fails)
1. Fix the two wizard typos: `COVERAGE_MIN=90%` → `90`, e2e `agent_cmd: "2"` → `python3 -m orchestrator`
2. Auto-format the scaffold's own files (`ruff format`), upgrade pytest to fix a CVE
3. First commit + first PASS proof

**Step 2 — Build the feature**
1. Create `registry/apps.json` (11 apps + fallback)
2. Build the `orchestrator` package in `src/`: LLM client, planner, plan validator, CLI printer (replaces the sample calculator.py)
3. Write unit tests (90% coverage, no network) + 2 end-to-end scenarios (replay mode)
4. Record the test fixture with one real Foundry call, commit everything, `make verify` green

## How you'll verify it

```bash
make verify                                          # all checks green, PASS proof
python3 -m orchestrator "plan my week of learning transformers"   # see the real thing
```

## Notes

- Two of the fixes touch harness-owned files (verify.config, scripts/) — approving this plan sanctions that.
- Needs your Foundry credentials working once, to record the test fixture.
