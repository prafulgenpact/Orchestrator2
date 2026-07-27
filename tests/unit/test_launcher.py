"""Unit tests for the on-demand app launcher (no real processes; injected spawn + MockTransport)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import httpx

from orchestrator.launcher import (
    LAUNCH_SPECS,
    LaunchSpec,
    _health_ok,
    ensure_started,
    is_healthy_response,
    reap_stale_listeners,
    start_all,
)
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
    # Default reap to a hermetic no-op so tests never touch real processes (lsof/ps/kill); a test
    # that exercises the reap path passes its own fake via reap=...
    kw.setdefault("reap", lambda _port, _spec: [])

    async def go() -> bool:
        async with client as c:
            return await ensure_started(app, c, sleep=_no_sleep, **kw)  # type: ignore[arg-type]

    return asyncio.run(go())


def _flip_client(first: int, rest: int) -> httpx.AsyncClient:
    """Health probe returns ``first`` once (500 = down), then ``rest`` (200 = recovered)."""
    calls = {"n": 0}

    def handler(_req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(first if calls["n"] == 1 else rest)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_ensure_started_already_healthy_skips_spawn() -> None:
    # Health-first: an app already answering is used as-is — no duplicate spawn, no reap.
    spawned = {"n": 0}

    def _spawn(_s: LaunchSpec, _p: int) -> bool:
        spawned["n"] += 1
        return True

    assert _run_ensure(_arxiv(), _client(200), spawn=_spawn) is True
    assert spawned["n"] == 0  # never spawned a duplicate over a live app


def test_ensure_started_reaps_then_respawns() -> None:
    # Down at first (500), so we reap the stale listener, spawn, then health recovers (200).
    reaped = {"n": 0}

    def _reap(_port: int, _spec: LaunchSpec) -> list[int]:
        reaped["n"] += 1
        return [42]  # pretend a stale pid was killed

    ok = _run_ensure(
        _arxiv(), _flip_client(500, 200), spawn=lambda _s, _p: True, reap=_reap, interval_s=1
    )
    assert ok is True
    assert reaped["n"] == 1  # reap ran exactly once, before the respawn


def test_ensure_started_no_spec() -> None:
    ghost = AppEntry("ghost", "Ghost", "d", (), (), False, port=9999, health="/h")
    assert _run_ensure(ghost, _client(500), spawn=lambda _s, _p: True) is False


def test_ensure_started_spawn_fails() -> None:
    # Unhealthy so it proceeds past health-first to the spawn, which fails -> False.
    assert _run_ensure(_arxiv(), _client(500), spawn=lambda _s, _p: False) is False


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


# --- is_healthy_response (honest health verdict, defeats the SPA false-positive) --------------


def test_json_2xx_is_healthy() -> None:
    assert is_healthy_response(200, "application/json") is True
    assert is_healthy_response(204, "") is True


def test_html_response_is_not_healthy() -> None:
    # The SPA catch-all returns 200 text/html for ANY path (teach-me /models) — must NOT be healthy.
    assert is_healthy_response(200, "text/html; charset=utf-8") is False


def test_non_2xx_is_not_healthy() -> None:
    assert is_healthy_response(404, "application/json") is False
    assert is_healthy_response(500, "application/json") is False


def test_health_ok_false_on_html_spa_page() -> None:
    # End-to-end through _health_ok: a 200 HTML body (the SPA page) is not a healthy API.
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<!doctype html>")

    async def go() -> bool:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await _health_ok(_arxiv(), c)

    assert asyncio.run(go()) is False


# --- reap_stale_listeners (safe recovery of a hung process squatting the port) ----------------

_ARXIV_SPEC = LAUNCH_SPECS["arxiv-papers"]  # folder "ArXiv papers", entrypoint "main:app"


def test_reap_kills_only_matching_process() -> None:
    # THIS app's own uvicorn launch line (uvicorn + entrypoint + the app's port) is killed. This
    # mirrors a REAL launch line — the folder/cwd is NOT in argv, so matching is on the port.
    matching = f"python -m uvicorn {_ARXIV_SPEC.entrypoint} --host 127.0.0.1 --port 8002"
    killed: list[int] = []
    result = reap_stale_listeners(
        8002,
        _ARXIV_SPEC,
        list_pids=lambda _p: [111],
        cmdline=lambda _pid: matching,
        kill=killed.append,
    )
    assert result == [111]
    assert killed == [111]


def test_reap_spares_unrelated_process() -> None:
    # A process on the port we cannot positively attribute to this app is NEVER killed.
    killed: list[int] = []
    for foreign in (
        "postgres: server process",  # not uvicorn
        "python -m uvicorn app.main:app --port 8002",  # different entrypoint (not arxiv's main:app)
        "python -m uvicorn main:app --port 9999",  # uvicorn+entrypoint but a DIFFERENT port
        "",  # unknown / unreadable
    ):
        result = reap_stale_listeners(
            8002,
            _ARXIV_SPEC,
            list_pids=lambda _p: [222],
            cmdline=lambda _pid, c=foreign: c,
            kill=killed.append,
        )
        assert result == []
    assert killed == []  # nothing unrelated was touched


def test_launch_spec_paths() -> None:
    spec = LaunchSpec("Some App", "main:app", {"K": "v"})
    assert spec.backend_dir().as_posix().endswith("Some App/backend")
    assert spec.env == {"K": "v"}


# --- start_all (outset preflight) --------------------------------------------


def _run_start_all(ensure: Callable[..., Awaitable[bool]]) -> dict[str, bool]:
    async def go() -> dict[str, bool]:
        async with _client(200) as c:
            return await start_all(REG.apps, c, ensure=ensure)

    return asyncio.run(go())


def test_start_all_health_map_excludes_fallback() -> None:
    async def ensure(app: AppEntry, _c: httpx.AsyncClient) -> bool:
        return app.id != "social-media-ai"  # one app cannot come up

    result = _run_start_all(ensure)
    # every non-fallback app is reported; the web-search fallback (no port) is not started
    assert "web-search" not in result
    assert set(result) == {a.id for a in REG.apps if not a.fallback}
    assert result["social-media-ai"] is False
    assert result["arxiv-papers"] is True


def test_start_all_maps_exceptions_to_false() -> None:
    async def ensure(app: AppEntry, _c: httpx.AsyncClient) -> bool:
        if app.id == "teach-me":
            raise RuntimeError("spawn blew up")
        return True

    result = _run_start_all(ensure)
    assert result["teach-me"] is False  # never raises — a failed start is just False
    assert result["arxiv-papers"] is True
