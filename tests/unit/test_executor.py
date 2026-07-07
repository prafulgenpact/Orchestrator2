"""Unit tests for the executor — full plan run with the HTTP call stubbed (no network)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from typing import Any

import httpx
import pytest
from conftest import FakeLLM

from orchestrator.app_caller import CallResult
from orchestrator.executor import execute_plan
from orchestrator.models import AppSelection, Plan, PlanResult, Subtask
from orchestrator.registry import AppEntry, AppOperation, load_registry

REG = load_registry()
MakeLLM = Callable[[Sequence[str]], FakeLLM]


def _sub(app_id: str, app_name: str, fallback: bool = False) -> Subtask:
    app = AppSelection(app_id, app_name, "because", 0.9, fallback)
    return Subtask("t1", "Find papers", "find recent MoE papers", (), app)


def _plan(*subs: Subtask) -> Plan:
    return Plan("task", "intent", subs, "claude-opus-4-8", "1")


def _dummy_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(lambda _r: httpx.Response(200)))


def _stub_call(**canned: Any) -> Callable[..., Any]:
    async def _call(
        app: AppEntry, op: AppOperation, args: dict[str, Any], **_kw: Any
    ) -> CallResult:
        return CallResult(
            app.id,
            op.name,
            f"http://x{op.path}",
            canned.get("ok", True),
            canned.get("status", 200),
            {"echo": args},
            canned.get("error"),
            0.01,
        )

    return _call


def _run(plan: Plan, client: FakeLLM) -> PlanResult:
    async def go() -> PlanResult:
        async with _dummy_client() as http:
            return await execute_plan(plan, REG, llm_client=client, http_client=http, model="m")

    return asyncio.run(go())


def test_execute_success(monkeypatch: pytest.MonkeyPatch, fake_llm: MakeLLM) -> None:
    monkeypatch.setattr("orchestrator.executor.call_operation", _stub_call())
    client = fake_llm(['{"operation": "search_papers_by_query", "arguments": {"query": "moe"}}'])
    result = _run(_plan(_sub("arxiv-papers", "ArXiv Paper Guide")), client)
    assert len(result.results) == 1
    r = result.results[0]
    assert r.status == "ok"
    assert r.operation == "search_papers_by_query"
    assert r.output == {"echo": {"query": "moe"}}
    assert r.source is not None


def test_execute_skips_fallback(fake_llm: MakeLLM) -> None:
    # no LLM response needed: the fallback subtask is skipped before any selector call
    result = _run(_plan(_sub("web-search", "Web Search (fallback)", fallback=True)), fake_llm([]))
    assert result.results[0].status == "skipped"
    assert "fallback" in (result.results[0].error or "")


def test_execute_selection_error_is_isolated(
    monkeypatch: pytest.MonkeyPatch, fake_llm: MakeLLM
) -> None:
    monkeypatch.setattr("orchestrator.executor.call_operation", _stub_call())
    client = fake_llm(["this is not valid json"])
    result = _run(_plan(_sub("arxiv-papers", "ArXiv Paper Guide")), client)
    assert result.results[0].status == "error"
    assert "JSON" in (result.results[0].error or "")


def test_execute_unknown_app_is_error(fake_llm: MakeLLM) -> None:
    result = _run(_plan(_sub("ghost-app", "Ghost App")), fake_llm([]))
    assert result.results[0].status == "error"
    assert "unknown app" in (result.results[0].error or "")


def test_execute_call_failure_recorded(monkeypatch: pytest.MonkeyPatch, fake_llm: MakeLLM) -> None:
    monkeypatch.setattr(
        "orchestrator.executor.call_operation", _stub_call(ok=False, error="retry: boom")
    )
    client = fake_llm(['{"operation": "search_papers_by_query", "arguments": {"query": "x"}}'])
    result = _run(_plan(_sub("arxiv-papers", "ArXiv Paper Guide")), client)
    assert result.results[0].status == "error"
    assert result.results[0].error == "retry: boom"
