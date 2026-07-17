# Project Constitution — read this first, every session

This project runs under a verification contract between the human and the agent.
The contract is enforced by hooks; these rules explain it. Violating them wastes
everyone's time because the hooks will block you anyway.

*ALWAYS ANSWER IN SIMPLE , CONCISE, DIRECT AND TO THE POINT LANGUAGE TO ME. NO JARGONS, NO LENGTHY ANSWERS* - THIS IS VERY IMPORTANT

## The contract

1. **Evidence, not assertions.** "Done", "fixed", and "works" mean exactly one
   thing: `make verify` PASSED and the proof is sealed (`make seal`). A verbal
   claim of success without a matching proof in `proofs/latest.json` is a
   contract violation.
2. **Plan, then execute.** No code without an active task file
   (`specs/tasks/ACTIVE.md`) containing Goal, Type, Scope, and Acceptance
   criteria. For anything non-trivial, present the plan and wait for approval
   before implementing.
3. **The objective is immutable.** `specs/00-objective.md` defines success. You
   may not edit it. If work stops serving it, stop and say so.
4. **Stay in scope.** Touch only files matching the active task's `Scope:` line.
   Wanting to refactor something unrelated = propose a new task, don't do it.
5. **Bugfix = failing test first.** Reproduce the bug with a test that fails,
   then fix until it passes. A fix without a regression test does not exist.
6. **Small steps.** One task per session. Within a task: edit → verify → commit.
   Never batch an hour of changes before the first verification.
7. **Doom-loop protocol.** If the same check fails 3 times, STOP. Write
   `## Failure analysis` in the active task (what was tried, why it failed, new
   hypothesis) and escalate to the human. Never set `LOOP_ACK` yourself.
8. **Never touch the enforcement layer**: `scripts/`, `githooks/`, `Makefile`,
   `verify.config`, `.proofignore`, `.claude/settings.json`, `.github/workflows/`,
   `proofs/`. Never use `--no-verify`, never force-push, never weaken tests,
   thresholds, or skip/xfail your way to green.
9. **Push only via `make push`** (verify → seal → push). The pre-push hook and CI
   will reject anything else.
10. **Leave a trail.** At task end: update `STATE.md` (done / in progress / next),
    update docs if behavior changed, mark the task file Done with a link to the
    sealed proof commit.

## Session workflow

```
Session start  → anchor is auto-injected (objective, active task, state, proof status)
Pick up ACTIVE task (or ask the human / create one via: make task NAME=...)
Plan the task  → list intended changes + how each acceptance criterion will be tested
Execute        → small edits; hooks auto-lint every file you touch
Verify         → make verify        (writes proof, pass or fail — both are recorded)
Seal & push    → make push          (only sanctioned publish path)
Close out      → update STATE.md + task file; suggest '@auditor' run to the human
```

## Commands (the only ones you need)

- `make verify` — run everything, write proof, auto-seal on pass. The definition of done.
- `make push` — verify (if needed) + seal + push. The only sanctioned publish path.
- `make status` — proof validity, doom-loop state, scope drift.
- `make doctor` — diagnose the harness if anything behaves oddly.
- `make task NAME=x` — start a new task file.

Commit messages are conventional commits: `type(scope): summary`
(feat|fix|docs|refactor|perf|test|build|ci|chore). The commit-msg hook enforces it.

## Project specifics

- Project: A multi agent orchestrator system calling relevant apps basis intent recognition — It recognises user intent, breaks it down into smaller tasks and then calls relevant APPS to complete the task
- Type: agent
- Primary run command: `2`
- E2E approach: agent kit: scenario runner + record/replay pattern for deterministic LLM e2e
- Objective: specs/00-objective.md (4 acceptance criteria — every task serves one)

### Standing context

- ALWAYS BE ACCURATE - DO NOT MAKE STUFF
- NEVER DRIFT FROM THE END OBJECTIVE
- UI needs to be world class, minimalistic and intuitive
- No guesswork - everything is a contract between me and the agent - show proofs
- Simple coding principles beat the most cool ones
- Use glue coding - if there is an existing API or solution that exists, never build that yourself
- Always look for agent harness - so that coding does not drift away from end objective
