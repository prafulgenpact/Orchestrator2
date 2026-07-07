"""Unit tests for the operation selector — grounded operation + argument choice (no network)."""

from __future__ import annotations

from collections.abc import Callable, Sequence

import pytest
from conftest import FakeLLM

from orchestrator.models import AppSelection, Subtask
from orchestrator.registry import AppEntry, AppOperation, RetrySpec, load_registry
from orchestrator.selector import SelectionError, select_operation

REG = load_registry()
MakeLLM = Callable[[Sequence[str]], FakeLLM]


def _arxiv() -> AppEntry:
    app = REG.get("arxiv-papers")
    assert app is not None
    return app


def _subtask() -> Subtask:
    app = AppSelection("arxiv-papers", "ArXiv Paper Guide", "searches arxiv", 0.9, False)
    return Subtask("t1", "Find papers", "find recent MoE papers", (), app)


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
        select_operation(client, _arxiv(), _subtask(), model="m")


def test_select_bad_json_raises(fake_llm: MakeLLM) -> None:
    client = fake_llm(["not json at all"])
    with pytest.raises(SelectionError, match="not valid JSON"):
        select_operation(client, _arxiv(), _subtask(), model="m")


def test_select_non_object_raises(fake_llm: MakeLLM) -> None:
    client = fake_llm(["[1, 2, 3]"])
    with pytest.raises(SelectionError, match="must be a JSON object"):
        select_operation(client, _arxiv(), _subtask(), model="m")


def test_select_missing_operation_name_raises(fake_llm: MakeLLM) -> None:
    client = fake_llm(['{"arguments": {"query": "x"}}'])
    with pytest.raises(SelectionError, match="missing a valid 'operation'"):
        select_operation(client, _arxiv(), _subtask(), model="m")


def test_select_bad_arguments_type_raises(fake_llm: MakeLLM) -> None:
    client = fake_llm(['{"operation": "search_papers_by_query", "arguments": "nope"}'])
    with pytest.raises(SelectionError, match="'arguments' must be an object"):
        select_operation(client, _arxiv(), _subtask(), model="m")
