# Task: model-eval-ml-debug

Status: planned
Type: feature
Scope: registry/apps.json, src/orchestrator/artifacts.py, tests/unit/**, tests/e2e/fixtures/**, tests/eval/fixtures/**, STATE.md
Phase: Phase 2 — capability coverage (Theme A wiring: model-eval charts + ML training + debug/analyze)

## Goal

The orchestrator can train an ML model, evaluate it with charts, and explain an error. Wire
coding-playground's model-eval viz endpoints, ML training endpoints, and debug/analyze endpoints as
HTTP operations. The viz ops emit chart specs flagged `produces: "chart"` (reusing last task's
artifact pipeline); a new line/curve renderer in artifacts.py draws the ROC/PR/learning-curve shapes
these endpoints return. All endpoints are synchronous (ml/train ~10s) — no async-poll needed.

## Acceptance criteria

Each one names the test that proves it.

1. `render_chart_svg` draws a `{curves:[{fpr,tpr}]}` ROC/PR spec as a multi-line curve plot —
   proven by `tests/unit/test_artifacts.py::test_render_chart_html_curves`.
2. `render_chart_svg` draws a `{train_sizes, train_mean, val_mean}` learning-curve spec as two
   lines — proven by `tests/unit/test_artifacts.py::test_render_chart_html_learning_curve`.
3. A `{confusion_matrix, classes}` classification-metrics spec renders as a heatmap — proven by
   `tests/unit/test_artifacts.py::test_render_chart_html_confusion_matrix`.
4. A viz op flagged `produces: "chart"` attaches a chart artifact on the ok result; a non-chart ML
   op (ml_train) does not — proven by `tests/unit/test_executor.py::test_viz_op_attaches_artifact`
   and `::test_ml_train_op_has_no_artifact`.
5. The registry parses the 16 new coding-playground ops with correct methods/required fields —
   proven by `tests/unit/test_registry.py::test_model_eval_ops_parse`.
6. `make verify` passes; decomposition eval stays 16/16 (no planner change → routing unaffected).

## Plan (before coding)

1. `artifacts.py`: add `_lines_svg(series, title, x_label, y_label)` (generic multi-line plot with
   axes). Extend `render_chart_svg` dispatch:
   - spec has `curves` (list of `{fpr,tpr}` or `{recall,precision}`) → one line per curve + ref
     diagonal for ROC.
   - spec has `train_sizes` → two lines (train_mean, val_mean) vs train_sizes.
   - spec has `confusion_matrix` + `classes` → map to the existing `_heatmap_svg` (columns=classes,
     values=matrix).
   - everything else keeps the current fallback (openable HTML data-table — nothing is ever lost).
   Update `render_chart_html`'s `known` guard so these shapes skip the redundant table.
2. `registry/apps.json` — add 16 ops to coding-playground (all synchronous, no `poll`):
   - **viz (produces: "chart"):** viz_roc, viz_pr_curve, viz_learning_curve,
     viz_classification_metrics, viz_regression_plots, viz_cross_validation,
     viz_decision_boundary, viz_compare  (POST /api/viz/*, VizRequest-family bodies).
   - **ml training:** ml_train, ml_train_unsupervised, ml_generate_code (POST /api/ml/*),
     ml_list_models (GET /api/ml/models), ml_model_params (GET /api/ml/models/{model_id}/params).
   - **debug:** debug_analyze (POST /api/debug/analyze), debug_list_pitfalls (GET),
     debug_pitfall_detail (GET /api/debug/pitfalls/{pitfall_id}).
   Update the app description / examples so the planner routes "train a model", "show the ROC curve",
   "why did I get this error" here. Give ml_train / viz ops a generous `timeout_s` (~120).
3. Tests: renderer unit tests (curves, learning-curve, confusion-matrix); executor viz-artifact
   test; registry parse test. Re-record eval + e2e fixtures (registry edit re-keys them).
4. `make verify`; confirm decomposition eval 16/16 with 0 skips.

## Grounded API shapes (from live app, port 8003 /openapi.json + live calls)

- viz/roc, viz/pr_curve -> {curves:[{class,fpr,tpr}], auc_scores} (multi-line)
- viz/learning-curve -> {train_sizes, train_mean, train_std, val_mean, val_std, scoring} (2-line)
- viz/classification-metrics -> {metrics:{...}, confusion_matrix:[[...]], classification_report, classes}
- VizRequest body: dataset_id*, model_id*, target_col*, test_size?, params?
- CompareRequest: dataset_id*, target_col*, model_ids*[], test_size?, params_list?
- CrossValRequest: + cv?; DecisionBoundaryRequest: + feature_x*, feature_y*; LearningCurve: + cv?
- ml/train (TrainRequest: dataset_id*, model_id*, target_col*, test_size?, params?) -> sync ~10s,
  {model_id, metrics, feature_importance, code, code_verification, ...}
- ml/generate-code -> {code, code_verification}; ml/models -> grouped list; ml/models/{id}/params -> params
- debug/analyze (DebugRequest: error_text*, code?) -> {error_text, matches:[{title,category,cause,...}]}
- debug/pitfalls -> list; debug/pitfalls/{id} -> detail

## Failure analysis

## Done

Proof commit: <sha>   Auditor verdict: <pending>   Docs updated: STATE.md
