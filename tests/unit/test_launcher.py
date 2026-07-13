"""Unit tests for the on-demand app launcher (no real processes; injected spawn + MockTransport)."""

from __future__ import annotations

import asyncio

import httpx

from orchestrator.launcher import LAUNCH_SPECS, LaunchSpec, _health_ok, ensure_started
from orchestrator.registry import AppEntry, load_registry

REG = load_registry()


def _arxiv() -> AppEntry:
    app = REG.get("arxiv-papers")
    assert app is not None
    return app


def _client(status: int = 200, raises: bool = False) -> httpx.AsyncClient:
    def handler(_req: httpx.Request) -> httpx.Response:
        if raises:
            raise RuntimeError("connection dropped")
        return httpx.Response(status)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def _no_sleep(_s: float) -> None:
    return None


# --- launch specs ------------------------------------------------------------


def test_launch_specs_cover_all_apps() -> None:
    for app in REG.apps:
        if not app.fallback:
            assert app.id in LAUNCH_SPECS, app.id
    for spec in LAUNCH_SPECS.values():
        assert spec.folder and spec.entrypoint
        assert spec.backend_dir().name == "backend"
        assert spec.venv_python().name == "python"


# --- ensure_started ----------------------------------------------------------


def _run_ensure(app: AppEntry, client: httpx.AsyncClient, **kw: object) -> bool:
    async def go() -> bool:
        async with client as c:
            return await ensure_started(app, c, sleep=_no_sleep, **kw)  # type: ignore[arg-type]

    return asyncio.run(go())


def test_ensure_started_success() -> None:
    # spawn "works" and health is up on the first poll
    assert _run_ensure(_arxiv(), _client(200), spawn=lambda _s, _p: True) is True


def test_ensure_started_no_spec() -> None:
    ghost = AppEntry("ghost", "Ghost", "d", (), (), False, port=9999, health="/h")
    assert _run_ensure(ghost, _client(200), spawn=lambda _s, _p: True) is False


def test_ensure_started_spawn_fails() -> None:
    assert _run_ensure(_arxiv(), _client(200), spawn=lambda _s, _p: False) is False


def test_ensure_started_health_never_comes_up() -> None:
    # spawn works but health stays 500 -> bounded polling gives up (never hangs)
    result = _run_ensure(
        _arxiv(), _client(500), spawn=lambda _s, _p: True, timeout_s=3, interval_s=1
    )
    assert result is False


# --- _health_ok --------------------------------------------------------------


def test_health_ok_true_on_2xx() -> None:
    async def go() -> bool:
        async with _client(200) as c:
            return await _health_ok(_arxiv(), c)

    assert asyncio.run(go()) is True


def test_health_ok_false_when_no_health_path() -> None:
    app = AppEntry("x", "X", "d", (), (), False, port=8080, health=None)

    async def go() -> bool:
        async with _client(200) as c:
            return await _health_ok(app, c)

    assert asyncio.run(go()) is False


def test_health_ok_false_on_exception() -> None:
    async def go() -> bool:
        async with _client(raises=True) as c:
            return await _health_ok(_arxiv(), c)

    assert asyncio.run(go()) is False


def test_launch_spec_paths() -> None:
    spec = LaunchSpec("Some App", "main:app", {"K": "v"})
    assert spec.backend_dir().as_posix().endswith("Some App/backend")
    assert spec.env == {"K": "v"}
