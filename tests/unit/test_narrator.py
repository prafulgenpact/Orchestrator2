"""Unit tests for the step narrator (fake LLM client — no network)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

from orchestrator import narrator
from orchestrator.llm.base import LLMClient, LLMRequest
from orchestrator.models import SubtaskResult


@dataclass
class _FakeClient:
    """Returns a canned narration (or raises), recording every request it saw."""

    reply: str = "Data loaded — 1,470 rows, 35 features."
    boom: bool = False
    requests: list[LLMRequest] = field(default_factory=list)

    def complete(self, request: LLMRequest) -> str:
        self.requests.append(request)
        if self.boom:
            raise RuntimeError("llm down")
        return self.reply


def _result(status: str = "ok", output: Any = None, error: str | None = None) -> SubtaskResult:
    return SubtaskResult(
        "t1",
        "coding-playground",
        "Coding Playground",
        status,
        "run_code",
        output if output is not None else {"rows": 1470, "cols": 35},
        None,
        error,
        1.2,
    )


def test_narrate_result_returns_stripped_text() -> None:
    client = _FakeClient(reply="  Data loaded — 1,470 rows.  \n")
    text = narrator.narrate_result(
        cast(LLMClient, client),
        model="m",
        task="blog on ML in HR",
        result=_result(),
        step_title="Load dataset",
    )
    assert text == "Data loaded — 1,470 rows."
    assert len(client.requests) == 1
    assert client.requests[0].max_tokens == narrator._MAX_TOKENS


def test_narrate_result_swallows_llm_errors() -> None:
    client = _FakeClient(boom=True)
    text = narrator.narrate_result(cast(LLMClient, client), model="m", task="t", result=_result())
    assert text == ""  # narration failure is silent — never an exception


def test_build_user_message_carries_the_step_facts() -> None:
    msg = narrator.build_user_message(
        "blog on ML in HR",
        _result(),
        step_title="Load dataset",
        step_description="Load the IBM HR attrition dataset.",
    )
    assert "blog on ML in HR" in msg
    assert "Load dataset" in msg
    assert "Load the IBM HR attrition dataset." in msg
    assert "Coding Playground" in msg
    assert "STATUS: ok" in msg
    assert '"rows": 1470' in msg
    assert "ERROR:" not in msg  # no error line on a successful step


def test_build_user_message_carries_the_error_on_failure() -> None:
    msg = narrator.build_user_message(
        "t", _result(status="error", output=None, error="kernel timed out")
    )
    assert "STATUS: error" in msg
    assert "ERROR: kernel timed out" in msg


def test_build_user_message_truncates_long_output() -> None:
    msg = narrator.build_user_message("t", _result(output="x" * 100_000))
    assert len(msg) < 100_000
    assert "x" * narrator._OUTPUT_LIMIT in msg
    assert "x" * (narrator._OUTPUT_LIMIT + 1) not in msg


def test_output_excerpt_handles_unserializable_values() -> None:
    class _Odd:
        def __repr__(self) -> str:
            return "<odd>"

    assert narrator._output_excerpt(None) == ""
    assert "odd" in narrator._output_excerpt(_Odd())
