# Handover Guide

<!-- The "hit by a bus / moved to another project" document. A competent engineer
     with zero context should be productive within a day using only this repo. -->

## Read in this order (≈1 hour)

1. `specs/00-objective.md` — what this project is and when it's done
2. `STATE.md` — where it stands right now
3. `specs/plan.md` — the phases and what's left
4. `docs/ARCHITECTURE.md` — how it's built
5. `PLAYBOOK.md` — how the development process itself works (the contract)
6. `docs/RUNBOOK.md` — how to run and fix it

## Get productive (≈15 min)

```
git clone <repo> && cd <repo>
make bootstrap        # installs toolchain + git hooks
make verify           # must be green on main — if not, that IS the first task
make status
```

## The development contract (summary)

Every change: task file first → small edits → `make verify` → `make push`.
Proofs in `proofs/` are the audit trail of every verification ever run.
Agents operate under `.claude/settings.json` hooks + `CLAUDE.md` rules.
`make audit` gives an independent drift assessment — run it if anything feels off.

## People & access

| What | Where / who |
|---|---|
| Repo & CI | … |
| Secrets | … |
| Domain questions | … |
| Deployment | … |

## Current risks / sharp edges

Honest list. The things you'd warn a friend about.
