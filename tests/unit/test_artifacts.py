"""Unit tests for chart-artifact rendering and saving (no network, no LLM)."""

from __future__ import annotations

import base64
from pathlib import Path

from orchestrator.artifacts import output_dir, render_chart_html, render_chart_svg, save_artifacts
from orchestrator.models import Artifact, PlanResult, SubtaskResult

_BOX = Artifact(
    "chart",
    "cylinders — box",
    {
        "type": "box",
        "column": "cylinders",
        "q1": 4,
        "median": 4,
        "q3": 8,
        "whisker_low": 3,
        "whisker_high": 8,
        "outliers": [],
        "mean": 5.4,
    },
    "t1",
)
_HIST = Artifact(
    "chart",
    "mpg — hist",
    {"type": "histogram", "bins": [0, 10, 20, 30], "counts": [5, 12, 3]},
    "t1",
)
_CORR = Artifact(
    "chart", "corr", {"columns": ["a", "b"], "values": [[1.0, -0.5], [-0.5, 1.0]]}, "t1"
)


def _self_contained(doc: str) -> bool:
    # no external resource *loads* (offline-safe). The SVG xmlns URI is a namespace name, not a
    # fetch, so we check for actual load vectors instead.
    lowered = doc.lower()
    return not any(v in lowered for v in ("src=", "<link", "<script", "cdn", "@import", "url("))


def test_render_chart_html_box() -> None:
    doc = render_chart_html(_BOX)
    assert doc.startswith("<!doctype html>")
    assert "<svg" in doc and "cylinders — box" in doc
    assert _self_contained(doc)


def test_render_chart_html_histogram() -> None:
    doc = render_chart_html(_HIST)
    assert "<rect" in doc  # bars drawn
    assert _self_contained(doc)


def test_render_chart_html_correlation_heatmap() -> None:
    doc = render_chart_html(_CORR)
    assert "rgb(" in doc  # heatmap cells coloured
    assert _self_contained(doc)


def test_render_chart_html_labels_counts() -> None:
    art = Artifact("chart", "target", {"labels": ["a", "b", "c"], "counts": [10, 5, 2]}, "t1")
    doc = render_chart_html(art)
    assert "<rect" in doc and _self_contained(doc)  # rendered as bars


def test_render_chart_svg_unknown_shape_is_safe() -> None:
    art = Artifact("chart", "mystery", {"weird": 1}, "t1")
    svg = render_chart_svg(art)
    assert svg.startswith("<svg") and "mystery" in svg  # title-only frame, no crash


def test_save_artifacts_writes_files(tmp_path: Path) -> None:
    r = SubtaskResult(
        "t1",
        "coding-playground",
        "Coding Playground",
        "ok",
        "eda_distribution",
        {"ok": True},
        None,
        None,
        0.1,
        None,
        (_BOX, _HIST),
    )
    result = PlanResult("task", "intent", (r,))
    paths = save_artifacts(result, out_dir=tmp_path)
    assert len(paths) == 2
    for p in paths:
        assert p.exists() and p.suffix == ".html"
        assert p.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_save_artifacts_none_when_no_artifacts(tmp_path: Path) -> None:
    r = SubtaskResult("t1", "a", "A", "ok", "op", "text", None, None, 0.1)
    assert save_artifacts(PlanResult("t", "i", (r,)), out_dir=tmp_path) == []


def test_output_dir_env_override(monkeypatch) -> None:
    monkeypatch.setenv("ORCHESTRATOR_OUTPUT_DIR", "/tmp/custom-charts")
    assert output_dir() == Path("/tmp/custom-charts")


# --- model-eval spec charts (line/curve renderer) -------------------------------------------------

_ROC = Artifact(
    "chart",
    "ROC",
    {"curves": [{"class": "positive", "fpr": [0.0, 0.3, 1.0], "tpr": [0.0, 0.8, 1.0]}]},
    "t1",
)
_LEARN = Artifact(
    "chart",
    "learning curve",
    {
        "train_sizes": [10, 50, 100],
        "train_mean": [0.7, 0.8, 0.85],
        "val_mean": [0.6, 0.7, 0.72],
        "scoring": "accuracy",
    },
    "t1",
)
_CONFUSION = Artifact(
    "chart", "confusion", {"confusion_matrix": [[92, 13], [37, 37]], "classes": ["no", "yes"]}, "t1"
)


def test_render_curves() -> None:
    svg = render_chart_svg(_ROC)
    assert svg.count("<polyline") == 1  # one curve
    assert "stroke-dasharray" in svg  # ROC chance diagonal
    assert _self_contained(render_chart_html(_ROC))
    assert "<table" not in render_chart_html(_ROC)  # a known shape: no fallback table


def test_render_learning_curve() -> None:
    svg = render_chart_svg(_LEARN)
    assert svg.count("<polyline") == 2  # train + validation
    assert "train" in svg and "validation" in svg  # legend labels


def test_render_confusion_matrix() -> None:
    svg = render_chart_svg(_CONFUSION)
    assert 'fill="rgb(' in svg  # rendered as a heatmap of cells
    assert "no" in svg and "yes" in svg  # class labels


# --- image artifacts (base64 PNG -> openable .png) ------------------------------------------------

_PNG_B64 = base64.b64encode(b"\x89PNG\r\n\x1a\nFAKE-PNG-BYTES").decode()
_IMAGE = Artifact("image", "kernel plot", {"png_base64": _PNG_B64}, "t1")


def test_image_artifact_html() -> None:
    doc = render_chart_html(_IMAGE)
    assert f"data:image/png;base64,{_PNG_B64}" in doc
    assert "<img" in doc
    # offline-safe: the only src is an inline data: URI (no remote fetch), no script/link/cdn.
    assert doc.count("src=") == doc.count('src="data:')
    assert not any(v in doc.lower() for v in ("<script", "<link", "cdn", "http://", "https://"))


def test_save_writes_png(tmp_path: Path) -> None:
    r = SubtaskResult(
        "t1",
        "coding-playground",
        "CP",
        "ok",
        "run_code",
        {"images": [_PNG_B64]},
        None,
        None,
        0.1,
        None,
        (_IMAGE,),
    )
    paths = save_artifacts(PlanResult("task", "intent", (r,)), out_dir=tmp_path)
    assert len(paths) == 1 and paths[0].suffix == ".png"
    assert paths[0].read_bytes() == b"\x89PNG\r\n\x1a\nFAKE-PNG-BYTES"  # decoded, not base64 text


def test_subtaskresult_carries_artifacts() -> None:
    r = SubtaskResult("t1", "a", "A", "ok", "op", {"x": 1}, None, None, 0.1, None, (_BOX,))
    assert r.artifacts == (_BOX,)
    assert r.to_dict()["artifacts"][0]["title"] == "cylinders — box"
    # trailing defaulted: existing positional construction (no artifacts) still works
    assert SubtaskResult("t2", "a", "A", "ok", "op", "text", None, None, 0.1).artifacts == ()


def test_artifacts_collected_and_not_in_prompt(fake_llm) -> None:
    from orchestrator.synthesis import synthesize

    # two structured results (forces the LLM fusion path) — one carries a chart artifact
    r1 = SubtaskResult(
        "t1",
        "coding-playground",
        "Coding Playground",
        "ok",
        "eda_distribution",
        {"rows": 398},
        "http://x",
        None,
        0.1,
        None,
        (_BOX,),
    )
    r2 = SubtaskResult(
        "t2",
        "stats-teacher",
        "Stats Teacher",
        "ok",
        "ask",
        {"note": "cylinders vary"},
        None,
        None,
        0.1,
    )
    client = fake_llm(["A fused grounded answer."])
    syn = synthesize(client, PlanResult("task", "intent", (r1, r2)), model="m")
    # the chart rides through as a first-class artifact...
    assert syn.artifacts == (_BOX,)
    # ...and its (potentially huge) spec never entered the LLM prompt text
    prompt = client.requests[0].messages[0]["content"]
    assert "whisker_high" not in prompt and "box" not in prompt.split("Coding Playground")[-1][:200]


def test_render_chart_paths_block() -> None:
    from orchestrator.render import render_chart_paths

    assert render_chart_paths([]) == ""
    block = render_chart_paths([Path("/out/01-a.html"), Path("/out/02-b.html")])
    assert "Charts" in block and "01-a.html" in block and "02-b.html" in block
