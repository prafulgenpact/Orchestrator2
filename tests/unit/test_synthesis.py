"""Unit tests for the synthesis step (AC-4) — no network; FakeLLM."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from conftest import FakeLLM

from orchestrator.models import PlanResult, SubtaskResult
from orchestrator.synthesis import Synthesis, _render_output, synthesize

MakeLLM = Callable[[Sequence[str]], FakeLLM]


def _res(
    sub_id: str,
    output: Any,
    *,
    status: str = "ok",
    operation: str | None = "op",
    source: str | None = None,
    app_name: str = "App",
) -> SubtaskResult:
    return SubtaskResult(
        subtask_id=sub_id,
        app_id="app-id",
        app_name=app_name,
        status=status,
        operation=operation,
        output=output,
        source=source,
        error=None,
        duration_s=1.0,
    )


def _plan_result(*results: SubtaskResult, task: str = "do the thing") -> PlanResult:
    return PlanResult(task=task, intent="intent", results=tuple(results))


# --- synthesize: the three modes --------------------------------------------


def test_single_prose_result_is_verbatim(fake_llm: MakeLLM) -> None:
    client = fake_llm([])  # verbatim must make NO LLM call
    pr = _plan_result(_res("t1", "  The answer is 42.  ", source="http://x"))
    s = synthesize(client, pr, model="m")
    assert s.mode == "verbatim"
    assert s.answer == "The answer is 42."  # stripped, passed through untouched
    assert s.sources == ("http://x",)
    assert client.requests == []  # proves no LLM call was made


def test_no_ok_results_is_none(fake_llm: MakeLLM) -> None:
    client = fake_llm([])  # none must make NO LLM call
    pr = _plan_result(
        _res("t1", None, status="error", source="http://x"),
        _res("t2", None, status="skipped"),
    )
    s = synthesize(client, pr, model="m")
    assert s.mode == "none"
    assert "no answer" in s.answer.lower()
    assert s.sources == ()
    assert client.requests == []


def test_multiple_results_are_synthesized(fake_llm: MakeLLM) -> None:
    client = fake_llm(["  Fused grounded answer.  "])
    pr = _plan_result(
        _res("t1", ["Paper A", "Paper B"], operation="search", source="http://a"),
        _res("t2", "Detailed takeaways text", operation="analyze", source="http://b"),
    )
    s = synthesize(client, pr, model="m")
    assert s.mode == "synthesized"
    assert s.answer == "Fused grounded answer."  # stripped
    assert s.sources == ("http://a", "http://b")
    # the synthesizer's message carried BOTH results (list + prose) and their operations
    msg = client.requests[0].messages[0]["content"]
    assert "Paper A" in msg and "Detailed takeaways text" in msg
    assert "(search)" in msg and "(analyze)" in msg
    assert "do the thing" in msg  # the task is included


def test_single_nonprose_result_is_synthesized(fake_llm: MakeLLM) -> None:
    # One ok result, but structured data (not prose) -> LLM phrases it. operation=None branch.
    client = fake_llm(["Answer from the list."])
    pr = _plan_result(_res("t1", [{"title": "P1"}], operation=None, source="http://a"))
    s = synthesize(client, pr, model="m")
    assert s.mode == "synthesized"
    assert s.answer == "Answer from the list."
    assert len(client.requests) == 1
    assert "(None)" not in client.requests[0].messages[0]["content"]  # no op suffix


def test_single_empty_string_result_is_synthesized(fake_llm: MakeLLM) -> None:
    # A lone but blank prose result is NOT a verbatim answer -> falls through to synthesis.
    client = fake_llm(["Something grounded."])
    pr = _plan_result(_res("t1", "   ", source="http://a"))
    s = synthesize(client, pr, model="m")
    assert s.mode == "synthesized"
    assert len(client.requests) == 1


def test_sources_collected_from_results(fake_llm: MakeLLM) -> None:
    # sources come from code: deduped, order-preserving, None sources skipped.
    client = fake_llm(["x"])
    pr = _plan_result(
        _res("t1", "a", source="http://dup"),
        _res("t2", "b", source=None),  # no source -> skipped
        _res("t3", "c", source="http://dup"),  # duplicate -> deduped
        _res("t4", "d", source="http://two"),
    )
    s = synthesize(client, pr, model="m")
    assert s.sources == ("http://dup", "http://two")


# --- helpers -----------------------------------------------------------------


def test_render_output_str_json_and_truncation() -> None:
    assert _render_output("  hi  ") == "hi"  # str branch, stripped
    assert _render_output({"k": "v"}) == '{"k": "v"}'  # json branch
    out = _render_output("y" * 5000)  # truncation branch
    assert out.endswith("…")
    assert len(out) <= 3001


def test_synthesis_to_dict() -> None:
    s = Synthesis(answer="a", mode="verbatim", sources=("u1", "u2"))
    assert s.to_dict() == {"answer": "a", "mode": "verbatim", "sources": ["u1", "u2"]}
