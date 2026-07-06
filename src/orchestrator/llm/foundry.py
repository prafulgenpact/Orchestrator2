"""Anthropic Foundry client — the real LLM backend.

Credentials resolve from the environment first, then from a sibling app's ``.env``
so this project shares the same Foundry setup as the other apps. The anthropic SDK
is imported lazily (and dynamically) inside ``complete`` so replay-mode runs — unit
tests, e2e, CI — need neither the package nor a key, and so type-checking does not
depend on the SDK's internals.
"""

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from orchestrator.llm.base import LLMError, LLMRequest

DEFAULT_MODEL = "claude-opus-4-6"
# Sibling app whose backend/.env carries the shared Foundry credentials. Overridable
# via ORCHESTRATOR_FALLBACK_ENV (tests always point this at a controlled file).
DEFAULT_FALLBACK_ENV = Path(__file__).resolve().parents[5] / "Blogs Playground" / "backend" / ".env"


@dataclass(frozen=True)
class FoundryCredentials:
    """Everything needed to make a live Foundry call."""

    api_key: str
    base_url: str
    model: str


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


def resolve_credentials(model_override: str | None = None) -> FoundryCredentials:
    """Resolve Foundry credentials: process env wins, then the fallback .env file.

    Model precedence: explicit override > ORCHESTRATOR_MODEL > ANTHROPIC_MODEL >
    the pinned default. Raises LLMError if the API key or base URL cannot be found.
    """
    fallback_override = os.environ.get("ORCHESTRATOR_FALLBACK_ENV")
    fallback_path = Path(fallback_override) if fallback_override else DEFAULT_FALLBACK_ENV
    fallback = _parse_env_file(fallback_path)

    def pick(key: str) -> str | None:
        return os.environ.get(key) or fallback.get(key)

    api_key = pick("ANTHROPIC_FOUNDRY_API_KEY")
    base_url = pick("ANTHROPIC_FOUNDRY_BASE_URL")
    if not api_key or not base_url:
        raise LLMError(
            "missing Foundry credentials: set ANTHROPIC_FOUNDRY_API_KEY and "
            "ANTHROPIC_FOUNDRY_BASE_URL (or point ORCHESTRATOR_FALLBACK_ENV at a .env)"
        )
    model = (
        model_override
        or os.environ.get("ORCHESTRATOR_MODEL")
        or pick("ANTHROPIC_MODEL")
        or DEFAULT_MODEL
    )
    return FoundryCredentials(api_key=api_key, base_url=base_url, model=model)


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
        )
        message = client.messages.create(
            model=request.model,
            max_tokens=request.max_tokens,
            system=request.system,
            messages=[dict(entry) for entry in request.messages],
        )
        texts = [block.text for block in message.content if getattr(block, "type", None) == "text"]
        if not texts:
            raise LLMError("Foundry response contained no text content")
        return "".join(texts)
