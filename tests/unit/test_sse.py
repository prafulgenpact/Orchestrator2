"""Unit tests for the SSE (text/event-stream) transport — hermetic via httpx.MockTransport."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import httpx
import pytest

from orchestrator.app_caller import CallResult, _sse_text, call_operation
from orchestrator.registry import load_registry

Handler = Callable[[httpx.Request], httpx.Response]
REG = load_registry()


@pytest.fixture(autouse=True)
def _autostart_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _off(*_a: object, **_kw: object) -> bool:
        return False

    monkeypatch.setattr("orchestrator.app_caller.ensure_started", _off)


def _client(handler: Handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_sse_text_handles_both_dialects_and_events() -> None:
    assert _sse_text({"token": "a"}) == "a"  # build/suggest dialect
    assert _sse_text({"type": "token", "content": "b"}) == "b"  # chat dialect
    assert _sse_text({"delta": "c"}) == "c"
    assert _sse_text({"type": "sources", "items": [1]}) is None  # structured event, not text
    assert _sse_text({"type": "done"}) is None


def _sse_op() -> tuple[object, object]:
    app = REG.get("github-learnings")
    assert app is not None
    op = app.operation("post_build_suggest")
    assert op is not None and op.stream == "sse"
    return app, op


def _run(handler: Handler) -> CallResult:
    app, op = _sse_op()

    async def go() -> CallResult:
        async with _client(handler) as c:
            return await call_operation(app, op, {"description": "a url shortener"}, client=c)

    return asyncio.run(go())


def test_sse_call_assembles_tokens_and_events() -> None:
    body = (
        b'data: {"token": "Hello"}\n\n'
        b'data: {"token": " world"}\n\n'
        b'data: {"type": "sources", "items": [1, 2]}\n\n'
        b"data: [DONE]\n\n"
        b'data: {"token": "IGNORED after done"}\n\n'
    )

    def handler(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if p == "/api/apps":
            return httpx.Response(
                200, json={"apps": [{"id": "github-learnings", "backend_port": 8009}]}
            )
        if "health" in p:
            return httpx.Response(200, json={"status": "ok"})
        if p == "/api/build/suggest":
            return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})
        return httpx.Response(404)

    res = _run(handler)
    assert res.ok is True
    assert res.data["text"] == "Hello world"  # stops at [DONE]; tokens concatenated
    assert res.data["events"] == [{"type": "sources", "items": [1, 2]}]


def test_sse_call_error_status_is_clean_failure() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if p == "/api/apps":
            return httpx.Response(
                200, json={"apps": [{"id": "github-learnings", "backend_port": 8009}]}
            )
        if "health" in p:
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(500, text="boom")  # the streamed endpoint errors

    res = _run(handler)
    assert res.ok is False
    assert res.error  # a clean error, never a raise
