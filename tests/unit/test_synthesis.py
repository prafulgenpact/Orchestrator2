"""Unit tests for the synthesis step (AC-4) — no network; FakeLLM."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from conftest import FakeLLM

from orchestrator.models import PlanResult, SubtaskResult
from orchestrator.synthesis import (
    Synthesis,
    _render_output,
    build_synthesis_message,
    load_system_prompt,
    synthesize,
)

MakeLLM = Callable[[Sequence[str]], FakeLLM]


def _res(
    sub_id: str,
    output: Any,
    *,
    status: str = "ok",
    operation: str | None = "op",
    source: str | None = None,
    app_name: str = "App",
    error: str | None = None,
) -> SubtaskResult:
    return SubtaskResult(
        subtask_id=sub_id,
        app_id="app-id",
        app_name=app_name,
        status=status,
        operation=operation,
        output=output,
        source=source,
        error=error,
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


def test_all_failed_answer_names_apps_and_reasons(fake_llm: MakeLLM) -> None:
    # No ok result, but apps failed: the answer must honestly name each app and why — NOT a bland
    # "no answer" and NEVER a web substitute (web is only the planner's no-app route).
    client = fake_llm([])  # none must make NO LLM call
    pr = _plan_result(
        _res("t1", None, status="error", app_name="ArXiv Paper Guide", error="health check failed"),
        _res(
            "t2", None, status="skipped", app_name="Statistics Teacher", error="missing module_id"
        ),
    )
    s = synthesize(client, pr, model="m")
    assert s.mode == "none"
    assert "could not be completed" in s.answer.lower()
    assert "ArXiv Paper Guide" in s.answer and "health check failed" in s.answer
    assert "Statistics Teacher" in s.answer and "missing module_id" in s.answer
    assert s.sources == ()
    assert client.requests == []  # honest failure is built in code, no LLM, no web


def test_no_results_at_all_is_bland_none(fake_llm: MakeLLM) -> None:
    # Degenerate case: a plan with zero results (nothing ran) keeps the plain message.
    client = fake_llm([])
    s = synthesize(client, _plan_result(), model="m")
    assert s.mode == "none"
    assert "no answer" in s.answer.lower()


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


# --- on_delta: stream the fused answer live (stream-answer task) --------------


def _fusion_plan() -> PlanResult:
    # two ok results (a list + prose) force the LLM-fusion path
    return _plan_result(
        _res("t1", ["Paper A"], operation="search", source="http://a"),
        _res("t2", "takeaways", operation="analyze", source="http://b"),
    )


class _StreamingClient:
    """A client that supports complete_stream — streams the fused answer in pieces."""

    def complete(self, _request: Any) -> str:
        raise AssertionError("complete() must not be called when streaming is supported")

    def complete_stream(self, _request: Any, on_delta: Callable[[str], None]) -> str:
        for piece in ("Fu", "sed", " answer"):
            on_delta(piece)
        return "Fused answer"


def test_synthesize_streams_when_supported() -> None:
    deltas: list[str] = []
    s = synthesize(_StreamingClient(), _fusion_plan(), model="m", on_delta=deltas.append)
    assert s.mode == "synthesized"
    assert s.answer == "Fused answer"
    assert deltas == ["Fu", "sed", " answer"]  # streamed live, in order


def test_synthesize_falls_back_to_single_emit(fake_llm: MakeLLM) -> None:
    # A client without complete_stream (FakeLLM) uses complete() and emits the whole answer once,
    # so the CLI still shows it. Proves determinism/CI clients are unaffected.
    client = fake_llm(["Whole fused answer."])
    deltas: list[str] = []
    s = synthesize(client, _fusion_plan(), model="m", on_delta=deltas.append)
    assert s.answer == "Whole fused answer."
    assert deltas == ["Whole fused answer."]  # single whole-string emit


def test_synthesize_pass_through_mode_still_emits(fake_llm: MakeLLM) -> None:
    # The verbatim pass-through path (no LLM call) also feeds the answer to on_delta.
    client = fake_llm([])
    deltas: list[str] = []
    pr = _plan_result(_res("t1", "The answer is 42.", source="http://x"))
    s = synthesize(client, pr, model="m", on_delta=deltas.append)
    assert s.mode == "verbatim"
    assert deltas == ["The answer is 42."]
    assert client.requests == []  # still no LLM call


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


# --- dominant terminal step: pass through instead of re-fusing ---------------


def test_dominant_terminal_passed_through(fake_llm: MakeLLM) -> None:
    client = fake_llm([])  # pass-through must make NO LLM call
    pr = _plan_result(
        _res("t1", ["repoA"], source="http://a"),
        _res("t2", "explanation text", source="http://b"),
        _res("t3", "# Final Blog\nfull content", source="http://c"),
    )
    deps = {"t1": (), "t2": (), "t3": ("t1", "t2")}  # t3 is the sole terminal, consumed t1+t2
    s = synthesize(client, pr, model="m", subtask_deps=deps)
    assert s.mode == "final-step"
    assert s.answer == "# Final Blog\nfull content"  # passed through, not re-fused/truncated
    assert s.sources == ("http://a", "http://b", "http://c")  # sources from ALL ok results
    assert client.requests == []


def test_no_terminal_still_fuses(fake_llm: MakeLLM) -> None:
    client = fake_llm(["fused answer"])
    pr = _plan_result(_res("t1", "a", source="http://a"), _res("t2", "b", source="http://b"))
    deps = {"t1": (), "t2": ()}  # two independent terminals -> no single sink -> fuse
    s = synthesize(client, pr, model="m", subtask_deps=deps)
    assert s.mode == "synthesized"
    assert s.answer == "fused answer"


def test_terminal_must_be_prose(fake_llm: MakeLLM) -> None:
    client = fake_llm(["fused"])
    pr = _plan_result(
        _res("t1", "expl", source="http://a"),
        _res("t2", {"data": 1}, source="http://b"),  # terminal sink but non-prose -> not passed
    )
    deps = {"t1": (), "t2": ("t1",)}
    s = synthesize(client, pr, model="m", subtask_deps=deps)
    assert s.mode == "synthesized"


def test_single_terminal_that_consumed_nothing_falls_back_to_fuse(fake_llm: MakeLLM) -> None:
    client = fake_llm(["fused"])
    # t2 is depended-upon by a (failed, non-ok) t3, so it isn't a terminal; t1 is the lone terminal
    # but depends on nothing -> it didn't consume the others -> fuse rather than pass t1 through.
    pr = _plan_result(_res("t1", "a", source="http://a"), _res("t2", "b", source="http://b"))
    deps = {"t1": (), "t2": (), "t3": ("t2",)}
    s = synthesize(client, pr, model="m", subtask_deps=deps)
    assert s.mode == "synthesized"


def test_synthesis_budget_raised() -> None:
    from orchestrator.synthesis import _MAX_TOKENS

    assert _MAX_TOKENS >= 4000  # fused answers with code/blog excerpts must not truncate


# --- helpers -----------------------------------------------------------------


def test_render_output_str_json_and_truncation() -> None:
    assert _render_output("  hi  ") == "hi"  # str branch, stripped
    assert _render_output({"k": "v"}) == '{"k": "v"}'  # json branch
    out = _render_output("y" * 5000)  # truncation branch
    assert out.endswith("…")
    assert len(out) <= 3001


def test_synthesis_to_dict() -> None:
    s = Synthesis(answer="a", mode="verbatim", sources=("u1", "u2"))
    assert s.to_dict() == {
        "answer": "a",
        "mode": "verbatim",
        "sources": ["u1", "u2"],
        "artifacts": [],
    }


# --- the answer must never describe work that did not happen ------------------------------------
# Live bug (run 39c3bcb9, 2026-08-11): 3 of 4 steps were skipped, yet the answer described the EDA
# and the modelling as if both had run, and never once said "skipped" / "could not" / "unable".
# Cause: the honest failure lines only ran when EVERY step failed; with one success the writer was
# handed the successful results alone and asked to answer the whole task.


def test_synthesis_message_lists_failed_steps() -> None:
    ok = (_res("t1", {"found": "a dataset"}, app_name="Web Search"),)
    failed = (
        _res(
            "t2", None, status="skipped", app_name="Coding Playground", error="no data to work on"
        ),
    )
    msg = build_synthesis_message("do the thing", ok, failed)
    assert "Coding Playground" in msg
    assert "no data to work on" in msg
    assert "t2" in msg


def test_answer_discloses_failures_when_some_succeeded(fake_llm: MakeLLM) -> None:
    client = fake_llm(["Here is what the one working step found."])
    pr = _plan_result(
        _res("t1", {"found": "a dataset"}, app_name="Web Search"),
        _res(
            "t2", None, status="skipped", app_name="Coding Playground", error="no data to work on"
        ),
        _res("t3", None, status="error", app_name="Blogs Playground", error="upstream failed"),
    )
    s = synthesize(client, pr, model="m")
    assert "Coding Playground" in s.answer  # the answer names what did not run
    assert "Blogs Playground" in s.answer
    # and the writer was TOLD, not left to guess
    sent = client.requests[0].messages[0]["content"]
    assert "Coding Playground" in sent


def test_verbatim_answer_still_discloses_failures(fake_llm: MakeLLM) -> None:
    # Pass-through modes must disclose too — otherwise one app's tuned prose hides the failures.
    client = fake_llm([])
    pr = _plan_result(
        _res("t1", "The answer is 42.", app_name="Teach Me"),
        _res("t2", None, status="error", app_name="Coding Playground", error="kernel died"),
    )
    s = synthesize(client, pr, model="m")
    assert s.answer.startswith("The answer is 42.")  # the app's voice is preserved first
    assert "Coding Playground" in s.answer  # then the honest note
    assert "kernel died" in s.answer


def test_final_step_answer_still_discloses_failures(fake_llm: MakeLLM) -> None:
    client = fake_llm([])
    deps = {"t1": (), "t2": ("t1",)}
    pr = _plan_result(
        _res("t1", {"data": 1}, app_name="Coding Playground"),
        _res("t2", "The finished blog post.", app_name="Blogs Playground"),
        _res("t3", None, status="skipped", app_name="Simulated Learning", error="no inputs"),
    )
    s = synthesize(client, pr, model="m", subtask_deps=deps)
    assert "The finished blog post." in s.answer
    assert "Simulated Learning" in s.answer


def test_no_disclosure_when_all_steps_succeeded(fake_llm: MakeLLM) -> None:
    # A clean run must be untouched — no note, no extra section.
    client = fake_llm([])
    pr = _plan_result(_res("t1", "The answer is 42.", app_name="Teach Me"))
    s = synthesize(client, pr, model="m")
    assert s.answer == "The answer is 42."


def test_prompt_requires_reporting_failures() -> None:
    prompt = load_system_prompt().lower()
    assert "did not" in prompt or "failed" in prompt
    assert "never describe work that did not happen" in prompt
