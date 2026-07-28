# Task: observability-quality-alerts

Status: DONE
Type: feature
Scope: src/orchestrator/observability.py, src/orchestrator/cli.py, tests/unit/test_observability.py, tests/unit/test_cli.py, STATE.md
Phase: Observability Step D — quality trend + health alerts (plan: ~/.claude/plans/i-need-to-build-validated-prism.md)

## Goal

Each run gets a quality score, the store tracks quality over time, and threshold breaches surface as
alerts — so a degrading system is visible instead of silent. Quality is derived from data already
captured (per-step status + relevance-caution note); alerts read the SQLite summary. No LLM/executor
change, so eval stays 16/16. (The plan's `promote <run_id>` into the eval dataset is deferred to its
own task — it mutates the 16/16 release-gate dataset and deserves separate care.)

## Acceptance criteria

Each one names the test that proves it.

1. Each executed run record carries a `quality` block (`score`, `executed`, `clean_ok`, `cautions`,
   `no_match`, `errors`); a dry run has `quality = None` — proven by
   `tests/unit/test_observability.py::test_quality_block` and `::test_dry_run_has_no_quality`.
2. `runs.quality_score` is persisted and included in `list_runs` summaries; an old DB missing the
   column is migrated on open, not crashed — proven by `::test_quality_score_persisted` and
   `::test_missing_quality_column_is_migrated`.
3. `kpis(root)` gains a `quality` aggregate (`avg_score`, `by_day`, `scored_runs`) — proven by
   `::test_kpis_quality_aggregate`.
4. `alerts(root, thresholds=None)` returns one entry per breached threshold (error rate, no-match
   rate, fallback rate, p95 latency, min quality, quality drop recent-vs-older) and `[]` when
   healthy/empty — proven by `::test_alerts_fire_on_breach` and `::test_alerts_empty_when_healthy`.
5. `orchestrator runs alerts` prints alerts (or "No alerts."), `--json` emits them; recording logs a
   per-run WARNING when a run has failed steps or low quality — proven by
   `tests/unit/test_cli.py::test_runs_alerts_command` and
   `tests/unit/test_observability.py::test_record_run_warns_on_bad_run` (caplog).
6. `make verify` PASS; decomposition eval unchanged at 16/16.
7. Live: a store with a failing/low-quality run shows a non-empty `runs alerts`; a clean store shows
   none.

## Plan (before coding)

1. observability.py:
   - `_quality(steps)` → per-run block (None when nothing executed); set on the record in
     `build_run_record`; add `quality_score` to the `runs` DDL + `_RUN_SUMMARY_COLS`.
   - `_ensure_columns(conn)` in `_connect`: `ALTER TABLE runs ADD COLUMN quality_score` if absent
     (idempotent migration for pre-existing local DBs).
   - extend `kpis` with a `quality` aggregate; add `alerts(root, *, thresholds=None)` with a
     `DEFAULT_THRESHOLDS` dict and a recent-vs-older quality-drop check.
   - `_log_run_alerts(record)` (stdlib logging WARNING) called best-effort inside `record_run`.
2. cli.py: add a `runs alerts [--json]` subcommand + a small renderer.
3. Tests in test_observability.py + test_cli.py (offline, tmp_path, caplog).
4. STATE.md.

## Failure analysis

<!-- MANDATORY when the same check fails 3x (doom-loop protocol). -->

## Done

Proof commit: <sha>   Auditor verdict: <>   Docs updated: <>
