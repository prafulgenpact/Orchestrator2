"""The LLM boundary: a minimal protocol so the planner never touches a vendor SDK.

Everything the orchestrator needs from a language model is
``complete(request) -> str``. Real calls go through FoundryClient; tests and CI go
through ReplayClient (recorded responses). Keeping this surface tiny is what lets the
planner logic be fully unit-tested with no network. LLMRequest is deterministic —
the same request serializes identically, which is what makes record/replay stable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class LLMError(RuntimeError):
    """An LLM call could not be completed (config, network, or provider error)."""


@dataclass(frozen=True)
class LLMRequest:
    """One completion request. Message dicts carry 'role' and 'content' strings."""

    model: str
    system: str
    messages: tuple[dict[str, str], ...]
    max_tokens: int = 8000

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "system": self.system,
            "messages": [dict(message) for message in self.messages],
            "max_tokens": self.max_tokens,
        }


class LLMClient(Protocol):
    """Structural type for anything that can answer a completion request."""

    def complete(self, request: LLMRequest) -> str:  # pragma: no cover
        """Return the model's text response, or raise LLMError."""
        ...
