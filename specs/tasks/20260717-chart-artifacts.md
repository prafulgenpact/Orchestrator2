# Task: chart-artifacts

Status: DONE
Type: feature
Scope: src/orchestrator/models.py, src/orchestrator/artifacts.py, src/orchestrator/synthesis.py, src/orchestrator/render.py, src/orchestrator/cli.py, tests/unit/**
Phase: Phase 2 — capability coverage (fill gaps found in the app catalogue) + UX

## Goal

Charts survive to the user. Today any structured/binary output is truncated to death in synthesis and
render. Add a first-class chart artifact that rides through the pipeline untouched, gets saved as a
self-contained openable HTML file, and has its path shown to the user. This is the foundation the EDA
and model-evaluation chart operations (next task) depend on.

## Acceptance criteria

1. A `SubtaskResult` carries chart artifacts (trailing, defaulted field) and they round-trip through
   synthesis without entering/being truncated by the text caps — proven by
   `tests/unit/test_artifacts.py::test_subtaskresult_carries_artifacts` and
   `::test_artifacts_collected_and_not_in_prompt`.
2. A chart spec (box/histogram/bar/scatter/correlation) renders to a valid self-contained HTML file
   with no external resource loads — proven by `tests/unit/test_artifacts.py::test_render_chart_html_*`.
3. Charts save to an output dir and their paths are surfaced — proven by
   `tests/unit/test_artifacts.py::test_save_artifacts_writes_files` and `::test_render_chart_paths_block`.

## Plan (before coding)

1. `models.py`: add frozen `Artifact(kind, title, spec, subtask_id)` + trailing `artifacts: tuple = ()`
   on `SubtaskResult`; include in `to_dict`.
2. `artifacts.py` (new): `render_chart_html(artifact) -> str` (inline SVG per chart type, no CDN) and
   `save_artifacts(results, out_dir) -> list[path]` (reuse the replay.py mkdir+write idiom; output dir
   env-overridable, default `./orchestrator-output`).
3. `synthesis.py`: collect artifacts in code (mirror `_sources`); keep them OUT of `_render_output` so
   they never hit the 3000-char cap; add `artifacts` to the `Synthesis` object.
4. `render.py`/`cli.py`: after synthesis, save artifacts and print `chart saved -> <path>` lines
   (stderr-safe; stdout/JSON unchanged).
5. `make verify`; decomposition eval stays 16/16.

## Failure analysis

## Done

Proof commit: <sha>   Auditor verdict: <pending>   Docs updated: STATE.md
