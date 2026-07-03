# A multi agent orchestrator system calling relevant apps basis intent recognition

It recognises user intent, breaks it down into smaller tasks and then calls relevant APPS to complete the task

Built on the agentic verification scaffold — process docs in PLAYBOOK.md.

A verification harness for AI-agent-driven development. Agents claim; proofs
convince. No push without a machine-generated, tamper-evident, code-bound
PASS proof of linting, typing, unit and e2e tests.

**Read `PLAYBOOK.md`** for how every mechanism works and why.

## Quick start

```bash
# in a fresh copy of this scaffold
python3 init.py         # interactive setup: asks about YOUR project, then
                        # writes the objective, seeds the plan, installs the
                        # E2E kit for your project type, git init + hooks
make bootstrap          # pinned toolchain (ruff/mypy/pytest)
make verify             # green; first proof written
```

The wizard asks: what you're building and for whom, acceptance criteria (each
becomes a test), out-of-scope items (the drift magnets), project type (which
selects the E2E harness: API / web / CLI / agentic-scenario / library),
coverage bar, and strictness. Manual setup still works — see PLAYBOOK.md.

## Layout

```
CLAUDE.md               agent constitution (rules the hooks enforce)
PLAYBOOK.md             how the whole harness works — start here
specs/                  objective (immutable) / plan / task files
STATE.md                living cross-session memory
scripts/                verification + enforcement (agents cannot edit)
githooks/               pre-commit lint, pre-push proof gate
proofs/                 machine-generated proof-of-testing (the audit trail)
.claude/                Claude Code hooks config + auditor subagent
.github/workflows/      CI: proof audit + independent re-verification
docs/                   architecture / runbook / handover / ADRs
verify.config           the contract knobs (required checks, coverage, strictness)
```

## The commands

```
make verify   # run everything, write proof, auto-seal on pass — the definition of done
make push     # verify (if needed) + seal + push
make status   # proof validity / doom-loop / drift
make doctor   # diagnose env, toolchain-vs-pins, hooks, contract state
make task     # NAME=x — start a new task file
make audit    # independent fresh-context drift audit
```

## Platform support

Linux and macOS (bash 3.2+, git ≥ 2.9, python ≥ 3.10). On Windows use WSL2 or
the included `.devcontainer/`. `make doctor` verifies your setup in one command.

## Updating a project when the scaffold improves

```
bash scripts/update_from_scaffold.sh /path/to/newer-scaffold          # dry run (diffs)
bash scripts/update_from_scaffold.sh /path/to/newer-scaffold --apply # backup + apply
```

Only harness-owned files (`scaffold.manifest`) are touched — your code, specs,
and tuned configs are never overwritten.
