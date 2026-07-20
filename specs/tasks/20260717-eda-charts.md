# Task: eda-charts

Status: Done
Type: feature
Scope: registry/apps.json, src/orchestrator/registry.py, src/orchestrator/executor.py, src/orchestrator/artifacts.py, tests/unit/**, tests/e2e/fixtures/**, tests/eval/fixtures/**, .gitignore, STATE.md
Phase: Phase 2 — capability coverage (wire coding-playground's EDA/analysis endpoints)

## Goal

The orchestrator can plot/analyze a dataset. Wire coding-playground's EDA endpoints (summary,
distribution, correlation, scatter, target-distribution, outliers, dtypes-missing) as HTTP
operations. Chart-producing ones are flagged `produces: "chart"`, so the executor keeps their output
as a chart artifact that saves to an openable HTML file (built last task). Adds a declarative
`produces` field to the operation schema so this stays generic (reused by the model-eval charts next).

## Acceptance criteria

1. The operation schema carries `produces` (default None), parsed from the registry — proven by
   `tests/unit/test_registry.py::test_operation_parses_produces`.
2. A chart-producing op's dict output becomes a chart artifact on the ok result; a non-chart op does
   not — proven by `tests/unit/test_executor.py::test_chart_op_attaches_artifact` and
   `::test_non_chart_op_has_no_artifact`.
3. `target_distribution`'s labels+counts spec renders as bars — proven by
   `tests/unit/test_artifacts.py::test_render_chart_html_labels_counts`.
4. `make verify` passes; decomposition eval stays 16/16 (routing unaffected — no planner change).

## Plan (before coding)

1. `registry.py`: add `produces: str | None = None` to `AppOperation` (+ to_dict + parse). [done]
2. `executor.py`: `_chart_artifacts(op, sub, data)` — when `op.produces == "chart"` and data is an
   error-free dict, attach `Artifact(kind="chart", ...)` to the ok result. [done]
3. `artifacts.py`: render_chart_svg also handles a `{labels, counts}` spec as bars.
4. `registry/apps.json`: add the 7 EDA ops to coding-playground; mark distribution/correlation/
   scatter/target-distribution as `produces: "chart"`; update the app description/when_not/examples.
5. Tests + `make verify`.

## Failure analysis

## Done

All 4 acceptance criteria met; `make verify` PASS (proof `f5867695c405`), decomposition eval 16/16.
Registry re-keyed the replay fixtures, so all 16 eval fixtures + 1 e2e fixture re-recorded and 16
orphaned old fixtures removed (proven: eval stays 16/16 with 0 skips). Scope widened for fixture/
housekeeping paths.

Proof commit: <sha>   Auditor verdict: <pending>   Docs updated: STATE.md
