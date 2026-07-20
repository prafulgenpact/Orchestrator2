# Task: render-charts-images

Status: DONE
Type: feature
Scope: registry/apps.json, src/orchestrator/artifacts.py, src/orchestrator/executor.py, tests/unit/**, STATE.md
Phase: Phase 2 — make chart/plot outputs viewable (openable files; UI-ready artifacts)

## Goal

Model-eval charts and free-form kernel plots become openable files, not raw JSON/base64. Two
mechanisms: (a) spec charts — flag the 8 viz ops `produces:"chart"` and add a line/curve renderer so
ROC/PR/learning-curve/confusion-matrix render to HTML; (b) image charts — `run_code`'s base64 PNGs
(and any endpoint returning `images`) become `Artifact(kind="image")` carrying the PNG data, saved
as openable `.png`. Artifacts carry the source data so a future UI renders them with no backend
change.

## Acceptance criteria

1. `render_chart_svg` draws `{curves:[{fpr,tpr}]}` (ROC/PR) as multi-line and
   `{train_sizes,train_mean,val_mean}` as a two-line learning curve — proven by
   `tests/unit/test_artifacts.py::test_render_curves` and `::test_render_learning_curve`.
2. `{confusion_matrix, classes}` renders as a heatmap — proven by
   `tests/unit/test_artifacts.py::test_render_confusion_matrix`.
3. An `Artifact(kind="image")` renders to an `<img>` HTML and `save_artifacts` writes it as a `.png`
   file carrying the decoded bytes — proven by `tests/unit/test_artifacts.py::test_image_artifact_html`
   and `::test_save_writes_png`.
4. A viz op flagged `produces:"chart"` attaches a chart artifact; `run_code`'s `images` become image
   artifacts — proven by `tests/unit/test_executor.py::test_viz_op_attaches_chart` and
   `::test_run_code_images_attach_image_artifacts`.
5. `make verify` passes; decomposition eval stays 16/16.

## Plan (before coding)

1. `artifacts.py`:
   - `_lines_svg(series, title)` generic multi-line plot with axes.
   - dispatch: `curves` -> lines (auto x/y: fpr/tpr or recall/precision); `train_sizes` -> two lines
     (train_mean, val_mean); `confusion_matrix`+`classes` -> existing heatmap (columns=classes).
   - image artifacts: `render_chart_html` returns `<img src="data:image/png;base64,..">` when
     `kind=="image"`; `save_artifacts` writes `.png` (decoded) for image artifacts, `.html` for charts.
2. `executor.py`: generalize `_chart_artifacts` -> `_result_artifacts(op, sub, data)` — chart artifact
   when `produces=="chart"`; one image artifact per base64 string in `data["images"]`.
3. `registry/apps.json`: flag the 8 `post_viz_*` ops `produces:"chart"`.
4. Tests + live smoke (real ROC -> HTML; real run_code plot -> PNG) + `make verify`.

## Failure analysis

## Done

Line/curve renderer + confusion heatmap + image artifacts added; 8 viz ops flagged produces=chart.
Live-smoked: ROC -> HTML (curve + diagonal), run_code plot -> valid 534x435 PNG. All 5 acceptance
criteria met; make verify PASS; eval 16/16. Artifacts carry source data, so UI-ready.

Proof commit: <this commit>   Auditor verdict: <pending>   Docs updated: STATE.md
