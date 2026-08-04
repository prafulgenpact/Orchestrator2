# Task: web-charts-and-run-logging

Status: DONE
Type: feature
Scope: src/orchestrator/web.py, web/atelier-workspace.html, tests/unit/test_web.py, STATE.md
Phase: Phase 3 — web connector

## Goal

Two web-connector parity gaps with the CLI, both user-reported:

1. **Charts in the UI.** Chart-spec outputs (ops with `produces: "chart"` — eda_correlation,
   eda_distribution, …) render as actual graphs in the Atelier output cards and in the final
   answer's Charts section. Today only base64 kernel PNGs display; spec charts fall through to a
   raw key/value dump. Reuse the existing, tested `render_chart_svg` (artifacts.py) server-side —
   no new chart renderer.
2. **Every run is logged.** Web-connector runs are recorded via the existing `record_run`
   (runs/<id>.json + sqlite + hash-chained events.jsonl), exactly like CLI runs. Recording is
   best-effort and never breaks or slows the stream.

## Acceptance criteria

1. `result` events carry a rendered inline `svg` on each known-shape chart artifact —
   proven by `tests/unit/test_web.py::test_result_payload_renders_chart_svg`
   (+ `test_result_payload_skips_unknown_chart_shapes`).
2. The `final` event carries `charts` (SVG strings from ok steps' chart artifacts, deduped,
   capped) — proven by `tests/unit/test_web.py::test_collect_chart_svgs*`.
3. `run_events` records every run: `record_run` called with exit_code 0 on success and 1 on an
   execute failure; planning failures (no plan object exists to record) end the stream without a
   record — proven by `tests/unit/test_web.py::test_run_events_records_run`,
   `test_run_events_records_execute_failure`, `test_run_events_no_record_without_plan`.
4. The UI draws artifact SVGs on step cards and `final.charts` on the answer card; `make verify`
   PASS.

## Plan (before coding)

1. `web.py`: `_artifact_payload` / `_result_payload` (result dict + `svg` per known-shape chart
   artifact via `render_chart_svg`); `_collect_chart_svgs(plan_result)` mirroring
   `_collect_images`; `run_events` stamps `started_at`, keeps the worker's result/synthesis/error
   in a holder, and calls `record_run` (wrapped best-effort) before yielding `done`.
2. `atelier-workspace.html`: `renderOutput` appends chart-artifact SVGs; `finalizeAnswer` renders
   `data.charts` alongside `data.images` in the Charts section.
3. Unit tests per the criteria above; restart the connector and live-check a chart task.

## Failure analysis

<!-- MANDATORY when the same check fails 3x (doom-loop protocol). -->

## Done

All four criteria met. `make verify` PASS (unit 20/20 in test_web.py, coverage/lint/format/types
green). Live-verified end-to-end: connector restarted, "Show the correlation matrix for the Titanic
dataset" run in headless Chrome — the heatmap SVG rendered on the step card AND the final answer's
Charts section (0 raw kv rows, 0 JS errors), and the run was recorded (runs/7957ffac….json +
events.jsonl seq 4, hash chain intact).

Proof commit: see seal after this commit   Auditor verdict: pending   Docs updated: STATE.md
