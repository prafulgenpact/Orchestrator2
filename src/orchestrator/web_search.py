"""Web-search fallback: a grounded answer with citations when no app fits.

The orchestrator's objective is to answer *any* task — when intent recognition finds no
specialized app for a subtask, this fetches a real answer from the web instead of giving up.
It reuses the same Tavily search key the sibling apps already use (glue coding, not a new
service); the ``include_answer`` result is a grounded summary, and the result URLs are the
citations. The HTTP client and key are injected so this is fully testable with no network.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from orchestrator.llm.base import LLMError
from orchestrator.llm.foundry import DEFAULT_FALLBACK_ENV, PROJECT_ENV, _parse_env_file

TAVILY_URL = "https://api.tavily.com/search"
SEARCH_KEY_ENV = "TAVILY_API_KEY"
DEFAULT_TIMEOUT_S = 30.0
DEFAULT_MAX_RESULTS = 5


class WebSearchError(LLMError):
    """A web search could not be completed (config, network, or provider error)."""


@dataclass(frozen=True)
class WebResult:
    """A grounded web answer and the URLs it was drawn from (provenance)."""

    answer: str
    citations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"answer": self.answer, "citations": list(self.citations)}


def resolve_search_key() -> str | None:
    """The Tavily key: process env, then the project ``.env``, then the sibling fallback.

    Mirrors ``foundry.resolve_credentials`` precedence (and honors ``ORCHESTRATOR_FALLBACK_ENV``
    as the sole override) so tests can isolate from any real ``.env``. Returns None when unset —
    the caller degrades to a clean "skipped", never a crash.
    """
    from_env = os.environ.get(SEARCH_KEY_ENV)
    if from_env:
        return from_env
    override = os.environ.get("ORCHESTRATOR_FALLBACK_ENV")
    files = [Path(override)] if override else [PROJECT_ENV, DEFAULT_FALLBACK_ENV]
    for path in files:
        value = _parse_env_file(path).get(SEARCH_KEY_ENV)
        if value:
            return value
    return None


async def search_web(
    query: str,
    *,
    client: httpx.AsyncClient,
    api_key: str,
    max_results: int = DEFAULT_MAX_RESULTS,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> WebResult:
    """Run one Tavily search and return a grounded answer + citation URLs.

    Raises WebSearchError on a transport error, a non-2xx response, or a response with no answer.
    """
    payload = {
        "api_key": api_key,
        "query": query,
        "include_answer": True,
        "max_results": max_results,
        "search_depth": "basic",
    }
    try:
        resp = await client.post(TAVILY_URL, json=payload, timeout=timeout_s)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as exc:
        detail = str(exc) or type(exc).__name__
        raise WebSearchError(f"web search request failed: {detail}") from exc

    answer = data.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        raise WebSearchError("web search returned no answer")
    citations = tuple(
        r["url"]
        for r in data.get("results", [])
        if isinstance(r, dict) and isinstance(r.get("url"), str)
    )
    return WebResult(answer=answer.strip(), citations=citations)
