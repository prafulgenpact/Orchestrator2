"""Unit tests for the live-kernel WebSocket transport — hermetic via a scripted fake socket."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest

from orchestrator.app_caller import CallResult, call_operation
from orchestrator.registry import load_registry

REG = load_registry()


@pytest.fixture(autouse=True)
def _autostart_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _off(*_a: object, **_kw: object) -> bool:
        return False

    monkeypatch.setattr("orchestrator.app_caller.ensure_started", _off)


class _FakeWS:
    """A stand-in for a websockets connection: replays scripted frames, swallows the send."""

    def __init__(self, frames: list[dict[str, Any]]) -> None:
        self._frames = [json.dumps(f) for f in frames]
        self.sent: str | None = None

    async def send(self, message: str) -> None:
        self.sent = message

    async def recv(self) -> str:
        return self._frames.pop(0)

    async def __aenter__(self) -> _FakeWS:
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False


def _http_client() -> httpx.AsyncClient:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/api/apps":
            return httpx.Response(
                200, json={"apps": [{"id": "coding-playground", "backend_port": 8003}]}
            )
        return httpx.Response(200, json={"status": "ok"})  # health

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _run(monkeypatch: pytest.MonkeyPatch, frames: list[dict[str, Any]]) -> CallResult:
    app = REG.get("coding-playground")
    assert app is not None
    op = app.operation("run_code")
    assert op is not None and op.stream == "ws"
    monkeypatch.setattr(
        "orchestrator.app_caller.websockets.connect", lambda *_a, **_kw: _FakeWS(frames)
    )

    async def go() -> CallResult:
        async with _http_client() as c:
            return await call_operation(app, op, {"code": "print(4)"}, client=c)

    return asyncio.run(go())


def test_ws_run_assembles_text_and_images(monkeypatch: pytest.MonkeyPatch) -> None:
    frames = [
        {"type": "status", "kernel_status": "busy"},
        {"type": "stream", "content": {"type": "text", "content": "4\n"}},
        {"type": "execute_result", "content": {"type": "text", "content": "42"}},
        {"type": "display_data", "content": {"type": "image", "content": "BASE64PNG"}},
        {"type": "execute_reply", "content": {"type": "text", "content": ""}},
        {"type": "status", "kernel_status": "idle"},  # never read: we stop at execute_reply
    ]
    res = _run(monkeypatch, frames)
    assert res.ok is True
    assert res.data["text"] == "4\n42"
    assert res.data["images"] == ["BASE64PNG"]
    assert "error" not in res.data


def test_ws_run_reports_error(monkeypatch: pytest.MonkeyPatch) -> None:
    frames = [
        {"type": "error", "content": {"type": "text", "content": "Traceback: NameError"}},
        {"type": "execute_reply", "content": {}},
    ]
    res = _run(monkeypatch, frames)
    assert res.ok is True  # the transport succeeded; the code error is reported in the result
    assert "NameError" in res.data["error"]
