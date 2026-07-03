# Master Plan — A multi agent orchestrator system calling relevant apps basis intent recognition

Objective: see specs/00-objective.md (immutable). Base branch: Orchestrator2.
A phase is complete only when its exit criterion is verified (sealed PASS proof
+ auditor ON_TRACK).

## Phase 1 — Walking skeleton

- Exit criterion: the thinnest end-to-end slice of AC-1 works and the e2e
  harness proves it (e2e configured, first real scenario/flow green).
- Maps to: AC-1
- Tasks:
  - [ ] 20260703-walking-skeleton — replace sample code, wire e2e kit to the real thing
- Status: not started

## Phase 2 — Core build

- Exit criterion: all acceptance criteria (AC-1, AC-2, AC-3, AC-4) have passing tests.
- Maps to: AC-1, AC-2, AC-3, AC-4
- Tasks:
  - [ ] (break down when Phase 1 ships)
- Status: not started

## Phase 3 — Hardening & handover

- Exit criterion: docs complete (ARCHITECTURE/RUNBOOK/HANDOVER), coverage at
  bar, auditor ON_TRACK on the full diff.
- Status: not started

## Phase gate ritual (every phase end)

1. `make verify` green, `make seal`, push.
2. `make audit` — verdict pasted below the phase.
3. Human reviews verdict; only then does the next phase start.
