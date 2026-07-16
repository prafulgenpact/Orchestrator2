"""Anthropic Foundry client — the real LLM backend.

Credentials resolve from the environment first, then from a sibling app's ``.env``
so this project shares the same Foundry setup as the other apps. The model used for a
request is resolved separately (``resolve_model``) and independently of credentials,
so replay reproduces the same request whether or not a live ``.env`` is present. The
anthropic SDK is imported lazily and dynamically inside ``complete`` so replay-mode
runs — unit tests, e2e, CI — need neither the package nor a key.
"""

from __future__ import annotations

import importlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from orchestrator.llm.base import LLMError, LLMRequest

DEFAULT_MODEL = "claude-opus-4-6"
# The orchestrator's own .env at the repo root — the first file consulted after the process
# environment, so `python -m orchestrator --execute ...` works with no exports (gitignored).
PROJECT_ENV = Path(__file__).resolve().parents[3] / ".env"
# Sibling app whose backend/.env carries the shared Foundry credentials — the last-resort fallback
# so this project shares the other apps' setup even without a local .env. Overridable via
# ORCHESTRATOR_FALLBACK_ENV (tests always point this at a controlled file).
DEFAULT_FALLBACK_ENV = Path(__file__).resolve().parents[5] / "Blogs Playground" / "backend" / ".env"


@dataclass(frozen=True)
class FoundryCredentials:
    """The endpoint credentials for a live Foundry call."""

    api_key: str
    base_url: str


DEFAULT_LLM_TIMEOUT_S = 180.0


def resolve_model(override: str | None = None) -> str:
    """Model for a request: explicit override > ORCHESTRATOR_MODEL > pinned default.

    Deliberately independent of credentials so record and replay produce the same
    request hash regardless of whether a live .env is present.
    """
    return override or os.environ.get("ORCHESTRATOR_MODEL") or DEFAULT_MODEL


def resolve_llm_timeout() -> float:
    """Hard per-request wall-clock timeout (seconds) for a live LLM call — the AC-2 anti-hang bound.

    A stalled Foundry request fails after this long (raising, then handled cleanly) instead of
    hanging the whole run: the SDK's own default is ~10 min per attempt, which — across retries —
    reads as a hang. Override with ``ORCHESTRATOR_LLM_TIMEOUT_S``; a blank / non-numeric / non-
    positive value falls back to the default. Independent of model/credential resolution so the
    record/replay request hash is unaffected.
    """
    raw = os.environ.get("ORCHESTRATOR_LLM_TIMEOUT_S")
    if raw is None:
        return DEFAULT_LLM_TIMEOUT_S
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_LLM_TIMEOUT_S
    return value if value > 0 else DEFAULT_LLM_TIMEOUT_S


def _parse_env_file(path: Path) -> dict[str, str]:
    """Minimal KEY=VALUE .env parser (stdlib only; no python-dotenv dependency)."""
    values: dict[str, str] = {}
    try:
        text = path.read_text()
    except OSError:
        return values
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def resolve_credentials() -> FoundryCredentials:
    """Resolve Foundry endpoint credentials.

    Precedence, highest first: the process environment, then the project-local ``.env`` (repo
    root), then the shared sibling-app ``.env`` (``DEFAULT_FALLBACK_ENV``). Setting
    ``ORCHESTRATOR_FALLBACK_ENV`` overrides the file chain entirely — that one file becomes the
    sole fallback, which is how the tests isolate from any real ``.env`` on disk.

    Raises LLMError if the API key or base URL cannot be found.
    """
    override = os.environ.get("ORCHESTRATOR_FALLBACK_ENV")
    fallback_files = [Path(override)] if override else [PROJECT_ENV, DEFAULT_FALLBACK_ENV]

    # Merge so an earlier-listed file wins: load lowest-priority first, let higher ones overwrite.
    merged: dict[str, str] = {}
    for path in reversed(fallback_files):
        merged.update(_parse_env_file(path))

    def pick(key: str) -> str | None:
        return os.environ.get(key) or merged.get(key)

    api_key = pick("ANTHROPIC_FOUNDRY_API_KEY")
    base_url = pick("ANTHROPIC_FOUNDRY_BASE_URL")
    if not api_key or not base_url:
        raise LLMError(
            "missing Foundry credentials: set ANTHROPIC_FOUNDRY_API_KEY and "
            "ANTHROPIC_FOUNDRY_BASE_URL (or point ORCHESTRATOR_FALLBACK_ENV at a .env)"
        )
    return FoundryCredentials(api_key=api_key, base_url=base_url)


def _extract_text(message: Any, *, expect_tool: bool) -> str:
    """Turn a Foundry message into the response string the orchestrator consumes.

    For a tool-use request (``expect_tool``), return the chosen tool call's input as canonical
    JSON — it came from the SDK's *structured* tool input, so it is ALWAYS valid JSON even when
    an argument embeds a large multi-line code block (the fragility that used to truncate the
    hand-written JSON and drop the run to a web fallback). A ``max_tokens`` truncation is
    surfaced as a clear LLMError so a cut-off response never masquerades as a complete one.

    Kept a pure function (no network) so it is fully unit-tested; ``complete`` — the only
    network line — stays excluded from coverage.
    """
    if expect_tool:
        if getattr(message, "stop_reason", None) == "max_tokens":
            raise LLMError(
                "selection response was truncated (hit max_tokens) before completing — "
                "the chosen argument was too large to return in full"
            )
        for block in message.content:
            if getattr(block, "type", None) == "tool_use":
                return json.dumps(block.input)
        raise LLMError("expected a tool_use block in the Foundry response, found none")
    texts = [block.text for block in message.content if getattr(block, "type", None) == "text"]
    if not texts:
        raise LLMError("Foundry response contained no text content")
    return "".join(texts)


class FoundryClient:
    """Calls Anthropic Foundry. Construction is cheap; the SDK loads on first call."""

    def __init__(self, credentials: FoundryCredentials) -> None:
        self._creds = credentials

    def complete(self, request: LLMRequest) -> str:  # pragma: no cover - network path
        try:
            anthropic: Any = importlib.import_module("anthropic")
        except ImportError as exc:
            raise LLMError("the 'anthropic' package is required for live LLM calls") from exc
        client = anthropic.AnthropicFoundry(
            api_key=self._creds.api_key,
            base_url=self._creds.base_url,
            max_retries=2,
            timeout=resolve_llm_timeout(),  # hard per-request bound so a stall never hangs the run
        )
        kwargs: dict[str, Any] = {
            "model": request.model,
            "max_tokens": request.max_tokens,
            "system": request.system,
            "messages": [dict(entry) for entry in request.messages],
        }
        if request.tools:
            kwargs["tools"] = [dict(tool) for tool in request.tools]
            if request.tool_choice is not None:
                kwargs["tool_choice"] = dict(request.tool_choice)
        message = client.messages.create(**kwargs)
        return _extract_text(message, expect_tool=bool(request.tools))
