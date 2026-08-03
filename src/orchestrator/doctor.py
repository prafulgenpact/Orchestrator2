"""Preflight doctor: which sibling apps are ready, and — for the ones that are down — why.

`python -m orchestrator.doctor` probes every app's health endpoint and, for any that is not up,
reports the real reason captured from its startup log (a down database, a missing key, an import
error) instead of a bare "not reachable". Use it before a run, or when a step errors with a health
failure, to see the true cause at a glance.

The health probe + process entry are I/O and marked ``# pragma: no cover``; the pure diagnosis and
rendering are unit-tested.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx

from orchestrator.launcher import _health_ok, read_startup_error
from orchestrator.registry import AppEntry, Registry, load_registry

HealthFn = Callable[[AppEntry, httpx.AsyncClient], Awaitable[bool]]


@dataclass(frozen=True)
class AppDiag:
    """One app's readiness verdict."""

    app_id: str
    name: str
    port: int | None
    healthy: bool
    reason: str | None  # why it's down (captured startup error), when not healthy


async def diagnose(
    registry: Registry, client: httpx.AsyncClient, *, health: HealthFn = _health_ok
) -> list[AppDiag]:
    """Probe every non-fallback app; for a down app, attach its captured startup reason."""
    diags: list[AppDiag] = []
    for app in registry.apps:
        if app.fallback:
            continue
        healthy = await health(app, client)
        reason = None if healthy else (read_startup_error(app.id) or "not running (no startup log)")
        diags.append(AppDiag(app.id, app.name, app.port, healthy, reason))
    return diags


def render_doctor(diags: list[AppDiag]) -> str:
    """A readable readiness report: an UP/DOWN line per app, with the reason for each down app."""
    up = sum(1 for d in diags if d.healthy)
    lines = [f"App readiness — {up}/{len(diags)} up", ""]
    width = max((len(d.name) for d in diags), default=0)
    for d in diags:
        mark = "UP  " if d.healthy else "DOWN"
        port = f":{d.port}" if d.port else ""
        lines.append(f"  {mark}  {d.name.ljust(width)}  {port}")
        if not d.healthy and d.reason:
            lines.append(f"        └─ {d.reason}")
    return "\n".join(lines)


async def _run() -> str:  # pragma: no cover - live I/O, exercised by the acceptance run
    async with httpx.AsyncClient() as client:
        return render_doctor(await diagnose(load_registry(), client))


def main() -> int:  # pragma: no cover - process entry
    print(asyncio.run(_run()))
    return 0


if __name__ == "__main__":  # pragma: no cover - process entry
    raise SystemExit(main())
