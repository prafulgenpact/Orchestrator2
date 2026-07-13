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
from orchestrator.web_search import WebResult, WebSearchError

REG = load_registry()
MakeLLM = Callable[[Sequence[str]], FakeLLM]


@pytest.fixture(autouse=True)
def _web_safety_net_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep executor unit tests offline: the web safety net is disabled unless a test opts in
    (by monkeypatching resolve_search_key back to a key). So a non-ok app result surfaces as-is."""
    monkeypatch.setattr("orchestrator.executor.resolve_search_key", lambda: None)


def _sub(app_id: str, app_name: str, fallback: bool = False) -> Subtask:
    app = AppSelection(app_id, app_name, "because", 0.9, fallback)
    return Subtask("t1", "Find papers", "find recent MoE papers", (), app)


def _sub_id(sub_id: str, depends_on: tuple[str, ...] = ()) -> Subtask:
    app = AppSelection("arxiv-papers", "ArXiv Paper Guide", "because", 0.9, False)
    return Subtask(sub_id, f"step {sub_id}", f"work for {sub_id}", depends_on, app)


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


_SELECT = '{"operation": "search_papers_by_query", "arguments": {"query": "moe"}}'
_RELEVANT = '{"relevant": true, "reason": "on topic"}'
_IRRELEVANT = '{"relevant": false, "reason": "off-topic keyword match"}'


def test_execute_success(monkeypatch: pytest.MonkeyPatch, fake_llm: MakeLLM) -> None:
    monkeypatch.setattr("orchestrator.executor.call_operation", _stub_call())
    client = fake_llm([_SELECT, _RELEVANT])  # selector, then relevance guard
    result = _run(_plan(_sub("arxiv-papers", "ArXiv Paper Guide")), client)
    assert len(result.results) == 1
    r = result.results[0]
    assert r.status == "ok"
    assert r.operation == "search_papers_by_query"
    assert r.output == {"echo": {"query": "moe"}}
    assert r.source is not None


def test_execute_irrelevant_becomes_no_match(
    monkeypatch: pytest.MonkeyPatch, fake_llm: MakeLLM
) -> None:
    monkeypatch.setattr("orchestrator.executor.call_operation", _stub_call())
    client = fake_llm([_SELECT, _IRRELEVANT])  # selector, then relevance says NO
    result = _run(_plan(_sub("arxiv-papers", "ArXiv Paper Guide")), client)
    r = result.results[0]
    assert r.status == "no_match"
    assert r.output is None  # raw (irrelevant) output suppressed
    assert "off-topic" in (r.error or "")


def _fallback_plan() -> Plan:
    return _plan(_sub("web-search", "Web Search (fallback)", fallback=True))


def test_web_fallback_success(monkeypatch: pytest.MonkeyPatch, fake_llm: MakeLLM) -> None:
    monkeypatch.setattr("orchestrator.executor.resolve_search_key", lambda: "k")

    async def _search(_query: str, **_kw: Any) -> WebResult:
        return WebResult(answer="Grounded web answer.", citations=("http://a", "http://b"))

    monkeypatch.setattr("orchestrator.executor.search_web", _search)
    result = _run(_fallback_plan(), fake_llm([]))  # no LLM/selector call on the fallback path
    r = result.results[0]
    assert r.status == "ok"
    assert r.operation == "web_search"
    assert r.output == {"answer": "Grounded web answer.", "citations": ["http://a", "http://b"]}
    assert r.source == "http://a"  # first citation surfaces as provenance


def test_web_fallback_no_citations_has_no_source(
    monkeypatch: pytest.MonkeyPatch, fake_llm: MakeLLM
) -> None:
    monkeypatch.setattr("orchestrator.executor.resolve_search_key", lambda: "k")

    async def _search(_query: str, **_kw: Any) -> WebResult:
        return WebResult(answer="Answer with no citations.", citations=())

    monkeypatch.setattr("orchestrator.executor.search_web", _search)
    r = _run(_fallback_plan(), fake_llm([])).results[0]
    assert r.status == "ok"
    assert r.source is None


def test_web_fallback_no_key(monkeypatch: pytest.MonkeyPatch, fake_llm: MakeLLM) -> None:
    monkeypatch.setattr("orchestrator.executor.resolve_search_key", lambda: None)
    r = _run(_fallback_plan(), fake_llm([])).results[0]
    assert r.status == "skipped"
    assert "TAVILY_API_KEY" in (r.error or "")


def test_web_fallback_error(monkeypatch: pytest.MonkeyPatch, fake_llm: MakeLLM) -> None:
    monkeypatch.setattr("orchestrator.executor.resolve_search_key", lambda: "k")

    async def _boom(_query: str, **_kw: Any) -> WebResult:
        raise WebSearchError("provider down")

    monkeypatch.setattr("orchestrator.executor.search_web", _boom)
    r = _run(_fallback_plan(), fake_llm([])).results[0]
    assert r.status == "error"
    assert "web search failed" in (r.error or "")


def test_execute_selection_error_is_isolated(
    monkeypatch: pytest.MonkeyPatch, fake_llm: MakeLLM
) -> None:
    monkeypatch.setattr("orchestrator.executor.call_operation", _stub_call())
    # the selector retries malformed JSON (default budget 2 -> 3 attempts); all bad -> error
    client = fake_llm(["not json", "still not json", "nope"])
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


def test_execute_threads_upstream_output_into_downstream_selection(
    monkeypatch: pytest.MonkeyPatch, fake_llm: MakeLLM
) -> None:
    """Data flow: step 2's operation is selected WITH step 1's result in the prompt."""
    monkeypatch.setattr("orchestrator.executor.call_operation", _stub_call())
    # LLM call order: t1 select, t1 relevance, t2 select, t2 relevance
    client = fake_llm([_SELECT, _RELEVANT, _SELECT, _RELEVANT])
    plan = _plan(_sub_id("t1"), _sub_id("t2", depends_on=("t1",)))
    result = _run(plan, client)

    assert [r.status for r in result.results] == ["ok", "ok"]
    messages = [r.messages[0]["content"] for r in client.requests]
    assert "UPSTREAM" not in messages[0]  # t1 has no dependencies
    t2_selection = messages[2]  # third LLM call is t2's operation selection
    assert "UPSTREAM" in t2_selection
    assert "moe" in t2_selection  # t1's echoed output reached t2's selection prompt


# required_fields: skip a doomed call when the selector can't ground a required input.
_STATS_SUB = Subtask(
    "t1",
    "Ask stats",
    "what is a p-value?",
    (),
    AppSelection("stats-teacher", "Statistics Teacher", "because", 0.9, False),
)
_STATS_SELECT_BLANK = (
    '{"operation": "ask_question", "arguments": {"question": "q", "module_id": ""}}'
)
_STATS_SELECT_FULL = (
    '{"operation": "ask_question", "arguments": '
    '{"question": "q", "module_id": 1, "module_title": "HT", "module_part": "P1"}}'
)


def test_skips_when_required_field_missing(
    monkeypatch: pytest.MonkeyPatch, fake_llm: MakeLLM
) -> None:
    async def _boom(*_a: Any, **_kw: Any) -> Any:
        raise AssertionError("call_operation must not run when a required field is missing")

    monkeypatch.setattr("orchestrator.executor.call_operation", _boom)
    # module_id is blank; module_title/module_part are absent but get filled by the op defaults,
    # so the residual missing required field is the blank module_id -> still skips, no HTTP call.
    result = _run(_plan(_STATS_SUB), fake_llm([_STATS_SELECT_BLANK]))
    r = result.results[0]
    assert r.status == "skipped"
    assert r.operation == "ask_question"
    assert "module_id" in (r.error or "")


def test_proceeds_when_required_fields_present(
    monkeypatch: pytest.MonkeyPatch, fake_llm: MakeLLM
) -> None:
    monkeypatch.setattr("orchestrator.executor.call_operation", _stub_call())
    result = _run(_plan(_STATS_SUB), fake_llm([_STATS_SELECT_FULL, _RELEVANT]))
    r = result.results[0]
    assert r.status == "ok"  # all required fields present -> the call goes through
    assert r.operation == "ask_question"


def test_execute_skips_failed_upstream(monkeypatch: pytest.MonkeyPatch, fake_llm: MakeLLM) -> None:
    """A failed dependency is NOT fed downstream (only successful outputs flow forward)."""
    monkeypatch.setattr(
        "orchestrator.executor.call_operation", _stub_call(ok=False, error="retry: boom")
    )
    # both calls fail, so each subtask returns after selection (no relevance check): 2 LLM calls
    client = fake_llm([_SELECT, _SELECT])
    plan = _plan(_sub_id("t1"), _sub_id("t2", depends_on=("t1",)))
    result = _run(plan, client)

    assert result.results[0].status == "error"
    messages = [r.messages[0]["content"] for r in client.requests]
    assert "UPSTREAM" not in messages[1]  # t2's selection has no failed upstream


# --- web safety net: fall back to the web when the CHOSEN app can't ground it ------------------


def _web_ok(monkeypatch: pytest.MonkeyPatch, answer: str = "Web answer.") -> None:
    monkeypatch.setattr("orchestrator.executor.resolve_search_key", lambda: "k")

    async def _search(_query: str, **_kw: Any) -> WebResult:
        return WebResult(answer=answer, citations=("http://w",))

    monkeypatch.setattr("orchestrator.executor.search_web", _search)


def test_web_safety_net_on_skip(monkeypatch: pytest.MonkeyPatch, fake_llm: MakeLLM) -> None:
    _web_ok(monkeypatch, "Web answer for p-value.")
    # _STATS_SUB with a blank module -> primary skips -> safety net -> web answers
    r = _run(_plan(_STATS_SUB), fake_llm([_STATS_SELECT_BLANK])).results[0]
    assert r.status == "ok"
    assert r.app_name == "Web Search (fallback)"  # transparently attributed to the web
    assert r.output == {"answer": "Web answer for p-value.", "citations": ["http://w"]}
    assert r.source == "http://w"


def test_web_safety_net_sets_disclosure_note(
    monkeypatch: pytest.MonkeyPatch, fake_llm: MakeLLM
) -> None:
    _web_ok(monkeypatch)
    r = _run(_plan(_STATS_SUB), fake_llm([_STATS_SELECT_BLANK])).results[0]
    assert r.status == "ok"
    assert r.note is not None
    assert "Statistics Teacher" in r.note  # names the app that was bypassed
    assert "web search" in r.note.lower()


def test_web_safety_net_on_error(monkeypatch: pytest.MonkeyPatch, fake_llm: MakeLLM) -> None:
    _web_ok(monkeypatch)
    monkeypatch.setattr(
        "orchestrator.executor.call_operation", _stub_call(ok=False, error="retry: boom")
    )
    r = _run(_plan(_sub("arxiv-papers", "ArXiv Paper Guide")), fake_llm([_SELECT])).results[0]
    assert r.status == "ok"
    assert r.app_name == "Web Search (fallback)"


def test_web_safety_net_on_no_match(monkeypatch: pytest.MonkeyPatch, fake_llm: MakeLLM) -> None:
    _web_ok(monkeypatch)
    monkeypatch.setattr("orchestrator.executor.call_operation", _stub_call())
    # call ok, but relevance guard rejects -> no_match -> safety net -> web
    r = _run(_plan(_sub("arxiv-papers", "ArXiv Paper Guide")), fake_llm([_SELECT, _IRRELEVANT]))
    assert r.results[0].status == "ok"
    assert r.results[0].app_name == "Web Search (fallback)"


def test_web_safety_net_keeps_original_failure_when_web_fails(
    monkeypatch: pytest.MonkeyPatch, fake_llm: MakeLLM
) -> None:
    monkeypatch.setattr("orchestrator.executor.resolve_search_key", lambda: "k")

    async def _boom(_query: str, **_kw: Any) -> WebResult:
        raise WebSearchError("down")

    monkeypatch.setattr("orchestrator.executor.search_web", _boom)
    monkeypatch.setattr(
        "orchestrator.executor.call_operation", _stub_call(ok=False, error="retry: boom")
    )
    r = _run(_plan(_sub("arxiv-papers", "ArXiv Paper Guide")), fake_llm([_SELECT])).results[0]
    assert r.status == "error"  # web also failed -> original failure preserved, not masked
    assert "retry: boom" in (r.error or "")
