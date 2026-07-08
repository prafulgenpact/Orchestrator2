"""Unit tests for the relevance guard (no network; FakeLLM)."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from conftest import FakeLLM

from orchestrator.grounding import _summarize, check_relevance
from orchestrator.models import AppSelection, Subtask

MakeLLM = Callable[[Sequence[str]], FakeLLM]


def _subtask() -> Subtask:
    app = AppSelection("arxiv-papers", "ArXiv Paper Guide", "r", 0.9, False)
    return Subtask("t1", "Find papers", "find recent MoE papers", (), app)


def test_relevance_true(fake_llm: MakeLLM) -> None:
    client = fake_llm(['{"relevant": true, "reason": "on topic"}'])
    ok, reason = check_relevance(client, _subtask(), [{"title": "MoE"}], model="m")
    assert ok is True
    assert reason == "on topic"


def test_relevance_false(fake_llm: MakeLLM) -> None:
    client = fake_llm(['{"relevant": false, "reason": "off-topic keyword match"}'])
    ok, reason = check_relevance(client, _subtask(), [{"title": "OD-VIRAT"}], model="m")
    assert ok is False
    assert "off-topic" in reason


def test_relevance_strips_fences(fake_llm: MakeLLM) -> None:
    client = fake_llm(['```json\n{"relevant": true, "reason": "x"}\n```'])
    ok, _ = check_relevance(client, _subtask(), "some text", model="m")
    assert ok is True


def test_relevance_fails_open_on_bad_json(fake_llm: MakeLLM) -> None:
    ok, reason = check_relevance(fake_llm(["not json"]), _subtask(), [], model="m")
    assert ok is True  # never hide results on a check error
    assert reason == ""


def test_relevance_fails_open_on_non_dict(fake_llm: MakeLLM) -> None:
    ok, reason = check_relevance(fake_llm(["[1, 2, 3]"]), _subtask(), [], model="m")
    assert ok is True
    assert reason == ""


# --- _summarize --------------------------------------------------------------


def test_summarize_prefers_title() -> None:
    assert "MoE paper" in _summarize([{"title": "MoE paper", "abstract": "long..."}])


def test_summarize_field_fallbacks() -> None:
    assert "nm" in _summarize([{"name": "nm"}])
    assert "idv" in _summarize([{"id": "idv"}])
    assert "foo" in _summarize([{"foo": "bar"}])  # no title/name/id -> str(dict)


def test_summarize_scalars_and_string_and_dict() -> None:
    assert "alpha" in _summarize(["alpha", "beta"])
    assert _summarize("hello   world") == "hello world"
    assert "k" in _summarize({"k": "v"})


def test_summarize_truncates() -> None:
    assert len(_summarize("x" * 5000)) <= 1500


def test_relevance_open_fence_without_close(fake_llm: MakeLLM) -> None:
    client = fake_llm(['```\n{"relevant": false, "reason": "no"}'])
    ok, reason = check_relevance(client, _subtask(), "x", model="m")
    assert ok is False
    assert reason == "no"


def test_relevance_defaults_when_keys_missing(fake_llm: MakeLLM) -> None:
    ok, reason = check_relevance(fake_llm(["{}"]), _subtask(), "x", model="m")
    assert ok is True  # absent "relevant" defaults to True
    assert reason == ""
