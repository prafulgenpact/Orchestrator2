"""Unit tests for the web-search fallback (no network; httpx MockTransport)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from orchestrator.web_search import (
    SEARCH_KEY_ENV,
    WebResult,
    WebSearchError,
    resolve_search_key,
    search_web,
)

Handler = Callable[[httpx.Request], httpx.Response]


def _run_search(handler: Handler, **kw: Any) -> WebResult:
    async def go() -> WebResult:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await search_web("q", client=client, api_key="k", **kw)

    return asyncio.run(go())


# --- search_web --------------------------------------------------------------


def test_search_web_success() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        assert "api.tavily.com" in str(req.url)
        body = json.loads(req.content)
        assert body["query"] == "q"
        assert body["include_answer"] is True
        assert body["api_key"] == "k"
        return httpx.Response(
            200,
            json={
                "answer": "  A p-value is a probability.  ",
                "results": [{"url": "http://a"}, "notadict", {"no_url": 1}, {"url": "http://b"}],
            },
        )

    res = _run_search(handler)
    assert res.answer == "A p-value is a probability."  # stripped
    assert res.citations == ("http://a", "http://b")  # non-dicts / url-less entries dropped


def test_search_web_error_status() -> None:
    with pytest.raises(WebSearchError, match="request failed"):
        _run_search(lambda _r: httpx.Response(500, json={"detail": "boom"}))


def test_search_web_transport_error() -> None:
    def handler(_r: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(WebSearchError, match="request failed"):
        _run_search(handler)


def test_search_web_missing_answer() -> None:
    with pytest.raises(WebSearchError, match="no answer"):
        _run_search(lambda _r: httpx.Response(200, json={"results": [{"url": "http://a"}]}))


def test_search_web_blank_answer() -> None:
    with pytest.raises(WebSearchError, match="no answer"):
        _run_search(lambda _r: httpx.Response(200, json={"answer": "   ", "results": []}))


def test_web_result_to_dict() -> None:
    assert WebResult("a", ("u1", "u2")).to_dict() == {"answer": "a", "citations": ["u1", "u2"]}


# --- resolve_search_key ------------------------------------------------------


def test_resolve_search_key_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SEARCH_KEY_ENV, "env-key")
    assert resolve_search_key() == "env-key"


def test_resolve_search_key_from_project_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(SEARCH_KEY_ENV, raising=False)
    monkeypatch.delenv("ORCHESTRATOR_FALLBACK_ENV", raising=False)
    proj = tmp_path / "p.env"
    proj.write_text(f"{SEARCH_KEY_ENV}=proj-key\n")
    monkeypatch.setattr("orchestrator.web_search.PROJECT_ENV", proj)
    monkeypatch.setattr("orchestrator.web_search.DEFAULT_FALLBACK_ENV", tmp_path / "absent.env")
    assert resolve_search_key() == "proj-key"


def test_resolve_search_key_none(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv(SEARCH_KEY_ENV, raising=False)
    monkeypatch.delenv("ORCHESTRATOR_FALLBACK_ENV", raising=False)
    monkeypatch.setattr("orchestrator.web_search.PROJECT_ENV", tmp_path / "a.env")
    monkeypatch.setattr("orchestrator.web_search.DEFAULT_FALLBACK_ENV", tmp_path / "b.env")
    assert resolve_search_key() is None


def test_resolve_search_key_override_ignores_project(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(SEARCH_KEY_ENV, raising=False)
    override = tmp_path / "ov.env"
    override.write_text(f"{SEARCH_KEY_ENV}=ov-key\n")
    monkeypatch.setenv("ORCHESTRATOR_FALLBACK_ENV", str(override))
    monkeypatch.setattr("orchestrator.web_search.PROJECT_ENV", tmp_path / "proj.env")  # ignored
    assert resolve_search_key() == "ov-key"
