"""Record/replay layer for deterministic, network-free LLM behavior.

``request_hash`` gives a stable id for an LLMRequest (canonical JSON -> sha256).
RecordingClient wraps a real client and writes each (request, response) to a
fixture file. ReplayClient reads those fixtures back, so unit tests, e2e, and CI
reproduce real model behavior with no network and no API key. Fixtures store only
the request and the response text — never headers or credentials — so they pass the
secret scanner and are safe to commit.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from orchestrator.llm.base import LLMClient, LLMError, LLMRequest

DEFAULT_FIXTURE_DIR = Path(__file__).resolve().parents[3] / "tests" / "e2e" / "fixtures"


class MissingFixtureError(LLMError):
    """No recorded fixture matches this request (record it with AGENT_LLM_MODE=record)."""


def request_hash(request: LLMRequest) -> str:
    """Stable 16-hex-char id for a request; identical requests hash identically."""
    payload = json.dumps(request.to_dict(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _fixture_dir(override: Path | None) -> Path:
    if override is not None:
        return override
    env = os.environ.get("AGENT_LLM_FIXTURES")
    return Path(env) if env else DEFAULT_FIXTURE_DIR


class ReplayClient:
    """Serves recorded responses; raises MissingFixtureError on a cache miss."""

    def __init__(self, fixture_dir: Path | None = None) -> None:
        self._dir = _fixture_dir(fixture_dir)

    def drain_usage(self) -> list[dict[str, object]]:
        """Replayed responses carry no real token counts, so a replay run reports zero usage."""
        return []

    def complete(self, request: LLMRequest) -> str:
        key = request_hash(request)
        path = self._dir / f"{key}.json"
        if not path.exists():
            raise MissingFixtureError(
                f"no fixture {key}.json in {self._dir} — " f"record it with AGENT_LLM_MODE=record"
            )
        data = json.loads(path.read_text())
        return str(data["response_text"])


class RecordingClient:
    """Wraps a real client and records each (request, response) as a fixture."""

    def __init__(self, inner: LLMClient, fixture_dir: Path | None = None) -> None:
        self._inner = inner
        self._dir = _fixture_dir(fixture_dir)

    def drain_usage(self) -> list[dict[str, object]]:
        """Delegate to the wrapped real client so recorded runs still report their token usage."""
        drain = getattr(self._inner, "drain_usage", None)
        if not callable(drain):
            return []
        events: list[dict[str, object]] = list(drain())
        return events

    def complete(self, request: LLMRequest) -> str:
        response = self._inner.complete(request)
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"{request_hash(request)}.json"
        payload = {"request": request.to_dict(), "response_text": response}
        path.write_text(json.dumps(payload, indent=2) + "\n")
        return response
