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
from orchestrator.synthesis import Synthesis


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
    note: str | None = None,
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
        note=note,
    )


def _one_ok(output: object) -> tuple[Plan, PlanResult]:
    sub = _sub("t1")  # -> Stanford LLM Course, confidence 0.90, rationale "because"
    plan = _plan((sub,))
    res = _result("t1", sub.app.app_id, sub.app.app_name, "ok", output=output)
    return plan, PlanResult(plan.task, plan.intent, (res,))


def test_render_execution_can_omit_answer() -> None:
    # include_answer=False (used when the CLI streams the answer itself) drops the Answer/Sources
    # block but keeps everything else, so the answer is never printed twice.
    plan, result = _one_ok({"reply": "hello"})
    syn = Synthesis(answer="The streamed answer.", mode="synthesized", sources=("http://s",))
    with_answer = render_execution(plan, result, syn)
    without = render_execution(plan, result, syn, include_answer=False)
    assert "Answer:" in with_answer and "The streamed answer." in with_answer
    assert "Answer:" not in without
    assert "The streamed answer." not in without
    assert "http://s" not in without  # sources are part of the answer block
    assert "Plan — 1 subtask(s)" in without  # the rest is still rendered
    assert "Results:" in without


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


def test_execution_lists_results() -> None:
    papers = [{"title": f"Paper {i}"} for i in range(6)]
    plan, result = _one_ok(papers)
    out = render_execution(plan, result)
    assert "— 6 result(s)" in out
    assert "1. Paper 0" in out
    assert "5. Paper 4" in out
    assert "… (1 more)" in out  # top 5 shown, 1 more summarized


def test_execution_no_match() -> None:
    sub = _sub("t1")
    plan = _plan((sub,))
    res = _result(
        "t1", sub.app.app_id, sub.app.app_name, "no_match", error="arXiv has nothing on this"
    )
    out = render_execution(plan, PlanResult(plan.task, plan.intent, (res,)))
    assert "no relevant results found — arXiv has nothing on this" in out


def test_execution_list_truncates_titles_and_omits_more_for_short_lists() -> None:
    items = [{"title": "T" * 200}, {"title": "short"}]  # 2 items, one very long
    plan, result = _one_ok(items)
    out = render_execution(plan, result)
    assert "— 2 result(s)" in out
    assert "…" in out  # long title truncated by _one_line
    assert "more)" not in out  # only 2 items -> no "(N more)" line


def test_execution_list_of_scalars() -> None:
    plan, result = _one_ok(["alpha", "beta"])  # non-dict list items
    out = render_execution(plan, result)
    assert "— 2 result(s)" in out
    assert "1. alpha" in out
    assert "2. beta" in out


# --- render_execution with a synthesis (the Answer section) ------------------


def test_execution_renders_answer_section() -> None:
    plan, result = _one_ok({"reply": "hi"})
    synthesis = Synthesis(
        answer="Mixture-of-experts routes tokens to specialized sub-networks.",
        mode="synthesized",
        sources=("http://127.0.0.1:8002/paper/1", "http://127.0.0.1:8002/paper/2"),
    )
    out = render_execution(plan, result, synthesis)
    # the answer leads, above the plan/results
    assert out.index("Answer:") < out.index("Plan —") < out.index("Results:")
    assert "Mixture-of-experts routes tokens" in out
    assert "  Sources:" in out
    assert "    - http://127.0.0.1:8002/paper/1" in out
    assert "    - http://127.0.0.1:8002/paper/2" in out
    # per-step detail still present below the answer
    assert "-> Stanford LLM Course  (confidence 0.90)" in out


def test_execution_answer_multiline_and_no_sources() -> None:
    plan, result = _one_ok("hi")
    synthesis = Synthesis(answer="line one\nline two", mode="verbatim", sources=())
    out = render_execution(plan, result, synthesis)
    assert "  line one" in out
    assert "  line two" in out
    assert "Sources:" not in out  # no sources -> no Sources block


def test_execution_without_synthesis_has_no_answer() -> None:
    plan, result = _one_ok({"reply": "hi"})
    out = render_execution(plan, result)  # synthesis omitted (backward compatible)
    assert "Answer:" not in out


def test_execution_announces_fallback() -> None:
    sub = _sub("t1")
    plan = _plan((sub,))
    res = _result(
        "t1",
        "web-search",
        "Web Search (fallback)",
        "ok",
        output={"answer": "x"},
        note="'Statistics Teacher' could not handle this; answered via web search instead",
    )
    synth = Synthesis(answer="A p-value is ...", mode="synthesized", sources=("http://w",))
    out = render_execution(plan, PlanResult(plan.task, plan.intent, (res,)), synth)
    assert "Heads up" in out  # explicit disclosure banner
    assert "Statistics Teacher" in out and "web search" in out
    assert out.index("Heads up") < out.index("Plan —")  # announced up front, before the plan


def test_execution_no_fallback_block_when_none() -> None:
    plan, result = _one_ok({"reply": "hi"})  # no note on the result
    out = render_execution(plan, result)
    assert "Heads up" not in out


def test_failed_subtasks_surface_as_heads_up() -> None:
    # A chosen app that failed must be flagged right under the answer (never hidden behind a
    # confident synthesized answer built only from the ok results) — the Fix 2 honesty guarantee.
    sub = _sub("t1")
    plan = _plan((sub,))
    res = _result(
        "t1",
        sub.app.app_id,
        sub.app.app_name,
        "error",
        error="health check failed for arxiv-papers",
    )
    synth = Synthesis(answer="Partial answer.", mode="synthesized", sources=())
    out = render_execution(plan, PlanResult(plan.task, plan.intent, (res,)), synth)
    assert "Some parts of the task could not be completed" in out
    assert "health check failed for arxiv-papers" in out
    assert out.index("could not be completed") < out.index("Plan —")  # up front, not buried
