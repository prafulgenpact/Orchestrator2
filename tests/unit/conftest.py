"""Shared unit-test helpers: an in-memory fake LLM client.

Exposed as the ``fake_llm`` fixture (a factory) so any test can create a client
that returns queued responses and records the requests it received — no network.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import pytest

from orchestrator.llm.base import LLMRequest


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
