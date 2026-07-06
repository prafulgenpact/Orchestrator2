# Runbook

<!-- Operational knowledge: how to run, debug, and recover the system.
     If you had to figure something out the hard way, it goes here. -->

## Run locally

```
make bootstrap                 # install pinned toolchain + anthropic, install hooks

# Live plan (calls Foundry; needs credentials — see below):
PYTHONPATH=src python3 -m orchestrator "plan my week of learning transformers"
PYTHONPATH=src python3 -m orchestrator --json "…"     # machine-readable plan

# Deterministic offline plan (serves a recorded fixture, no network/key):
PYTHONPATH=src AGENT_LLM_MODE=replay python3 -m orchestrator "plan my week of learning transformers"
```

Flags: `--json`, `--model`, `--registry PATH`, `--mode {live,record,replay}`,
`--max-retries N`. Exit codes: 0 ok, 2 usage, 3 config/registry/credential error,
4 planning failure.

## Record / re-record e2e fixtures

The e2e scenarios replay a recorded model response. To (re)record after changing the
prompt, registry, model, or task, make one live call from the repo root:

```
PYTHONPATH=src AGENT_LLM_MODE=record python3 -m orchestrator "plan my week of learning transformers"
```

This writes `tests/e2e/fixtures/<hash>.json` (request + response text only — no keys).
Commit it. The fixture key is a hash of the request, so any change to prompt/registry/
model/task produces a new key; a replay miss means "re-record".

## Verify & publish

```
make verify   # full check suite -> proof
make push     # verify (if needed) + seal + push
make status   # proof / doom-loop / drift state
```

## Environments & secrets

Foundry credentials: `ANTHROPIC_FOUNDRY_API_KEY`, `ANTHROPIC_FOUNDRY_BASE_URL`. Read
from the environment first, else from `../Blogs Playground/backend/.env`. Override the
fallback path with `ORCHESTRATOR_FALLBACK_ENV`. Model: `--model` > `ORCHESTRATOR_MODEL`
> default (`claude-opus-4-6`). Never commit keys; fixtures store only response text.

## Common failures

| Symptom | Likely cause | Fix |
|---|---|---|
| exit 3 "missing Foundry credentials" | no key/base URL | set the env vars or point `ORCHESTRATOR_FALLBACK_ENV` at a .env |
| exit 4 "did not produce a valid plan" | model output invalid after retries | inspect stderr; re-run; raise `--max-retries` |
| e2e: MissingFixtureError | request changed vs recording | re-record (see above) and commit the fixture |
| pre-push blocked: STALE proof | code changed after verify | `make verify && make seal` |
| verify blocked: DOOM LOOP | 3+ fails on same check | write failure analysis, human runs `make verify LOOP_ACK=1` |

## Recovery procedures

Stateless (dry run only) — no data to back up or roll back. To reset a wedged
environment: `make clean && make bootstrap && make verify`.
