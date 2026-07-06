# Task: dry-run-orchestrator

<!-- This file IS the plan for this task; drift_check.py enforces the Scope line. -->

Status: DONE
Type: feature
Scope: src/**, tests/**, registry/**, pyproject.toml, requirements-dev.txt, requirements.txt
Phase: Phase 1 (walking skeleton) — maps to AC-1 and AC-3

## Goal

A CLI that takes a natural-language task, recognizes the intent, decomposes it into
smaller subtasks (sequential and parallel), and reports which of the 11 pre-built
apps would handle each subtask — with rationale and confidence. It performs a DRY
RUN only: no app is invoked. This is the thinnest end-to-end slice of AC-1.

## Acceptance criteria

Each one names the test that proves it.

1. CLI prints intent + a subtask DAG (parallel/sequential) + one app per subtask
   with rationale and confidence, and never invokes an app —
   proven by `tests/e2e/scenarios/dry_run_plan.json` (replay).
2. `--json` emits the structured plan (intent, subtasks, task keys) —
   proven by `tests/e2e/scenarios/dry_run_json.json` (replay).
3. Planner/validation/registry/render logic is ≥90% covered offline (no network) —
   proven by the `py-unit` coverage gate over `tests/unit/`.

## Plan (before coding) — built one component at a time, verify+commit each

1. models.py — Plan/Subtask/AppSelection frozen dataclasses (+ to_dict/from_dict). Removes sample calculator.
2. registry/apps.json + registry.py — self-contained app registry (11 apps + web-search fallback) + validating loader.
3. validation.py — parse_plan: JSON/fence handling, schema checks, DAG cycle detection, app_id ∈ registry, denormalize app_name/fallback.
4. llm/base.py + llm/replay.py — LLMClient protocol + LLMRequest; request_hash, ReplayClient, RecordingClient.
5. llm/foundry.py + llm/__init__.py — Foundry creds resolution (env + Blogs Playground/.env fallback) + call; get_client(mode) factory.
6. planner.py + prompts/planner_system.md — build_messages + plan_task (single call, validate, retry ≤2).
7. render.py — human output (dependency waves) + JSON output.
8. cli.py + __main__.py + __init__.py — argparse, wiring, exit codes (0/2/3/4).
9. Record fixtures (one live Foundry call), set e2e.config.json configured=true + agent_cmd, add scenarios, final verify.

## Failure analysis

<!-- none yet -->

## Done

Proof commit: sealed by final verify of this task   Auditor verdict: pending (run `make audit`)   Docs updated: yes (ARCHITECTURE, RUNBOOK, STATE, plan)
