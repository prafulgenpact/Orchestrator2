# Agentic Development Playbook

How this scaffold keeps AI-driven development honest, on course, and repeatable.

The core idea, applied everywhere: **never trust an agent's verbal claim; trust
only machine-generated artifacts bound to the exact code they verified.** Every
rule below is enforced by a hook or script, not by asking the agent nicely.

## The proof contract (read this first)

The unit of trust is a **proof**: a JSON file written only by `make verify`.

- `scripts/verify.sh` runs every check (lint, format, types, unit, e2e) and
  records each result with its evidence log.
- `scripts/gen_proof.py` seals the results into `proofs/latest.json` with:
  a **code fingerprint** (sha256 over every code file's git blob hash — change
  one byte and the proof is stale), test counts, coverage, tool versions, and a
  **content hash** (hand-editing the proof is detected — forgery-evident).
- `scripts/check_proof.py` is the single validator used by the pre-push git
  hook, the agent's Bash/Stop gates, `make seal`, and CI.
- FAIL runs produce proofs too (`proofs/history/`) — that history is what the
  doom-loop detector reads.

Three enforcement layers, each catching what the previous can miss:

| Layer | Mechanism | Catches |
|---|---|---|
| 1. Agent hooks | `.claude/settings.json` → gate/lint/stop scripts | violations at the moment the agent acts, with instant feedback into its context |
| 2. Git hooks | `githooks/pre-commit`, `pre-push` | anything that reaches git, from any tool (Claude Code, Codex, Windsurf, a human) |
| 3. CI (GitHub Actions) | `.github/workflows/verify.yml` + branch protection | local bypasses (`--no-verify`, edited hooks) — the server re-verifies everything from scratch |

## The 12 requirements → mechanisms

### 1. No context rot

The objective cannot decay because it is re-injected, not remembered.

- `specs/00-objective.md` — immutable north star with acceptance criteria,
  written before any code. The agent's Edit tool is blocked from touching it.
- SessionStart hook (`scripts/session_brief.sh`) re-injects objective + active
  task + `STATE.md` + proof status into **every** session automatically.
- One task per session, tasks sized ≤ ~90 minutes. Long sessions rot; prefer a
  fresh session + `STATE.md` over compaction.
- `STATE.md` is the cross-session memory: updated at every task end (rule 10 of
  the constitution), so a fresh session loses nothing that matters.

### 2. No doom loop

A false "it's fixed" cannot survive contact with this system.

- "Fixed" has exactly one meaning: `make verify` PASS on the current code. The
  Stop hook (`scripts/stop_gate.sh`) blocks the agent from ending its turn with
  unverified changes — it is forced to run verify or report failure honestly.
- Every verify run (pass or fail) is recorded. `scripts/loop_detector.py` reads
  the history: 3 consecutive FAILs on the same check ⇒ verification locks,
  the agent must write `## Failure analysis` in the task file, and only a human
  can unlock (`make verify LOOP_ACK=1`). The Bash gate blocks agents from
  setting `LOOP_ACK` — escalation to you is mandatory, by construction.
- Bugfix tasks require a regression test (drift_check flags source-only
  "fixes"). E2E tests catch "units pass but the feature is still broken".

### 3. Linters + security lane

- Python: ruff (lint + format) + mypy strict. Web: eslint + prettier + tsc
  strict. Config in `pyproject.toml` / `web.template/`.
- Three trigger points: PostToolUse hook lints **every file the moment the
  agent writes it** (auto-fixes, feeds leftovers back for immediate repair);
  pre-commit lints staged files; verify runs the full suite as required checks.
- Security lane in every verify + pre-commit: `secrets` (stdlib scanner — AWS
  keys, private keys, tokens, hardcoded passwords; required check by default;
  gitleaks used additionally if installed), `dep-audit` (pip-audit against
  known CVEs), `diff-cover` (changed-lines coverage so NEW code can't ship
  untested; set `DIFF_COVERAGE_MIN` to make it a floor). Suppressions are
  explicit and reviewable: `.secretsallow`, `DEP_AUDIT_ARGS` in verify.config.

### 4. Plan → then → execute

- Project level: `specs/00-objective.md` (what) → `specs/plan.md` (phases with
  verifiable exit criteria) → phase gate ritual (proof + audit before the next
  phase starts).
- Task level: `make task NAME=x` creates the task file from
  `specs/tasks/TEMPLATE.md`; Goal/Type/Scope/Acceptance must be filled **before
  code**. Mechanically enforced: `gate_edit.sh` blocks agent code edits while no
  `specs/tasks/ACTIVE.md` exists (planning/docs edits remain allowed;
  `REQUIRE_ACTIVE_TASK=0` disables). The constitution additionally requires the
  agent to present its plan and wait; in Claude Code use Plan Mode (shift+tab)
  for the analysis phase.

### 5. Hooks (the contract, auto-triggered)

| Event | Script | Enforces |
|---|---|---|
| SessionStart | `session_brief.sh` | context re-anchoring (req 1) |
| PreToolUse: Bash | `gate_bash.sh` | no push without proof, no `--no-verify`, no `LOOP_ACK`, no force-push, no proof forgery via shell |
| PreToolUse: Edit/Write | `gate_edit.sh` | enforcement files, objective, and `proofs/` are untouchable |
| PostToolUse: Edit/Write | `lint_file.sh` | instant lint/format of every touched file (req 3) |
| Stop | `stop_gate.sh` | no "done" without a matching PASS proof (req 2) |
| git pre-commit | `githooks/pre-commit` | staged files lint-clean |
| git pre-push | `githooks/pre-push` | push carries a committed, tamper-checked, fingerprint-matching PASS proof (req 6) |

The "proof of testing" you asked for is `proofs/latest.json` — machine-generated,
content-hashed, code-fingerprinted. A verbal confirmation cannot satisfy any gate.

### 6. Git push only when tests pass

- `githooks/pre-push` reads the proof **from the commit being pushed**
  (`git show <sha>:proofs/latest.json`) and validates: PASS result, intact
  content hash, fingerprint == that commit's code. Stale, forged, uncommitted,
  or FAIL proofs ⇒ push rejected.
- On a PASS with a clean tree, `make verify` **auto-seals** the proof
  (AUTOSEAL=1 default) — the flow collapses to: commit → `make verify` →
  `git push`. `make push` chains it all when you prefer one command.
- The agent-side Bash gate blocks `git push` even earlier with an actionable
  message. `githooks/commit-msg` additionally enforces conventional commits
  (`type(scope): summary`) for machine-readable history.
- Server side: make both CI jobs required checks (§9) so even a bypassed local
  hook cannot land unverified code on main.

### 7. Harness (staying on course between iterations)

- The Makefile is the harness: agents and humans use the same five commands
  (`verify`, `seal`, `push`, `status`, `task`) — no improvised procedures.
- `CLAUDE.md` is the constitution: small steps, one task per session, in-scope
  only, evidence not assertions. Hooks make the important rules physical.
- Rhythm per task: plan → small edit → verify → commit → … → seal → push →
  audit. The cheapest way to stay on course is verifying every few minutes.

### 8. Testing (unit + e2e, auto-executed, with proof)

- `tests/unit/` (pytest + coverage ≥ `COVERAGE_MIN`, junit XML) and
  `tests/e2e/` (pytest; Playwright via `web/` for browser flows) both run in
  every `make verify` and in CI — they are REQUIRED_CHECKS, so a proof cannot
  be PASS without them.
- Proof of testing = `proofs/latest.json` (counts, coverage, durations) +
  `reports/junit-*.xml` + per-check logs, uploaded as CI artifacts (90 days).
- A required check that gets skipped (tool missing, test dir deleted) fails the
  proof — silently disabling tests is not possible.

### 9. Enforcement

- Layers 1-3 above. Agents are mechanically blocked from editing the
  enforcement layer itself (`scripts/`, `githooks/`, `Makefile`,
  `verify.config`, `.proofignore`, `.claude/settings.json`, workflows, proofs).
- The tamper-proof back-stop is server-side. On GitHub enable branch protection
  for `main`: Settings → Branches → Add rule → require status checks
  **`audit committed proof (contract)`** and **`independent re-verification`**,
  require PRs, disallow force pushes. Also set **squash merging only**
  (Settings → General → Pull Requests): proofs bind to exact trees, and a true
  merge commit creates a combined tree that was never verified — squash/FF
  merges preserve the verified tree. After that, nothing unverified can merge
  even if every local control was defeated.

### 10. Deviation detection (independent assessment)

- Mechanical: `scripts/drift_check.py` compares every changed file against the
  active task's declared `Scope:` globs — runs inside verify (blocking with
  `STRICT_SCOPE=1`) and in `make status`.
- Judgment: the **auditor subagent** (`.claude/agents/auditor.md`) — a fresh
  context, read-only reviewer that checks the diff against the objective, plan,
  and task; sweeps for weakened tests (skips, xfails, deleted assertions,
  lowered thresholds); verifies the proof; and returns a structured verdict
  (`ON_TRACK / DRIFT_MINOR / DRIFT_MAJOR / EVIDENCE_MISSING`). Fresh context is
  the point: it cannot inherit the builder's rationalizations.
- Cadence: after every task, at every phase gate, on every PR (verdict pasted
  into the PR template), and any time your instincts itch.

### 11. Deterministic, repeatable cycle

- Pinned everything: `requirements-dev.txt` (exact versions), `package-lock.json`
  via `npm ci`, pinned CI runner setup, `.devcontainer/` for an identical local
  environment.
- Fixed execution: same checks, same order, same flags every run; `TZ=UTC`,
  `PYTHONHASHSEED=0`, seeded randomness in tests; pytest cache disabled.
- Same entrypoints everywhere: `make verify` behaves identically on your
  laptop, the agent's shell, and CI. Proofs make repeatability *observable*:
  identical code ⇒ identical fingerprint ⇒ comparable runs.
- Single-flight lock (`.verify.lock`) — concurrent verifications can't corrupt
  reports or interleave proofs. `make doctor` diagnoses environment drift
  (installed tool versions vs pins) in one command.
- Agent nondeterminism is fenced, not fixed: you cannot make an LLM
  deterministic, so the cycle is deterministic *around* it — whatever path the
  agent takes, it must exit through the same gates.

### 12. Documentation

- Templates that force substance: `docs/ARCHITECTURE.md`, `docs/RUNBOOK.md`,
  `docs/HANDOVER.md` (a new engineer productive in a day), `docs/decisions/`
  ADRs, `CHANGELOG.md`, and living `STATE.md`.
- Kept honest by process: constitution rule 10 (docs updated at task end), the
  PR template checkbox, and the auditor flagging behavior changes without doc
  changes. Docs changes don't invalidate proofs (`.proofignore`), so there is
  no friction excuse.

## How E2E testing actually works (per project type)

The harness enforces THAT e2e runs and produces proof; the tests' substance
comes from your acceptance criteria. Division of labor: **the objective's ACs
define what to prove** (project level), **each task file names the test that
proves each of its criteria** (task level), **the coding agent writes the
tests** as part of every task (constitution: bugfix = failing test first;
acceptance criteria must name their proving test), **you review tests harder
than code** (they are the contract's substance), and **the auditor checks the
suite wasn't weakened** and that ACs actually map to tests.

`init.py` installs a starter harness matched to the project type so "write an
e2e test" means filling a template, not inventing infrastructure:

| Type | Kit | What a test does |
|---|---|---|
| API / service | session fixture boots your real service; tests hit real HTTP | POST a thing, GET it back, assert round-trip + failure paths |
| Web app | API kit + Playwright (activate `web/`) | drive a real browser through user flows |
| CLI | subprocess runner against the real entrypoint | run commands as a user would; golden-file outputs |
| Agentic AI system | scenario runner: `tests/e2e/scenarios/*.json` | scripted run of the real agent; assert exit code, must-contain output, produced files, JSON structure |
| Library | fresh-interpreter consumer test | use the public API exactly as a consumer would |

Agentic systems get special determinism treatment (the LLM is the nondeterminism):
temperature 0 / fixed seeds; **recorded model responses** for CI (record once,
replay forever — pattern in `tests/e2e/fixtures/README.md`); assertions on
structure and facts (files produced, keys present, must-contain strings), never
on exact model prose; one live-model smoke scenario kept out of CI (nightly).
Unconfigured kits skip visibly — skip counts appear in the proof, so a hollow
e2e lane is evidence, not silence, and the auditor flags it.

## Daily workflow (the whole loop)

```
make task NAME=payment-retry      # 1. task file: goal, scope, acceptance criteria
<agent plans; you approve>        # 2. plan-then-execute
<agent codes in small steps>      # 3. hooks lint every edit, gates watch every command
make verify                       # 4. proof written (agent is forced to anyway)
make push                         # 5. seal + push (pre-push + CI validate the contract)
make audit                        # 6. independent verdict; paste into PR
<update STATE.md, merge>          # 7. context preserved for the next session
```

## New project setup

`python3 init.py` (or `make init`) automates all of this interactively: it asks
what you're building, for whom, the acceptance criteria (each becomes a test),
out-of-scope drift magnets, constraints, project type, and contract knobs —
then writes the objective, seeds a walking-skeleton plan, fills the agent's
context in CLAUDE.md, installs the type-matched E2E kit, initializes git with
hooks, makes the first commit, and runs verification for proof #1.

Manual equivalent, if you prefer:

1. Copy this scaffold into an empty repo (`git init`).
2. `make bootstrap` (installs toolchain + activates git hooks).
3. Write `specs/00-objective.md` — acceptance criteria first, this is the step
   that prevents drift for the whole project. Sketch phases in `specs/plan.md`.
4. `make verify` → the sample code goes green and the first proof exists.
   `make task NAME=first-real-task`, delete the sample as part of it.
5. Push to GitHub; enable branch protection with both required checks (§9).
6. Frontend? Follow `web.template/README.md`.

## Using agents other than Claude Code

Layers 2 (git hooks) and 3 (CI) are tool-agnostic — the contract holds for
Codex, Windsurf, or a human with vim, because it lives in git and the server.
For layer 1: give any agent `CLAUDE.md` as its system/rules file (Windsurf:
`.windsurfrules`; Codex: `AGENTS.md` — symlink it). For LangGraph/CrewAI
builders: expose `make verify` / `make status` as tools and treat exit codes as
the contract; run the auditor prompt as a separate reviewer agent with a clean
context.

## Scaffold lifecycle

The scaffold is versioned (`VERSION`, currently 1.1.0). When a newer scaffold
exists, propagate improvements into any derived project with
`bash scripts/update_from_scaffold.sh <newer-scaffold-dir> [--apply]` — dry-run
shows diffs; apply backs up to `.scaffold-backup/` and overwrites only
harness-owned files listed in `scaffold.manifest`. Your specs, code, and tuned
configs are never touched. After updating: `make verify`, review, commit as
`chore: scaffold <version>`.

## Escape hatches (humans only, deliberately)

- Doom-loop unlock: `make verify LOOP_ACK=1` after reviewing the failure analysis.
- Emergency push without proof: `git push --no-verify` — CI will still fail the
  branch, which is exactly the paper trail you want an emergency to leave.
- Relax a gate: edit `verify.config` / `.claude/settings.json` yourself; agents
  cannot.
