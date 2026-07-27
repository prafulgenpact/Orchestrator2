"""Unit tests for the LLM request model and the record/replay layer."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import FakeLLM  # pytest adds tests/unit/ to sys.path (prepend import mode)

from orchestrator.llm.base import LLMRequest
from orchestrator.llm.replay import (
    DEFAULT_FIXTURE_DIR,
    MissingFixtureError,
    RecordingClient,
    ReplayClient,
    _fixture_dir,
    request_hash,
)


def _req(content: str = "plan my week") -> LLMRequest:
    return LLMRequest(
        model="claude-opus-4-6",
        system="you are a planner",
        messages=({"role": "user", "content": content},),
    )


def test_request_to_dict_shape() -> None:
    data = _req().to_dict()
    assert data["model"] == "claude-opus-4-6"
    assert data["messages"] == [{"role": "user", "content": "plan my week"}]
    assert data["max_tokens"] == 8000


def test_request_hash_is_stable_and_distinct() -> None:
    assert request_hash(_req()) == request_hash(_req())
    assert request_hash(_req("a")) != request_hash(_req("b"))
    assert len(request_hash(_req())) == 16


def test_temperature_not_in_request_hash() -> None:
    # Two requests differing ONLY in temperature must hash identically, so adding a temperature
    # default (0.0) does not invalidate any recorded fixture — temperature doesn't change a replay.
    from dataclasses import replace

    base = _req()
    hot = replace(base, temperature=1.0)
    assert base.temperature == 0.0
    assert request_hash(base) == request_hash(hot)
    assert "temperature" not in base.to_dict()


def test_replay_reads_a_fixture(tmp_path: Path) -> None:
    req = _req()
    (tmp_path / f"{request_hash(req)}.json").write_text(
        json.dumps({"request": req.to_dict(), "response_text": "hello"})
    )
    assert ReplayClient(tmp_path).complete(req) == "hello"


def test_replay_missing_fixture_raises(tmp_path: Path) -> None:
    with pytest.raises(MissingFixtureError, match="record it with AGENT_LLM_MODE=record"):
        ReplayClient(tmp_path).complete(_req())


def test_record_then_replay_round_trip(tmp_path: Path) -> None:
    inner = FakeLLM(["recorded answer"])
    recorder = RecordingClient(inner, tmp_path)
    assert recorder.complete(_req()) == "recorded answer"
    # the fixture now exists and replay serves it without touching the inner client
    assert ReplayClient(tmp_path).complete(_req()) == "recorded answer"
    assert len(inner.requests) == 1


def test_recording_client_creates_dir(tmp_path: Path) -> None:
    nested = tmp_path / "does" / "not" / "exist"
    RecordingClient(FakeLLM(["x"]), nested).complete(_req())
    assert (nested / f"{request_hash(_req())}.json").exists()


def test_fixture_dir_override(tmp_path: Path) -> None:
    assert _fixture_dir(tmp_path) == tmp_path


def test_fixture_dir_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LLM_FIXTURES", "/tmp/fixtures-xyz")
    assert _fixture_dir(None) == Path("/tmp/fixtures-xyz")


def test_fixture_dir_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LLM_FIXTURES", raising=False)
    assert _fixture_dir(None) == DEFAULT_FIXTURE_DIR


def test_fake_llm_fixture_factory(fake_llm: Callable[..., FakeLLM]) -> None:
    client = fake_llm(["one"])
    assert client.complete(_req()) == "one"
    with pytest.raises(AssertionError, match="ran out"):
        client.complete(_req())
