# Task: observability-report-command

Status: DONE
Type: feature
Scope: src/orchestrator/observability.py, src/orchestrator/cli.py, tests/unit/test_observability.py, tests/unit/test_cli.py, docs/RUNBOOK.md, STATE.md
Phase: Observability — one-command live report (plan: ~/.claude/plans/i-need-to-build-validated-prism.md)

## Goal

One command runs a real task and then prints the full observability report, so all of it —
KPIs, cost/tokens per model, quality, health alerts, per-app usage, recent runs, and this run's
per-step drill-down — is visible in a single terminal view with real numbers. Delivered as a
`--report` flag on the normal run (`--execute --report "<task>"`) plus a standalone
`orchestrator runs report` for viewing the store any time. Read-only aggregation over the store we
already built; no LLM/executor change, so eval stays 16/16.

## Acceptance criteria

Each one names the test that proves it.

1. `render_report(kpis, alerts, recent, run_detail=None)` composes one report string with clearly
   labelled sections (Summary/Cost/Quality/Alerts/Per-app/Recent/this-run) and omits the drill-down
   when `run_detail` is None — proven by `tests/unit/test_observability.py::test_render_report`.
2. `orchestrator runs report [--run-id X] [--json]` prints the store report (JSON emits
   kpis+alerts+recent) — proven by `tests/unit/test_cli.py::test_runs_report_command`.
3. `--report` on a run prints the report after the answer, including THIS run's drill-down, and does
   not change the run's exit code — proven by `::test_run_with_report_flag`.
4. `--report` degrades cleanly if the store can't be read (prints the answer, skips the report,
   exit unchanged) — proven by `::test_report_flag_survives_unreadable_store`.
5. `make verify` PASS; decomposition eval unchanged at 16/16.
6. Live: `PYTHONPATH=src python3 -m orchestrator --execute --report "<task>"` runs against the live
   LLM + apps and prints real KPIs, cost/tokens, quality, alerts, per-app, recent, and the step
   drill-down.

## Plan (before coding)

1. observability.py: `render_report(...)` composing the existing atomic renderers + a summary
   header; a small `_render_cost`/`_render_quality` helper section (or fold into the report).
2. cli.py: add `--report` flag; after `_record(...)` on both paths, best-effort print
   `_full_report(root, run_id)` (reads kpis/alerts/list_runs/get_run and calls render_report). Add a
   `runs report` subcommand (with `--run-id`, `--json`). Move the KPI text out of `_render_kpis`
   reuse so both the `--kpis` view and the report share it.
3. Tests (observability render_report; cli report flag + runs report), offline.
4. docs/RUNBOOK.md: document the one-command live report. STATE.md.

## Failure analysis

<!-- MANDATORY when the same check fails 3x (doom-loop protocol). -->

## Done

Proof commit: <sha>   Auditor verdict: <>   Docs updated: <>
