"""Unit tests for the relevance guard (no network; FakeLLM).

New contract: the judge sees the app's FULL output (no truncation), empty output is a
deterministic FAIL with no LLM call, and the LLM returns {"verdict": PASS|FAIL} — biased
to PASS, failing OPEN on any parse/LLM error.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from conftest import FakeLLM

from orchestrator.grounding import (
    _is_blank,
    _render_full,
    check_relevance,
    load_system_prompt,
)
from orchestrator.llm.base import LLMError, LLMRequest
from orchestrator.models import AppSelection, Subtask

MakeLLM = Callable[[Sequence[str]], FakeLLM]


class _BoomLLM:
    """An LLM client whose complete() always raises — to prove the guard fails open."""

    def __init__(self) -> None:
        self.requests: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> str:
        self.requests.append(request)
        raise LLMError("model unavailable")


def _subtask() -> Subtask:
    app = AppSelection("arxiv-papers", "ArXiv Paper Guide", "r", 0.9, False)
    return Subtask("t1", "Find papers", "find recent MoE papers", (), app)


def test_verdict_pass(fake_llm: MakeLLM) -> None:
    client = fake_llm(['{"verdict": "PASS", "reason": "on topic"}'])
    ok, reason = check_relevance(client, _subtask(), [{"title": "MoE"}], model="m")
    assert ok is True
    assert reason == "on topic"


def test_verdict_fail(fake_llm: MakeLLM) -> None:
    client = fake_llm(['{"verdict": "FAIL", "reason": "off-topic keyword match"}'])
    ok, reason = check_relevance(client, _subtask(), [{"title": "OD-VIRAT"}], model="m")
    assert ok is False
    assert "off-topic" in reason


def test_verdict_fail_gets_default_reason(fake_llm: MakeLLM) -> None:
    client = fake_llm(['{"verdict": "FAIL"}'])
    ok, reason = check_relevance(client, _subtask(), "unrelated text", model="m")
    assert ok is False
    assert reason  # a non-empty default reason is supplied


def test_full_output_is_not_truncated(fake_llm: MakeLLM) -> None:
    # A string well past the old 1500-char cap, with a marker only reachable if untruncated.
    long_str = "A" * 2000 + "TAIL_MARKER"
    client = fake_llm(['{"verdict": "PASS"}'])
    check_relevance(client, _subtask(), long_str, model="m")
    msg = client.requests[0].messages[0]["content"]
    assert "TAIL_MARKER" in msg
    assert long_str in msg  # the ENTIRE output is present, verbatim

    # A large dict: a value buried deep must also survive whole.
    big = {"preview_html": "X" * 3000, "marker": "DEEP_VALUE"}
    client2 = fake_llm(['{"verdict": "PASS"}'])
    check_relevance(client2, _subtask(), big, model="m")
    assert "DEEP_VALUE" in client2.requests[0].messages[0]["content"]


def test_blank_output_fails_without_llm(fake_llm: MakeLLM) -> None:
    for blank in (None, "", "   ", [], {}):
        client = fake_llm([])  # empty queue: any LLM call would raise AssertionError
        ok, reason = check_relevance(client, _subtask(), blank, model="m")
        assert ok is False, f"{blank!r} should FAIL deterministically"
        assert reason == "the app returned no content"
        assert client.requests == []  # the LLM was never consulted


def test_strips_fences(fake_llm: MakeLLM) -> None:
    client = fake_llm(['```json\n{"verdict": "PASS", "reason": "x"}\n```'])
    ok, _ = check_relevance(client, _subtask(), "some text", model="m")
    assert ok is True


def test_fails_open_on_bad_json(fake_llm: MakeLLM) -> None:
    ok, reason = check_relevance(fake_llm(["not json"]), _subtask(), "content", model="m")
    assert ok is True  # never hide a real result on a check error
    assert reason == ""


def test_fails_open_on_non_dict(fake_llm: MakeLLM) -> None:
    ok, reason = check_relevance(fake_llm(["[1, 2, 3]"]), _subtask(), "content", model="m")
    assert ok is True
    assert reason == ""


def test_fails_open_on_unknown_verdict(fake_llm: MakeLLM) -> None:
    # An unrecognized verdict, and a missing verdict, both keep the result (bias to PASS).
    ok, _ = check_relevance(fake_llm(['{"verdict": "MAYBE"}']), _subtask(), "content", model="m")
    assert ok is True
    ok2, _ = check_relevance(fake_llm(["{}"]), _subtask(), "content", model="m")
    assert ok2 is True


def test_fails_open_on_llm_error() -> None:
    client = _BoomLLM()
    ok, reason = check_relevance(client, _subtask(), "content", model="m")
    assert ok is True  # an LLM failure must not discard the app's real answer
    assert reason == ""
    assert client.requests  # it did attempt the call


def test_prompt_states_pass_fail_rules() -> None:
    prompt = load_system_prompt()
    assert "PASS" in prompt and "FAIL" in prompt
    assert "doubt" in prompt.lower() or "unsure" in prompt.lower()
    assert "Be strict" not in prompt  # the old strict bias is gone


# --- helpers -----------------------------------------------------------------


def test_is_blank() -> None:
    assert _is_blank(None) and _is_blank("") and _is_blank("  ") and _is_blank([]) and _is_blank({})
    assert not _is_blank("x")
    assert not _is_blank([1])
    assert not _is_blank(0)  # a scalar 0 is content, not blank


def test_render_full_passes_string_through_and_serializes_objects() -> None:
    assert _render_full("hello world") == "hello world"
    assert "42" in _render_full({"n": 42})
