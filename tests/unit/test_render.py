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


def _result(
    sub_id: str,
    app_id: str,
    app_name: str,
    status: str,
    *,
    output: object = None,
    error: str | None = None,
    source: str | None = "http://127.0.0.1:8006/api/chat",
) -> SubtaskResult:
    return SubtaskResult(
        subtask_id=sub_id,
        app_id=app_id,
        app_name=app_name,
        status=status,
        operation="chat_with_assistant",
        output=output,
        source=source,
        error=error,
        duration_s=1.23,
    )


def _one_ok(output: object) -> tuple[Plan, PlanResult]:
    sub = _sub("t1")  # -> Stanford LLM Course, confidence 0.90, rationale "because"
    plan = _plan((sub,))
    res = _result("t1", sub.app.app_id, sub.app.app_name, "ok", output=output)
    return plan, PlanResult(plan.task, plan.intent, (res,))


def test_execution_clean_shows_plan_and_result() -> None:
    plan, result = _one_ok({"reply": "hello"})
    out = render_execution(plan, result)
    assert "Task: learn transformers" in out
    assert "Intent: build a learning plan" in out
    assert "Plan — 1 subtask(s) in 1 step(s):" in out
    assert "-> Stanford LLM Course  (confidence 0.90)" in out
    assert "why: because" in out
    assert "Results:" in out
    assert "reply" in out  # real output shown
    assert "source: http://127.0.0.1:8006/api/chat" in out


def test_execution_clean_hides_operational_detail() -> None:
    plan, result = _one_ok({"reply": "hi"})
    out = render_execution(plan, result)  # not verbose
    assert "op=" not in out
    assert "status=" not in out
    assert "chat_with_assistant" not in out  # operation name is operational detail
    assert "1.23s" not in out


def test_execution_verbose_adds_detail() -> None:
    plan, result = _one_ok({"reply": "hi"})
    out = render_execution(plan, result, verbose=True)
    assert "op=chat_with_assistant" in out
    assert "status=ok" in out
    assert "1.23s" in out


def test_execution_verbose_output_untruncated() -> None:
    long_text = "y" * 800
    plan, result = _one_ok(long_text)
    assert "…" in render_execution(plan, result)  # truncated in clean
    verbose = render_execution(plan, result, verbose=True)
    assert "…" not in verbose
    assert long_text in verbose


def test_execution_error_and_skipped_and_missing() -> None:
    arxiv = _app(app_id="arxiv-papers", name="ArXiv Paper Guide")
    fb = _app(app_id="web-search", name="Web Search (fallback)", fb=True)
    subs = (_sub("t1", app=arxiv), _sub("t2", app=fb), _sub("t3", ("t1", "t2")))
    plan = _plan(subs)
    results = (
        _result("t1", "arxiv-papers", "ArXiv Paper Guide", "error", error="retry: boom"),
        _result("t2", "web-search", "Web Search (fallback)", "skipped", error="deferred"),
        # no result for t3 -> "(no result)" branch
    )
    out = render_execution(plan, PlanResult(plan.task, plan.intent, results))
    assert "Step 1 (parallel):" in out  # t1 + t2 independent
    assert "(needs t1, t2)" in out  # t3 dependency
    assert "[fallback]" in out  # t2 is the fallback app
    assert "could not complete: retry: boom" in out
    assert "(not executed — deferred)" in out
    assert "(no result)" in out  # t3 has no result


def test_execution_ok_without_source_omits_source_line() -> None:
    sub = _sub("t1")
    plan = _plan((sub,))
    res = _result("t1", sub.app.app_id, sub.app.app_name, "ok", output="hi", source=None)
    out = render_execution(plan, PlanResult(plan.task, plan.intent, (res,)))
    assert "source:" not in out
