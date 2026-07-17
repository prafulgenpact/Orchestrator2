"""Turn chart artifacts into openable, self-contained HTML files.

An app hands back the *numbers behind a chart* (a box plot's quartiles, a histogram's bins, a
correlation matrix). A terminal can't draw those, so we render each one to a standalone HTML file —
inline SVG, no external network references — that opens straight in a browser. This is exactly the
data a future web UI would render inline; here it becomes a file whose path we show the user.

Kept dependency-free (stdlib only) and pure (no I/O in the renderers) so it is fully unit-testable.
"""

from __future__ import annotations

import html
import os
from pathlib import Path
from typing import Any

from orchestrator.models import Artifact, PlanResult

Spec = dict[str, Any]

# Output dir for saved charts; env-overridable so tests/CI can point it at a temp dir.
_DEFAULT_OUTPUT_DIR = "orchestrator-output"

_W, _H = 640, 400
_PAD = 50


def _esc(text: object) -> str:
    return html.escape(str(text))


def _svg_frame(body: str, title: str) -> str:
    return (
        f'<svg viewBox="0 0 {_W} {_H}" xmlns="http://www.w3.org/2000/svg" '
        f'role="img" aria-label="{_esc(title)}">'
        f'<rect width="{_W}" height="{_H}" fill="#ffffff"/>'
        f'<text x="{_W // 2}" y="24" text-anchor="middle" '
        f'font-family="system-ui,sans-serif" font-size="16" font-weight="600">{_esc(title)}</text>'
        f"{body}</svg>"
    )


def _scale(value: float, lo: float, hi: float, out_lo: float, out_hi: float) -> float:
    if hi == lo:
        return (out_lo + out_hi) / 2
    return out_lo + (value - lo) / (hi - lo) * (out_hi - out_lo)


def _bars_svg(labels: list[object], counts: list[float], title: str) -> str:
    if not counts:
        return _svg_frame("", title)
    top = max(counts) or 1
    n = len(counts)
    plot_w = _W - 2 * _PAD
    bw = plot_w / n
    bars: list[str] = []
    for i, c in enumerate(counts):
        h = _scale(c, 0, top, 0, _H - 2 * _PAD)
        x = _PAD + i * bw
        y = _H - _PAD - h
        bars.append(
            f'<rect x="{x + bw * 0.1:.1f}" y="{y:.1f}" width="{bw * 0.8:.1f}" height="{h:.1f}" '
            f'fill="#7c7cf0"/>'
        )
        if n <= 20:
            lab = _esc(labels[i] if i < len(labels) else i)
            bars.append(
                f'<text x="{x + bw / 2:.1f}" y="{_H - _PAD + 14:.1f}" text-anchor="middle" '
                f'font-family="system-ui,sans-serif" font-size="9">{lab}</text>'
            )
    axis = (
        f'<line x1="{_PAD}" y1="{_H - _PAD}" x2="{_W - _PAD}" y2="{_H - _PAD}" stroke="#888"/>'
        f'<line x1="{_PAD}" y1="{_PAD}" x2="{_PAD}" y2="{_H - _PAD}" stroke="#888"/>'
    )
    return _svg_frame(axis + "".join(bars), title)


def _box_svg(spec: Spec, title: str) -> str:
    lo = float(spec.get("whisker_low", spec.get("q1", 0)))
    hi = float(spec.get("whisker_high", spec.get("q3", 1)))
    q1, med, q3 = float(spec["q1"]), float(spec["median"]), float(spec["q3"])
    outliers = [float(o) for o in spec.get("outliers", [])]
    allv = [lo, hi, q1, med, q3, *outliers]
    vlo, vhi = min(allv), max(allv)
    span = (vhi - vlo) or 1
    vlo -= span * 0.1
    vhi += span * 0.1

    def y(v: float) -> float:
        return _scale(v, vlo, vhi, _H - _PAD, _PAD)

    cx = _W / 2
    bw = 120
    parts = [
        f'<line x1="{cx}" y1="{y(lo):.1f}" x2="{cx}" y2="{y(hi):.1f}" stroke="#5a5ad8"/>',
        f'<rect x="{cx - bw / 2:.1f}" y="{y(q3):.1f}" width="{bw}" height="{y(q1) - y(q3):.1f}" '
        f'fill="#b9b9f5" stroke="#5a5ad8"/>',
        f'<line x1="{cx - bw / 2:.1f}" y1="{y(med):.1f}" x2="{cx + bw / 2:.1f}" y2="{y(med):.1f}" '
        f'stroke="#2b2b8f" stroke-width="2"/>',
    ]
    for label, v in (("max", hi), ("q3", q3), ("median", med), ("q1", q1), ("min", lo)):
        parts.append(
            f'<text x="{cx + bw / 2 + 8:.1f}" y="{y(v) + 3:.1f}" '
            f'font-family="system-ui,sans-serif" font-size="10" fill="#333">'
            f"{label}: {v:g}</text>"
        )
    for o in outliers[:200]:
        parts.append(f'<circle cx="{cx}" cy="{y(o):.1f}" r="2.5" fill="#d33"/>')
    return _svg_frame("".join(parts), title)


def _scatter_svg(spec: Spec, title: str) -> str:
    xs = [float(v) for v in spec.get("x", [])]
    ys = [float(v) for v in spec.get("y", [])]
    if not xs or not ys:
        return _svg_frame("", title)
    xlo, xhi, ylo, yhi = min(xs), max(xs), min(ys), max(ys)
    pts = [
        f'<circle cx="{_scale(x, xlo, xhi, _PAD, _W - _PAD):.1f}" '
        f'cy="{_scale(y, ylo, yhi, _H - _PAD, _PAD):.1f}" r="2.5" fill="#5a5ad8" opacity="0.6"/>'
        for x, y in zip(xs, ys, strict=False)
    ]
    axis = (
        f'<line x1="{_PAD}" y1="{_H - _PAD}" x2="{_W - _PAD}" y2="{_H - _PAD}" stroke="#888"/>'
        f'<line x1="{_PAD}" y1="{_PAD}" x2="{_PAD}" y2="{_H - _PAD}" stroke="#888"/>'
    )
    return _svg_frame(axis + "".join(pts), title)


def _heatmap_svg(spec: Spec, title: str) -> str:
    cols = spec.get("columns", [])
    vals = spec.get("values", [])
    n = len(cols)
    if not n:
        return _svg_frame("", title)
    grid = min(_W, _H) - 2 * _PAD
    cell = grid / n
    parts: list[str] = []
    for i, row in enumerate(vals):
        for j, v in enumerate(row):
            try:
                fv = float(v)
            except (TypeError, ValueError):
                fv = 0.0
            # -1 (red) .. 0 (white) .. 1 (blue)
            if fv >= 0:
                r, g, b = int(255 * (1 - fv)), int(255 * (1 - fv)), 255
            else:
                r, g, b = 255, int(255 * (1 + fv)), int(255 * (1 + fv))
            x, y = _PAD + j * cell, _PAD + i * cell
            parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{cell:.1f}" height="{cell:.1f}" '
                f'fill="rgb({r},{g},{b})" stroke="#eee"/>'
            )
    for i, c in enumerate(cols):
        parts.append(
            f'<text x="{_PAD - 4:.1f}" y="{_PAD + i * cell + cell / 2 + 3:.1f}" text-anchor="end" '
            f'font-family="system-ui,sans-serif" font-size="9">{_esc(c)}</text>'
        )
    return _svg_frame("".join(parts), title)


def _spec_table(spec: Spec) -> str:
    rows = "".join(f"<tr><td>{_esc(k)}</td><td>{_esc(v)}</td></tr>" for k, v in spec.items())
    return f"<table><tbody>{rows}</tbody></table>"


def render_chart_svg(artifact: Artifact) -> str:
    """The chart as an inline SVG string (no HTML wrapper) — chosen by the spec's shape."""
    spec = artifact.spec
    kind = spec.get("type")
    title = artifact.title
    if kind == "box":
        return _box_svg(spec, title)
    if kind == "histogram":
        return _bars_svg(spec.get("bins", []), spec.get("counts", []), title)
    if kind == "bar":
        return _bars_svg(spec.get("labels", []), spec.get("counts", []), title)
    if kind == "scatter" or ("x" in spec and "y" in spec):
        return _scatter_svg(spec, title)
    if "columns" in spec and "values" in spec:
        return _heatmap_svg(spec, title)
    return _svg_frame("", title)  # unknown shape: title-only frame (table shown in the HTML below)


def render_chart_html(artifact: Artifact) -> str:
    """A complete, self-contained HTML document for the chart (inline SVG, no external refs)."""
    svg = render_chart_svg(artifact)
    known = artifact.spec.get("type") in ("box", "histogram", "bar", "scatter") or (
        "values" in artifact.spec
    )
    table = "" if known else _spec_table(artifact.spec)
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{_esc(artifact.title)}</title>"
        "<style>body{font-family:system-ui,sans-serif;margin:24px;background:#fafafa}"
        "svg{max-width:100%;height:auto;border:1px solid #eee;background:#fff}"
        "table{border-collapse:collapse;margin-top:12px}td{border:1px solid #ddd;padding:4px 8px}"
        "</style></head><body>"
        f"<h2>{_esc(artifact.title)}</h2>{svg}{table}</body></html>"
    )


def _slug(text: str) -> str:
    keep = [c if c.isalnum() else "-" for c in text.lower()]
    return "".join(keep).strip("-")[:50] or "chart"


def output_dir() -> Path:
    return Path(os.environ.get("ORCHESTRATOR_OUTPUT_DIR", _DEFAULT_OUTPUT_DIR))


def save_artifacts(plan_result: PlanResult, out_dir: Path | None = None) -> list[Path]:
    """Write every chart artifact in the result to a self-contained HTML file; return the paths."""
    artifacts = [a for r in plan_result.results for a in r.artifacts]
    if not artifacts:
        return []
    target = out_dir or output_dir()
    target.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for i, art in enumerate(artifacts, start=1):
        path = target / f"{i:02d}-{_slug(art.title)}.html"
        path.write_text(render_chart_html(art), encoding="utf-8")
        paths.append(path)
    return paths
