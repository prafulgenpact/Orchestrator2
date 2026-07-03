# Runbook

<!-- Operational knowledge: how to run, debug, and recover the system.
     If you had to figure something out the hard way, it goes here. -->

## Run locally

```
make bootstrap
<project-specific run command>
```

## Verify & publish

```
make verify   # full check suite -> proof
make push     # verify (if needed) + seal + push
make status   # proof / doom-loop / drift state
```

## Environments & secrets

Where config lives, which env vars matter, where secrets come from (never in git).

## Common failures

| Symptom | Likely cause | Fix |
|---|---|---|
| pre-push blocked: STALE proof | code changed after verify | `make verify && make seal` |
| pre-push blocked: no committed proof | forgot seal | `make seal` |
| verify blocked: DOOM LOOP | 3+ fails on same check | write failure analysis, human runs `make verify LOOP_ACK=1` |
| CI proof-audit fails but local passed | proof not committed / local bypass | `make push` from a clean tree |

## Recovery procedures

Backups, rollbacks, data fixes — fill in per project.
