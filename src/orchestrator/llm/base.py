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
    """One completion request. Message dicts carry 'role' and 'content' strings.

    ``tools`` + ``tool_choice`` are optional forced-structured-output controls (Anthropic
    tool-use). When set, the client must return the chosen tool call's input as JSON — this
    is what makes a code-heavy selection response always valid JSON. They are serialized by
    ``to_dict`` ONLY when set, so a request without them hashes identically to before and no
    recorded fixtures need re-recording.
    """

    model: str
    system: str
    messages: tuple[dict[str, str], ...]
    max_tokens: int = 8000
    tools: tuple[dict[str, Any], ...] = ()
    tool_choice: dict[str, Any] | None = None
    # Default 0.0 so every call is as deterministic as the model allows — the same task decomposes,
    # selects, and is judged the same way run-to-run, instead of the SDK default 1.0 (a per-run
    # lottery). Deliberately NOT in to_dict below: temperature does not change a *replayed*
    # response, so keeping it out of the request hash means recorded fixtures still resolve.
    temperature: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "model": self.model,
            "system": self.system,
            "messages": [dict(message) for message in self.messages],
            "max_tokens": self.max_tokens,
        }
        if self.tools:
            data["tools"] = [dict(tool) for tool in self.tools]
        if self.tool_choice is not None:
            data["tool_choice"] = dict(self.tool_choice)
        return data


class LLMClient(Protocol):
    """Structural type for anything that can answer a completion request."""

    def complete(self, request: LLMRequest) -> str:  # pragma: no cover
        """Return the model's text response, or raise LLMError."""
        ...
