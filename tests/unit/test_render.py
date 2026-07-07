"""Unit tests for rendering — wave computation, human output, and JSON output."""

from __future__ import annotations

import json

import pytest

from orchestrator.models import AppSelection, Plan, PlanResult, Subtask, SubtaskResult
from orchestrator.render import (
    DRY_RUN_BANNER,
    compute_waves,
    render_execution,
    render_human,
    render_json,
)


def _app(
    app_id: str = "stanford-llm", name: str = "Stanford LLM Course", fb: bool = False
) -> AppSelection:
    return AppSelection(
        app_id=app_id, app_name=name, rationale="because", confidence=0.9, fallback=fb
    )


def _plan(subtasks: tuple[Subtask, ...]) -> Plan:
    return Plan(
        task="learn transformers",
        intent="build a learning plan",
        subtasks=subtasks,
        model="claude-opus-4-6",
        prompt_version="1",
    )


def _sub(sub_id: str, deps: tuple[str, ...] = (), app: AppSelection | None = None) -> Subtask:
    return Subtask(sub_id, f"title-{sub_id}", f"desc-{sub_id}", deps, app or _app())


# --- compute_waves -----------------------------------------------------------


def test_waves_parallel_then_sequential() -> None:
    subs = (_sub("t1"), _sub("t2"), _sub("t3", ("t1", "t2")))
    waves = compute_waves(subs)
    assert [len(w) for w in waves] == [2, 1]
    assert {s.id for s in waves[0]} == {"t1", "t2"}
    assert waves[1][0].id == "t3"


def test_waves_single_subtask() -> None:
    assert [len(w) for w in compute_waves((_sub("t1"),))] == [1]


def test_waves_cycle_raises() -> None:
    subs = (_sub("t1", ("t2",)), _sub("t2", ("t1",)))
    with pytest.raises(ValueError, match="cycle"):
        compute_waves(subs)


# --- render_json -------------------------------------------------------------


def test_render_json_round_trips() -> None:
    plan = _plan((_sub("t1"),))
    data = json.loads(render_json(plan))
    assert data["task"] == "learn transformers"
    assert data["subtasks"][0]["id"] == "t1"


# --- render_human ------------------------------------------------------------


def test_human_output_structure() -> None:
    plan = _plan((_sub("t1"), _sub("t2"), _sub("t3", ("t1", "t2"))))
    out = render_human(plan)
    assert "Intent: build a learning plan" in out
    assert "3 subtask(s) in 2 step(s)" in out
    assert "Step 1 (parallel):" in out
    assert "Step 2:" in out
    assert "(depends on: t1, t2)" in out
    assert "-> Stanford LLM Course  (confidence 0.90)" in out
    assert "no apps were invoked" in out  # dry-run banner (ascii-safe substring)
    assert out.rstrip().endswith("prompt=v1")


def test_human_single_step_not_labelled_parallel() -> None:
    out = render_human(_plan((_sub("t1"),)))
    assert "Step 1:" in out
    assert "(parallel)" not in out


def test_human_marks_fallback() -> None:
    fallback_app = _app(app_id="web-search", name="Web Search (fallback)", fb=True)
    out = render_human(_plan((_sub("t1", app=fallback_app),)))
    assert "[FALLBACK]" in out


def test_banner_constant_used() -> None:
    assert DRY_RUN_BANNER in render_human(_plan((_sub("t1"),)))


# --- render_execution --------------------------------------------------------


def _result(status: str, output: object = None, error: str | None = None) -> SubtaskResult:
    return SubtaskResult(
        subtask_id="t1",
        app_id="arxiv-papers",
        app_name="ArXiv Paper Guide",
        status=status,
        operation="search_papers_by_query",
        output=output,
        source="http://127.0.0.1:8002/api/papers/search",
        error=error,
        duration_s=1.23,
    )


def test_render_execution_ok() -> None:
    pr = PlanResult("t", "i", (_result("ok", output={"papers": ["a"]}),))
    out = render_execution(pr)
    assert "Executed 1 subtask(s): 1 ok" in out
    assert "ArXiv Paper Guide :: search_papers_by_query" in out
    assert "-> OK" in out
    assert "source: http://127.0.0.1:8002/api/papers/search" in out
    assert '"papers"' in out  # real output shown


def test_render_execution_error() -> None:
    out = render_execution(PlanResult("t", "i", (_result("error", error="retry: boom"),)))
    assert "-> ERROR" in out
    assert "error: retry: boom" in out


def test_render_execution_skipped() -> None:
    skipped = SubtaskResult(
        "t1",
        "web-search",
        "Web Search (fallback)",
        "skipped",
        None,
        None,
        None,
        "web-search fallback not executed yet (deferred)",
        0.0,
    )
    out = render_execution(PlanResult("t", "i", (skipped,)))
    assert "-> SKIP" in out
    assert "deferred" in out


def test_render_execution_previews_long_and_nonstring_output() -> None:
    long_text = "x" * 500
    out = render_execution(PlanResult("t", "i", (_result("ok", output=long_text),)))
    assert "…" in out  # truncated preview
    dict_out = render_execution(PlanResult("t", "i", (_result("ok", output={"k": "v"}),)))
    assert '{"k": "v"}' in dict_out  # non-string output rendered as JSON
