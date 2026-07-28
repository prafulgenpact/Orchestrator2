# Task: observability-runs-cli

Status: DONE
Type: feature
Scope: src/orchestrator/observability.py, src/orchestrator/cli.py, tests/unit/test_observability.py, tests/unit/test_cli.py, tests/unit/conftest.py, .gitleaksignore, STATE.md
Phase: Observability Step C — read service + terminal commands (plan: ~/.claude/plans/i-need-to-build-validated-prism.md)

## Goal

The saved runs become browsable without a UI. A UI-agnostic read service (`kpis`, `list_runs`,
`get_run`) queries the SQLite store, and two terminal commands expose it: `orchestrator runs list`
(recent runs — time, status, duration, subtasks) and `orchestrator runs show <id>` (one run's full
per-step drill-down). The same read functions are the stable contract a future dashboard binds to.
Read-only: no LLM, registry, or network — so eval stays 16/16 and the existing `orchestrator
"<task>"` behavior is unchanged.

## Acceptance criteria

Each one names the test that proves it.

1. `list_runs(root, limit, status)` returns saved runs newest-first as summary dicts, honoring
   `limit` and an optional `status` filter — proven by
   `tests/unit/test_observability.py::test_list_runs_orders_and_filters`.
2. `kpis(root)` aggregates the store into totals, status counts, run-latency p50/p95/p99, per-app
   usage (calls/ok/error/no_match/avg duration), avg routing confidence, and fallback/no-match
   rates — proven by `::test_kpis_aggregates`. An empty store returns zeros, not an error —
   `::test_kpis_empty_store`.
3. `orchestrator runs list` and `runs show <id>` render from the store; `--json` emits machine
   output; an unknown id exits non-zero with a clear message — proven by
   `tests/unit/test_cli.py::test_runs_list_command`, `::test_runs_show_command`, and
   `::test_runs_show_unknown_id`.
4. The `runs` command touches no LLM/registry/network (routed before any of that in `main`), and a
   normal `orchestrator "<task>"` invocation is unaffected — proven by `::test_runs_command_offline`
   and the unchanged existing CLI tests.
5. `make verify` PASS; decomposition eval unchanged at 16/16.
6. Live: after a recorded run, `runs list` shows it and `runs show <id>` prints its steps.

## Plan (before coding)

1. observability.py — read service:
   - `list_runs(root=None, *, limit=20, status=None)` → SELECT from `runs` newest-first.
   - `kpis(root=None)` → load `runs` + `steps`, aggregate in Python (a `_percentile` helper for
     p50/p95/p99); return a plain dict. Empty store → zeroed dict.
   - Small text renderers `render_runs_list(rows)` and `render_run_detail(record)`.
2. cli.py — routing:
   - At the top of `main`, if `argv and argv[0] == "runs"`, dispatch to `_runs_command(argv[1:])`
     (its own tiny argparse: `list`/`show`, `--root`, `--limit`, `--status`, `--json`). Returns an
     exit code; never loads the registry/client.
3. Tests in test_observability.py (read service) + test_cli.py (command routing/exit codes), offline.
4. STATE.md.

## Failure analysis

<!-- MANDATORY when the same check fails 3x (doom-loop protocol). -->

## Done

Proof commit: <sha>   Auditor verdict: <>   Docs updated: <>
