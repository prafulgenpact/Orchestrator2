"""Shared unit-test helpers: an in-memory fake LLM client.

Exposed as the ``fake_llm`` fixture (a factory) so any test can create a client
that returns queued responses and records the requests it received — no network.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from orchestrator.llm.base import LLMRequest


@pytest.fixture(autouse=True)
def _isolate_observability(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep run-recording out of the repo. Recording defaults to the current directory, so without
    this every test that invokes the CLI would litter the repo root with runs/, logs/, and
    observability.db. Point it at a per-test tmp dir; tests that assert on saved runs override
    ORCHESTRATOR_OBS_ROOT explicitly."""
    monkeypatch.setenv("ORCHESTRATOR_OBS_ROOT", str(tmp_path / "_obs"))


class FakeLLM:
    """LLMClient stub: returns queued responses in order; remembers requests seen."""

    def __init__(self, responses: Sequence[str]) -> None:
        self._responses = list(responses)
        self.requests: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> str:
        self.requests.append(request)
        if not self._responses:
            raise AssertionError("FakeLLM ran out of queued responses")
        return self._responses.pop(0)


@pytest.fixture
def fake_llm() -> Callable[[Sequence[str]], FakeLLM]:
    def _make(responses: Sequence[str]) -> FakeLLM:
        return FakeLLM(responses)

    return _make
