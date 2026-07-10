"""Unit tests for the operation selector — grounded operation + argument choice (no network)."""

from __future__ import annotations

from collections.abc import Callable, Sequence

import pytest
from conftest import FakeLLM

from orchestrator.models import AppSelection, Subtask, SubtaskResult
from orchestrator.registry import AppEntry, AppOperation, RetrySpec, load_registry
from orchestrator.selector import SelectionError, build_select_message, select_operation

REG = load_registry()
MakeLLM = Callable[[Sequence[str]], FakeLLM]


def _arxiv() -> AppEntry:
    app = REG.get("arxiv-papers")
    assert app is not None
    return app


def _subtask() -> Subtask:
    app = AppSelection("arxiv-papers", "ArXiv Paper Guide", "searches arxiv", 0.9, False)
    return Subtask("t1", "Find papers", "find recent MoE papers", (), app)


def _upstream_result(output: object) -> SubtaskResult:
    return SubtaskResult(
        "t1",
        "arxiv-papers",
        "ArXiv Paper Guide",
        "ok",
        "search_papers_by_query",
        output,
        "http://arxiv/x",
        None,
        0.01,
    )


def test_select_success(fake_llm: MakeLLM) -> None:
    client = fake_llm(
        ['{"operation": "search_papers_by_query", "arguments": {"query": "moe", "max_results": 5}}']
    )
    op, args = select_operation(client, _arxiv(), _subtask(), model="m")
    assert op.name == "search_papers_by_query"
    assert args == {"query": "moe", "max_results": 5}


def test_select_strips_code_fences(fake_llm: MakeLLM) -> None:
    client = fake_llm(
        ['```json\n{"operation": "get_paper_by_id", "arguments": {"arxiv_id": "2401.00001"}}\n```']
    )
    op, args = select_operation(client, _arxiv(), _subtask(), model="m")
    assert op.name == "get_paper_by_id"
    assert args == {"arxiv_id": "2401.00001"}


def test_select_open_fence_without_close(fake_llm: MakeLLM) -> None:
    client = fake_llm(['```\n{"operation": "get_paper_by_id", "arguments": {"arxiv_id": "1"}}'])
    op, args = select_operation(client, _arxiv(), _subtask(), model="m")
    assert op.name == "get_paper_by_id"
    assert args == {"arxiv_id": "1"}


def test_select_filters_unknown_arguments(fake_llm: MakeLLM) -> None:
    client = fake_llm(
        ['{"operation": "search_papers_by_query", "arguments": {"query": "x", "bogus": 1}}']
    )
    _, args = select_operation(client, _arxiv(), _subtask(), model="m")
    assert args == {"query": "x"}  # "bogus" is not a request_field -> dropped


def test_select_keeps_all_args_when_no_request_fields(fake_llm: MakeLLM) -> None:
    op = AppOperation(
        name="noargs",
        description="d",
        method="POST",
        path="/x",
        timeout_s=30,
        destructive=False,
        idempotency="none",
        retry=RetrySpec(0, 0.0),
    )
    app = AppEntry("custom", "Custom", "d", (), (), False, port=8099, health="/h", operations=(op,))
    client = fake_llm(['{"operation": "noargs", "arguments": {"anything": 1}}'])
    _, args = select_operation(client, app, _subtask(), model="m")
    assert args == {"anything": 1}


def test_select_unknown_operation_raises(fake_llm: MakeLLM) -> None:
    client = fake_llm(['{"operation": "does_not_exist", "arguments": {}}'])
    with pytest.raises(SelectionError, match="has no operation"):
        select_operation(client, _arxiv(), _subtask(), model="m", max_retries=0)


def test_select_bad_json_raises(fake_llm: MakeLLM) -> None:
    client = fake_llm(["not json at all"])
    with pytest.raises(SelectionError, match="not valid JSON"):
        select_operation(client, _arxiv(), _subtask(), model="m", max_retries=0)


def test_select_non_object_raises(fake_llm: MakeLLM) -> None:
    client = fake_llm(["[1, 2, 3]"])
    with pytest.raises(SelectionError, match="must be a JSON object"):
        select_operation(client, _arxiv(), _subtask(), model="m", max_retries=0)


def test_select_missing_operation_name_raises(fake_llm: MakeLLM) -> None:
    client = fake_llm(['{"arguments": {"query": "x"}}'])
    with pytest.raises(SelectionError, match="missing a valid 'operation'"):
        select_operation(client, _arxiv(), _subtask(), model="m", max_retries=0)


def test_select_bad_arguments_type_raises(fake_llm: MakeLLM) -> None:
    client = fake_llm(['{"operation": "search_papers_by_query", "arguments": "nope"}'])
    with pytest.raises(SelectionError, match="'arguments' must be an object"):
        select_operation(client, _arxiv(), _subtask(), model="m", max_retries=0)


# --- retry on malformed JSON (self-correction, mirrors the planner) ----------


def test_select_retries_then_succeeds(fake_llm: MakeLLM) -> None:
    # first reply is invalid JSON (a raw newline inside a string value); the retry recovers
    bad = '{"operation": "search_papers_by_query", "arguments": {"query": "line1\nline2"'
    good = '{"operation": "search_papers_by_query", "arguments": {"query": "moe"}}'
    client = fake_llm([bad, good])
    op, args = select_operation(client, _arxiv(), _subtask(), model="m", max_retries=1)
    assert op.name == "search_papers_by_query"
    assert args == {"query": "moe"}
    assert len(client.requests) == 2  # it took a second attempt
    assert "invalid" in client.requests[1].messages[-1]["content"]  # error fed back to the model


def test_select_exhausts_retries(fake_llm: MakeLLM) -> None:
    client = fake_llm(["nope", "still bad"])  # 2 responses = 2 attempts (max_retries=1)
    with pytest.raises(SelectionError, match="not valid JSON"):
        select_operation(client, _arxiv(), _subtask(), model="m", max_retries=1)
    assert len(client.requests) == 2  # both attempts consumed, original error re-raised


# --- data flow between steps (Task 1: upstream results reach the selector) ---


def test_message_has_no_upstream_section_when_none() -> None:
    # backward compatible: without dependencies, no UPSTREAM block is emitted
    message = build_select_message(_arxiv(), _subtask())
    assert "UPSTREAM" not in message


def test_message_includes_upstream_list_with_ids() -> None:
    # a downstream step must be able to see the arxiv_id an earlier step returned
    upstream = (_upstream_result([{"arxiv_id": "2401.12345", "title": "MoE paper"}]),)
    message = build_select_message(_arxiv(), _subtask(), upstream)
    assert "UPSTREAM RESULTS" in message
    assert "[t1]" in message  # provenance: which step produced it
    assert "2401.12345" in message  # the concrete id survives the summary


def test_upstream_output_is_truncated_when_long() -> None:
    upstream = (_upstream_result("x" * 5000),)
    message = build_select_message(_arxiv(), _subtask(), upstream)
    assert "…" in message  # long output is bounded, not dumped whole


def test_select_can_use_upstream_id_as_argument(fake_llm: MakeLLM) -> None:
    # end-to-end through select_operation: the model picks the id it saw upstream
    upstream = (_upstream_result([{"arxiv_id": "2401.12345"}]),)
    client = fake_llm(['{"operation": "get_paper_by_id", "arguments": {"arxiv_id": "2401.12345"}}'])
    op, args = select_operation(client, _arxiv(), _subtask(), model="m", upstream=upstream)
    assert op.name == "get_paper_by_id"
    assert args == {"arxiv_id": "2401.12345"}
    assert "2401.12345" in client.requests[0].messages[0]["content"]
