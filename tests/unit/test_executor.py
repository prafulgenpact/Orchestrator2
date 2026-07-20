"""Unit tests for the executor — full plan run with the HTTP call stubbed (no network)."""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable, Sequence
from typing import Any

import httpx
import pytest
from conftest import FakeLLM

from orchestrator.app_caller import AppEndpoints, CallResult
from orchestrator.executor import _ASYNC_MAX_SILENT_POLLS, _dig, _run_async, execute_plan
from orchestrator.llm.base import LLMError
from orchestrator.models import AppSelection, Plan, PlanResult, Subtask
from orchestrator.registry import AppEntry, AppOperation, AsyncSpec, load_registry
from orchestrator.resilience import CircuitBreaker
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
_RELEVANT = '{"verdict": "PASS", "reason": "on topic"}'
_IRRELEVANT = '{"verdict": "FAIL", "reason": "off-topic keyword match"}'


class _ConcurrencyProbe:
    """Thread-safe fake LLM that records the peak number of concurrent in-flight calls.

    Selection requests (forced tool-use -> ``request.tools`` set) hold for a short window so
    genuinely-overlapping subtasks are observable, then return a fixed valid selection; relevance
    requests return PASS immediately. It has no shared response queue, so it is safe to call from
    several ``asyncio.to_thread`` worker threads at once (unlike the sequential ``FakeLLM``)."""

    def __init__(self, hold_s: float = 0.05) -> None:
        self._hold = hold_s
        self._lock = threading.Lock()
        self.current = 0
        self.peak = 0

    def complete(self, request: Any) -> str:
        if not request.tools:  # relevance guard — not part of the concurrency measurement
            return _RELEVANT
        with self._lock:
            self.current += 1
            self.peak = max(self.peak, self.current)
        time.sleep(self._hold)  # overlap window: serial callers can never raise peak above 1
        with self._lock:
            self.current -= 1
        return _SELECT


def _independent_plan(n: int) -> Plan:
    """A plan of n subtasks with no dependencies — compute_waves puts them all in one wave."""
    subs = tuple(
        Subtask(
            f"t{i}",
            f"step {i}",
            f"work {i}",
            (),
            AppSelection("arxiv-papers", "ArXiv Paper Guide", "because", 0.9, False),
        )
        for i in range(n)
    )
    return _plan(*subs)


def _coding_sub(title: str = "plot cylinders") -> Subtask:
    app = AppSelection("coding-playground", "Coding Playground", "because", 0.9, False)
    return Subtask("t1", title, "plot the distribution of cylinders", (), app)


def test_chart_op_attaches_artifact(monkeypatch: pytest.MonkeyPatch, fake_llm: MakeLLM) -> None:
    box = {"type": "box", "column": "cylinders", "q1": 4, "median": 4, "q3": 8}

    async def _call(app: Any, op: Any, _args: Any, **_kw: Any) -> CallResult:
        return CallResult(app.id, op.name, "http://x", True, 200, box, None, 0.01)

    monkeypatch.setattr("orchestrator.executor.call_operation", _call)
    sel = '{"operation": "eda_distribution", "arguments": {"dataset_id": "auto-mpg", "column": "cylinders", "plot_type": "box"}}'  # noqa: E501
    r = _run(_plan(_coding_sub()), fake_llm([sel, _RELEVANT])).results[0]
    assert r.status == "ok"
    assert len(r.artifacts) == 1
    assert r.artifacts[0].kind == "chart" and r.artifacts[0].spec["type"] == "box"


def test_non_chart_op_has_no_artifact(monkeypatch: pytest.MonkeyPatch, fake_llm: MakeLLM) -> None:
    payload = {"column": "fare", "outlier_count": 3}

    async def _call(app: Any, op: Any, _args: Any, **_kw: Any) -> CallResult:
        return CallResult(app.id, op.name, "http://x", True, 200, payload, None, 0.01)

    monkeypatch.setattr("orchestrator.executor.call_operation", _call)
    sel = '{"operation": "eda_outliers", "arguments": {"dataset_id": "titanic", "column": "fare"}}'
    r = _run(_plan(_coding_sub("find outliers")), fake_llm([sel, _RELEVANT])).results[0]
    assert r.status == "ok"
    assert r.artifacts == ()


def test_viz_op_attaches_chart(monkeypatch: pytest.MonkeyPatch, fake_llm: MakeLLM) -> None:
    roc = {
        "curves": [{"class": "positive", "fpr": [0.0, 1.0], "tpr": [0.0, 1.0]}],
        "auc_scores": {},
    }

    async def _call(app: Any, op: Any, _args: Any, **_kw: Any) -> CallResult:
        return CallResult(app.id, op.name, "http://x", True, 200, roc, None, 0.01)

    monkeypatch.setattr("orchestrator.executor.call_operation", _call)
    sel = '{"operation": "post_viz_roc", "arguments": {"dataset_id": "titanic", "model_id": "logistic_regression", "target_col": "Survived"}}'  # noqa: E501
    r = _run(_plan(_coding_sub("show the ROC curve")), fake_llm([sel, _RELEVANT])).results[0]
    assert r.status == "ok"
    assert len(r.artifacts) == 1 and r.artifacts[0].kind == "chart"
    assert "curves" in r.artifacts[0].spec


def test_run_code_images_attach_image_artifacts(
    monkeypatch: pytest.MonkeyPatch, fake_llm: MakeLLM
) -> None:
    payload = {"text": "done", "images": ["QUJD", "REVG"]}  # two base64 PNGs

    async def _call(app: Any, op: Any, _args: Any, **_kw: Any) -> CallResult:
        return CallResult(app.id, op.name, "ws://x", True, 200, payload, None, 0.01)

    monkeypatch.setattr("orchestrator.executor.call_operation", _call)
    sel = '{"operation": "run_code", "arguments": {"code": "import matplotlib; ..."}}'
    r = _run(_plan(_coding_sub("plot something custom")), fake_llm([sel, _RELEVANT])).results[0]
    assert r.status == "ok"
    assert [a.kind for a in r.artifacts] == ["image", "image"]
    assert r.artifacts[0].spec["png_base64"] == "QUJD"


def test_wave_runs_subtasks_concurrently(monkeypatch: pytest.MonkeyPatch) -> None:
    # Independent subtasks in a wave must run in parallel (the plan already labels them
    # "(parallel)"). With the default cap (5) and a wave of 3, all three selections should be
    # in flight at once. Serial execution would cap peak at 1.
    monkeypatch.delenv("ORCHESTRATOR_MAX_CONCURRENCY", raising=False)
    monkeypatch.setattr("orchestrator.executor.call_operation", _stub_call())
    probe = _ConcurrencyProbe()
    result = _run(_independent_plan(3), probe)  # type: ignore[arg-type]
    assert [r.status for r in result.results] == ["ok", "ok", "ok"]
    assert probe.peak == 3


def test_wave_concurrency_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    # ORCHESTRATOR_MAX_CONCURRENCY caps how many subtasks run at once: with a cap of 2 and a wave
    # of 4, peak in-flight must reach 2 (concurrency works) but never exceed it (the cap holds).
    monkeypatch.setenv("ORCHESTRATOR_MAX_CONCURRENCY", "2")
    monkeypatch.setattr("orchestrator.executor.call_operation", _stub_call())
    probe = _ConcurrencyProbe()
    result = _run(_independent_plan(4), probe)  # type: ignore[arg-type]
    assert [r.status for r in result.results] == ["ok", "ok", "ok", "ok"]
    assert probe.peak == 2


def test_execute_emits_progress(monkeypatch: pytest.MonkeyPatch, fake_llm: MakeLLM) -> None:
    # execute_plan reports a start line and a finish line (with status) per subtask via the
    # progress callback, so the user is never left staring at silence.
    monkeypatch.setattr("orchestrator.executor.call_operation", _stub_call())
    events: list[str] = []
    client = fake_llm([_SELECT, _RELEVANT])

    async def go() -> PlanResult:
        async with _dummy_client() as http:
            return await execute_plan(
                _plan(_sub("arxiv-papers", "ArXiv Paper Guide")),
                REG,
                llm_client=client,
                http_client=http,
                model="m",
                progress=events.append,
            )

    asyncio.run(go())
    assert any(e.startswith("-> Find papers") for e in events)  # start line
    assert any(e.startswith("[ok] Find papers") for e in events)  # finish line, ok status


def test_async_poll_emits_heartbeat(monkeypatch: pytest.MonkeyPatch) -> None:
    # A genuinely slow start-then-poll job that keeps responding emits a heartbeat, so slow never
    # reads as hung.
    running = [_cr({"status": "running"}) for _ in range(7)]
    monkeypatch.setattr(
        "orchestrator.executor.call_operation",
        _fake_calls(
            _cr({"run_id": "r1"}), *running, _cr({"status": "done", "result": {"content": "x"}})
        ),
    )
    events: list[str] = []
    app, op = _blogs_gen()

    async def go() -> CallResult:
        async with _dummy_client() as http:
            return await _run_async(
                app,
                op,
                {"topic": "x"},
                http_client=http,
                breaker=CircuitBreaker(),
                sleep=_no_sleep,
                progress=events.append,
            )

    res = asyncio.run(go())
    assert res.ok is True
    assert any("still working" in e for e in events)


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


def test_selection_llm_error_becomes_clean_error(
    monkeypatch: pytest.MonkeyPatch, fake_llm: MakeLLM
) -> None:
    # A truncation (or any LLM-layer failure) during operation selection must NOT crash the run:
    # it surfaces as a clean subtask error (which then feeds the web safety net). Web is offline
    # here (autouse), so the clean error surfaces directly.
    def _raise(*_a: Any, **_kw: Any) -> Any:
        raise LLMError("selection response was truncated (hit max_tokens)")

    monkeypatch.setattr("orchestrator.executor.select_operation", _raise)
    r = _run(_plan(_sub("arxiv-papers", "ArXiv Paper Guide")), fake_llm([])).results[0]
    assert r.status == "error"
    assert "truncated" in (r.error or "")


def test_selection_llm_error_triggers_disclosed_web_fallback(
    monkeypatch: pytest.MonkeyPatch, fake_llm: MakeLLM
) -> None:
    # Same failure, but with the web enabled: the safety net answers and discloses the bypass.
    _web_ok(monkeypatch, "Web answer.")

    def _raise(*_a: Any, **_kw: Any) -> Any:
        raise LLMError("selection response was truncated (hit max_tokens)")

    monkeypatch.setattr("orchestrator.executor.select_operation", _raise)
    r = _run(_plan(_sub("arxiv-papers", "ArXiv Paper Guide")), fake_llm([])).results[0]
    assert r.status == "ok"
    assert r.app_name == "Web Search (fallback)"
    assert r.note is not None and "ArXiv Paper Guide" in r.note


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


# --- async-poll: drive a start-then-poll job to completion --------------------


async def _no_sleep(_s: float) -> None:
    return None


def _cr(data: Any, *, ok: bool = True, error: str | None = None) -> CallResult:
    return CallResult("app", "op", "http://x", ok, 200 if ok else None, data, error, 0.1)


def _fake_calls(*results: CallResult) -> Callable[..., Any]:
    seq = list(results)

    async def _call(_app: Any, _op: Any, _args: Any, **_kw: Any) -> CallResult:
        return seq.pop(0)

    return _call


def _blogs_gen() -> tuple[AppEntry, AppOperation]:
    app = REG.get("blogs-playground")
    assert app is not None
    op = app.operation("generate_blog_async")
    assert op is not None
    return app, op


def _do_async(app: AppEntry, op: AppOperation) -> CallResult:
    async def go() -> CallResult:
        async with _dummy_client() as http:
            return await _run_async(
                app, op, {"topic": "x"}, http_client=http, breaker=CircuitBreaker(), sleep=_no_sleep
            )

    return asyncio.run(go())


def test_dig_paths() -> None:
    assert _dig({"a": {"b": 1}}, "a.b") == 1
    assert _dig({"xs": [{"v": 9}]}, "xs.0.v") == 9
    assert _dig({"xs": [1, 2, 3]}, "xs.-1") == 3  # negative index
    assert _dig({"a": 1}, "a.b") is None  # descend into a scalar -> None
    assert _dig({"xs": [1]}, "xs.5") is None  # index out of range
    assert _dig({"xs": [1]}, "xs.k") is None  # non-int segment on a list
    assert _dig({}, "missing") is None


def test_async_runs_to_completion(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "orchestrator.executor.call_operation",
        _fake_calls(
            _cr({"run_id": "r1"}),
            _cr({"status": "running", "result": None}),
            _cr({"status": "done", "result": {"content": "# Blog\ntext"}}),
        ),
    )
    res = _do_async(*_blogs_gen())
    assert res.ok is True
    assert res.data == "# Blog\ntext"  # result.content extracted from the finished run


def test_async_missing_run_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("orchestrator.executor.call_operation", _fake_calls(_cr({"nope": 1})))
    res = _do_async(*_blogs_gen())
    assert res.ok is False
    assert "no 'run_id'" in (res.error or "")


def test_async_failed_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "orchestrator.executor.call_operation",
        _fake_calls(_cr({"run_id": "r1"}), _cr({"status": "failed"})),
    )
    res = _do_async(*_blogs_gen())
    assert res.ok is False
    assert "failed" in (res.error or "")


def test_async_start_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "orchestrator.executor.call_operation", _fake_calls(_cr(None, ok=False, error="down"))
    )
    res = _do_async(*_blogs_gen())
    assert res.ok is False
    assert "down" in (res.error or "")


def test_async_stops_when_app_goes_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    # The app stops answering polls: after _ASYNC_MAX_SILENT_POLLS consecutive failures we declare
    # "no progress" and stop (silence = hung), preserving the underlying error.
    fails = [_cr(None, ok=False, error="retry: boom") for _ in range(_ASYNC_MAX_SILENT_POLLS)]
    monkeypatch.setattr(
        "orchestrator.executor.call_operation", _fake_calls(_cr({"run_id": "r1"}), *fails)
    )
    res = _do_async(*_blogs_gen())
    assert res.ok is False
    assert "stopped responding" in (res.error or "")
    assert "boom" in (res.error or "")


def test_async_tolerates_transient_poll_blip(monkeypatch: pytest.MonkeyPatch) -> None:
    # A single failed poll (a blip) is not a hang: the run recovers and completes.
    monkeypatch.setattr(
        "orchestrator.executor.call_operation",
        _fake_calls(
            _cr({"run_id": "r1"}),
            _cr(None, ok=False, error="retry: transient"),
            _cr({"status": "running"}),
            _cr({"status": "done", "result": {"content": "recovered"}}),
        ),
    )
    res = _do_async(*_blogs_gen())
    assert res.ok is True
    assert res.data == "recovered"


def test_async_slow_but_responsive_completes(monkeypatch: pytest.MonkeyPatch) -> None:
    # A genuinely slow job that keeps answering "running" is NOT cut off — it finishes when done.
    running = [_cr({"status": "running"}) for _ in range(20)]
    monkeypatch.setattr(
        "orchestrator.executor.call_operation",
        _fake_calls(
            _cr({"run_id": "r1"}),
            *running,
            _cr({"status": "done", "result": {"content": "finally"}}),
        ),
    )
    res = _do_async(*_blogs_gen())
    assert res.ok is True
    assert res.data == "finally"


def test_async_poll_op_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("orchestrator.executor.call_operation", _fake_calls(_cr({"run_id": "r1"})))
    spec = AsyncSpec("ghost", "run_id", "run_id", "status", ("done",), (), "result")
    op = AppOperation("start", "d", "POST", "/s", 30, False, "none", poll=spec)
    app = AppEntry("custom", "Custom", "d", (), (), False, port=8099, health="/h", operations=(op,))
    res = _do_async(app, op)
    assert res.ok is False
    assert "not found" in (res.error or "")


def test_async_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("orchestrator.executor._ASYNC_MAX_WAIT_S", 0.05)
    monkeypatch.setattr("orchestrator.executor._ASYNC_POLL_INTERVAL_S", 0.01)
    monkeypatch.setattr(
        "orchestrator.executor.call_operation",
        _fake_calls(_cr({"run_id": "r1"}), *[_cr({"status": "running"}) for _ in range(10)]),
    )
    res = _do_async(*_blogs_gen())
    assert res.ok is False
    assert "did not finish" in (res.error or "")


def test_async_poll_reuses_resolved_endpoint() -> None:
    # Real call_operation over the poll loop (NOT stubbed): with a shared AppEndpoints, the
    # launcher resolve (/api/apps) and health check happen ONCE, not per poll (amplification fix).
    counts = {"apps": 0, "health": 0}
    polls = {"n": 0}
    spec = AsyncSpec("get_run", "run_id", "run_id", "status", ("done",), (), "result")
    start_op = AppOperation("start", "d", "POST", "/api/start", 30, False, "none", poll=spec)
    poll_op = AppOperation("get_run", "d", "GET", "/api/runs/{run_id}", 30, False, "none")
    app = AppEntry(
        "cust",
        "Cust",
        "d",
        (),
        (),
        False,
        port=8099,
        health="/health",
        operations=(start_op, poll_op),
    )

    def handler(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if p == "/api/apps":
            counts["apps"] += 1
            return httpx.Response(200, json={"apps": [{"id": "cust", "backend_port": 8099}]})
        if p == "/health":
            counts["health"] += 1
            return httpx.Response(200, json={"ok": True})
        if p == "/api/start":
            return httpx.Response(200, json={"run_id": "r1"})
        if p.startswith("/api/runs/"):
            polls["n"] += 1
            if polls["n"] >= 4:
                return httpx.Response(200, json={"status": "done", "result": {"content": "done!"}})
            return httpx.Response(200, json={"status": "running"})
        return httpx.Response(404)

    async def go() -> CallResult:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await _run_async(
                app,
                start_op,
                {"topic": "x"},
                http_client=c,
                breaker=CircuitBreaker(),
                sleep=_no_sleep,
                endpoints=AppEndpoints(),
            )

    res = asyncio.run(go())
    assert res.ok is True
    assert res.data == {"content": "done!"}  # spec.result_path="result" -> the whole result object
    assert polls["n"] >= 4  # several polls happened
    assert counts["apps"] == 1  # launcher resolved once, not per poll
    assert counts["health"] == 1  # health checked once, not per poll


def test_execute_routes_async_op(monkeypatch: pytest.MonkeyPatch, fake_llm: MakeLLM) -> None:
    # selecting an async op routes through the poller; the finished content becomes the result
    monkeypatch.setattr(
        "orchestrator.executor.call_operation",
        _fake_calls(_cr({"run_id": "r1"}), _cr({"status": "done", "result": {"content": "blog!"}})),
    )
    sub = Subtask(
        "t1",
        "Write blog",
        "write a blog about x",
        (),
        AppSelection("blogs-playground", "Blogs Playground", "because", 0.9, False),
    )
    client = fake_llm(
        ['{"operation": "generate_blog_async", "arguments": {"topic": "x"}}', _RELEVANT]
    )
    r = _run(_plan(sub), client).results[0]
    assert r.status == "ok"
    assert r.output == "blog!"


def test_async_start_backfills_missing_topic(
    monkeypatch: pytest.MonkeyPatch, fake_llm: MakeLLM
) -> None:
    # The selector omitted 'topic' (the upstream-distraction bug). It is backfilled from the subtask
    # so the blog app actually RUNS on the request instead of 422-ing / skipping to web.
    calls: list[tuple[str, dict[str, Any]]] = []

    async def _capture(_app: Any, op: Any, args: Any, **_kw: Any) -> CallResult:
        calls.append((op.name, dict(args)))
        if op.name == "generate_blog_async":
            return _cr({"run_id": "r1"})
        return _cr({"status": "done", "result": {"content": "blog!"}})

    monkeypatch.setattr("orchestrator.executor.call_operation", _capture)
    sub = Subtask(
        "t1",
        "Draft a blog",
        "write a blog about retrocausality",
        (),
        AppSelection("blogs-playground", "Blogs Playground", "b", 0.9, False),
    )
    client = fake_llm(['{"operation": "generate_blog_async", "arguments": {}}', _RELEVANT])
    r = _run(_plan(sub), client).results[0]
    assert r.status == "ok"
    assert r.output == "blog!"
    start_args = next(a for name, a in calls if name == "generate_blog_async")
    assert start_args.get("topic") == "write a blog about retrocausality"  # backfilled, no fallback


def test_iterate_without_blog_id_skips(monkeypatch: pytest.MonkeyPatch, fake_llm: MakeLLM) -> None:
    # A non-derivable id field (blog_id) is NOT backfilled — the run skips cleanly rather than
    # inventing an id or firing a doomed call.
    async def _boom(*_a: Any, **_kw: Any) -> Any:
        raise AssertionError("must not call the app when a non-derivable id is missing")

    monkeypatch.setattr("orchestrator.executor.call_operation", _boom)
    sub = Subtask(
        "t1",
        "Revise blog",
        "make my blog shorter",
        (),
        AppSelection("blogs-playground", "Blogs Playground", "b", 0.9, False),
    )
    client = fake_llm(['{"operation": "iterate_blog_async", "arguments": {}}'])
    r = _run(_plan(sub), client).results[0]
    assert r.status == "skipped"
    assert "blog_id" in (r.error or "")
