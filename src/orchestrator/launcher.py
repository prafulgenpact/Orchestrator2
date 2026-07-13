"""Auto-start a sibling app's backend on demand — the user never launches apps by hand.

When the orchestrator needs an app that isn't running, it starts that app's backend itself
(detached, so it outlives the short-lived CLI and is reused by later runs), waits until healthy,
then proceeds. Launch details per app are the recon-verified specs below. The spawner and clock are
injected so this is fully unit-testable with no real processes or network; the real spawn path is
the only thing not exercised in tests (``_spawn_uvicorn``).
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from orchestrator.registry import AppEntry
from orchestrator.resilience import run_with_deadline

# The folder that holds both this repo and the sibling apps (…/Desktop/Desktop).
_SIBLING_ROOT = Path(__file__).resolve().parents[4]
_HEALTH_TIMEOUT_S = 5.0
DEFAULT_START_TIMEOUT_S = 75.0  # cold start incl. model loads; bounded so a bad start never hangs
_POLL_INTERVAL_S = 1.5


@dataclass(frozen=True)
class LaunchSpec:
    """How to launch one app's backend: sibling folder, uvicorn target, and any extra env."""

    folder: str  # backend lives at <_SIBLING_ROOT>/<folder>/backend
    entrypoint: str  # uvicorn app target, e.g. "main:app" or "app.main:app"
    env: dict[str, str] = field(default_factory=dict)

    def backend_dir(self) -> Path:
        return _SIBLING_ROOT / self.folder / "backend"

    def venv_python(self) -> Path:
        return self.backend_dir() / "venv" / "bin" / "python"


# Verified against each live backend (folder name, ASGI entrypoint, startup env).
LAUNCH_SPECS: dict[str, LaunchSpec] = {
    "simulated-learning": LaunchSpec("Simulated Learning", "main:app"),
    "arxiv-papers": LaunchSpec("ArXiv papers", "main:app"),
    "coding-playground": LaunchSpec("Coding playground", "app.main:app"),
    "ai-intelligence-deck": LaunchSpec("Test", "main:app", {"STATIC_DIR": "../frontend/dist"}),
    "social-media-ai": LaunchSpec("Social Media AI", "main:app"),
    "stanford-llm": LaunchSpec("Stanford LLM", "main:app"),
    "stats-teacher": LaunchSpec("Stats Teacher", "app.main:app"),
    "teach-me": LaunchSpec("Teach Me", "main:app"),
    "github-learnings": LaunchSpec("Github Learnings", "app.main:app"),
    "blogs-playground": LaunchSpec("Blogs Playground", "main:app"),
    "research-assistant": LaunchSpec("Research Assistant", "main:app"),
}


def _spawn_uvicorn(spec: LaunchSpec, port: int) -> bool:  # pragma: no cover - real process spawn
    """Start the backend detached on 127.0.0.1:port. Returns False if it cannot be launched."""
    python = spec.venv_python()
    if not python.exists():
        return False
    try:
        subprocess.Popen(
            [
                str(python),
                "-m",
                "uvicorn",
                spec.entrypoint,
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=str(spec.backend_dir()),
            env={**os.environ, **spec.env},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,  # detach: survives the CLI, reused by later runs
        )
    except OSError:
        return False
    return True


async def _health_ok(app: AppEntry, client: httpx.AsyncClient) -> bool:
    if app.base_url is None or app.health is None:
        return False
    try:
        resp = await run_with_deadline(client.get(f"{app.base_url}{app.health}"), _HEALTH_TIMEOUT_S)
    except Exception:
        return False
    return resp.status_code < 500


async def ensure_started(
    app: AppEntry,
    client: httpx.AsyncClient,
    *,
    spawn: Callable[[LaunchSpec, int], bool] = _spawn_uvicorn,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    timeout_s: float = DEFAULT_START_TIMEOUT_S,
    interval_s: float = _POLL_INTERVAL_S,
) -> bool:
    """Start ``app`` if we know how, and wait until it is healthy. Returns True iff healthy.

    Never raises: returns False when there is no launch spec, no port, the spawn fails, or health
    does not come up within ``timeout_s`` — the caller then errors cleanly (no hang).
    """
    spec = LAUNCH_SPECS.get(app.id)
    if spec is None or app.port is None:
        return False
    if not spawn(spec, app.port):
        return False
    for _ in range(max(1, int(timeout_s / interval_s))):
        if await _health_ok(app, client):
            return True
        await sleep(interval_s)
    return False
