"""LLM client implementations and the record/replay layer.

The planner depends only on the ``LLMClient`` protocol in ``base``; concrete clients
(Foundry for real calls, replay/record for tests) are selected by ``get_client``.
"""

from __future__ import annotations

from pathlib import Path

from orchestrator.llm.base import LLMClient
from orchestrator.llm.foundry import FoundryClient, resolve_credentials
from orchestrator.llm.replay import RecordingClient, ReplayClient

VALID_MODES = ("live", "record", "replay")


def get_client(mode: str, *, fixture_dir: Path | None = None) -> LLMClient:
    """Return the LLM client for a mode.

    - ``replay``: serve recorded fixtures (no network, no key) — used by tests/CI.
    - ``live``: call Foundry directly.
    - ``record``: call Foundry and save the response as a fixture.

    The request model is resolved separately (see ``foundry.resolve_model``).
    """
    if mode == "replay":
        return ReplayClient(fixture_dir)
    if mode == "live":
        return FoundryClient(resolve_credentials())
    if mode == "record":
        return RecordingClient(FoundryClient(resolve_credentials()), fixture_dir)
    raise ValueError(f"unknown LLM mode {mode!r}; valid modes: {', '.join(VALID_MODES)}")
