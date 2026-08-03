"""Unit tests for the preflight doctor (health probing is injected; no network)."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from orchestrator import doctor
from orchestrator.doctor import AppDiag, diagnose, render_doctor
from orchestrator.registry import AppEntry, load_registry

REG = load_registry()


def _dummy_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(lambda _r: httpx.Response(200)))


def test_diagnose_marks_down_apps_with_their_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    # arxiv-papers is "down"; everything else is "up".
    async def fake_health(app: AppEntry, _client: httpx.AsyncClient) -> bool:
        return app.id != "arxiv-papers"

    monkeypatch.setattr(doctor, "read_startup_error", lambda _app_id: "Connect call failed (:5432)")

    async def go() -> list[AppDiag]:
        async with _dummy_client() as c:
            return await diagnose(REG, c, health=fake_health)

    diags = asyncio.run(go())
    by_id = {d.app_id: d for d in diags}
    assert "web-search" not in by_id  # the fallback app is not probed
    arxiv = by_id["arxiv-papers"]
    assert arxiv.healthy is False and arxiv.reason == "Connect call failed (:5432)"
    assert all(d.healthy for d in diags if d.app_id != "arxiv-papers")


def test_diagnose_down_without_log_says_not_running(monkeypatch: pytest.MonkeyPatch) -> None:
    async def all_down(_app: AppEntry, _client: httpx.AsyncClient) -> bool:
        return False

    monkeypatch.setattr(doctor, "read_startup_error", lambda _app_id: None)

    async def go() -> list[AppDiag]:
        async with _dummy_client() as c:
            return await diagnose(REG, c, health=all_down)

    diags = asyncio.run(go())
    assert diags and all(d.reason == "not running (no startup log)" for d in diags)


def test_render_doctor_lists_status_and_reasons() -> None:
    diags = [
        AppDiag("arxiv-papers", "ArXiv Paper Guide", 8002, False, "Connect call failed (:5432)"),
        AppDiag("teach-me", "Teach Me", 8008, True, None),
    ]
    out = render_doctor(diags)
    assert "1/2 up" in out
    assert "DOWN" in out and "UP" in out
    assert "ArXiv Paper Guide" in out
    assert "Connect call failed (:5432)" in out  # the reason is shown under the down app
    assert ":8002" in out
