"""Unit tests for the app-caller — hermetic via httpx.MockTransport (no real network)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import httpx
import pytest

from orchestrator.app_caller import AppEndpoints, CallResult, call_operation
from orchestrator.registry import AppEntry, AppOperation, RetrySpec, load_registry
from orchestrator.resilience import CircuitBreaker

Handler = Callable[[httpx.Request], httpx.Response]

REG = load_registry()


@pytest.fixture(autouse=True)
def _autostart_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never spawn a real backend in unit tests: auto-start is a no-op unless a test opts in."""

    async def _off(*_a: object, **_kw: object) -> bool:
        return False

    monkeypatch.setattr("orchestrator.app_caller.ensure_started", _off)


def _client(handler: Handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _arxiv() -> tuple[AppEntry, AppOperation]:
    app = REG.get("arxiv-papers")
    assert app is not None
    op = app.operation("search_papers_by_query")
    assert op is not None
    return app, op


def _apps_ok(port: int = 8002) -> httpx.Response:
    return httpx.Response(200, json={"apps": [{"id": "arxiv-papers", "backend_port": port}]})


def test_call_success() -> None:
    app, op = _arxiv()

    def handler(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if p == "/api/apps":
            return _apps_ok()
        if p == "/api/health":
            return httpx.Response(200, json={"status": "ok"})
        if p == "/api/papers/search":
            return httpx.Response(200, json={"papers": [{"title": "MoE survey"}]})
        return httpx.Response(404)

    async def go() -> CallResult:
        async with _client(handler) as c:
            return await call_operation(app, op, {"query": "moe", "max_results": 5}, client=c)

    res = asyncio.run(go())
    assert res.ok is True
    assert res.status_code == 200
    assert res.data == {"papers": [{"title": "MoE survey"}]}
    assert res.url.endswith("/api/papers/search")
    assert res.error is None


def test_post_sends_body() -> None:
    app, op = _arxiv()
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if p == "/api/apps":
            return _apps_ok()
        if p == "/api/health":
            return httpx.Response(200, json={"ok": True})
        seen["body"] = req.content.decode()
        return httpx.Response(200, json={"papers": []})

    async def go() -> CallResult:
        async with _client(handler) as c:
            return await call_operation(app, op, {"query": "attention", "max_results": 3}, client=c)

    res = asyncio.run(go())
    assert res.ok is True
    assert "attention" in seen["body"]


def test_get_path_param_and_query() -> None:
    app = REG.get("coding-playground")
    assert app is not None
    op = app.operation("preview_dataset")
    assert op is not None

    def handler(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if p == "/api/apps":
            return httpx.Response(
                200, json={"apps": [{"id": "coding-playground", "backend_port": 8003}]}
            )
        if p == "/health":
            return httpx.Response(200, json={"status": "healthy"})
        if p == "/api/datasets/iris/preview":
            return httpx.Response(200, json={"rows": int(req.url.params["n_rows"])})
        return httpx.Response(404)

    async def go() -> CallResult:
        async with _client(handler) as c:
            return await call_operation(app, op, {"dataset_id": "iris", "n_rows": 10}, client=c)

    res = asyncio.run(go())
    assert res.ok is True
    assert res.url.endswith("/api/datasets/iris/preview")
    assert res.data == {"rows": 10}


def test_text_body_fallback() -> None:
    app = REG.get("stats-teacher")
    assert app is not None
    op = app.operation("ask_question")
    assert op is not None

    def handler(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if p == "/api/apps":
            return httpx.Response(
                200, json={"apps": [{"id": "stats-teacher", "backend_port": 8007}]}
            )
        if p == "/api/health":
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(200, text="a streamed plain-text answer")

    async def go() -> CallResult:
        async with _client(handler) as c:
            return await call_operation(app, op, {"question": "what is a p-value?"}, client=c)

    res = asyncio.run(go())
    assert res.ok is True
    assert res.data == "a streamed plain-text answer"


def test_health_failure_is_reported() -> None:
    app, op = _arxiv()

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/api/apps":
            return _apps_ok()
        return httpx.Response(500)  # health (and anything else) unhealthy

    async def go() -> CallResult:
        async with _client(handler) as c:
            return await call_operation(app, op, {"query": "x"}, client=c)

    res = asyncio.run(go())
    assert res.ok is False
    assert "health check failed" in (res.error or "")


def test_health_failure_surfaces_the_startup_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    # When we captured why the app failed to boot, that real reason is appended to the error, so
    # the trace shows "Postgres refused" instead of a bare "health check failed".
    app, op = _arxiv()
    monkeypatch.setattr(
        "orchestrator.app_caller.read_startup_error",
        lambda _app_id: "OSError: Connect call failed ('127.0.0.1', 5432)",
    )

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/api/apps":
            return _apps_ok()
        return httpx.Response(500)

    async def go() -> CallResult:
        async with _client(handler) as c:
            return await call_operation(app, op, {"query": "x"}, client=c)

    res = asyncio.run(go())
    assert res.ok is False
    assert "failed to start" in (res.error or "")
    assert "5432" in (res.error or "")


class _HangTransport(httpx.AsyncBaseTransport):
    """Serves launcher/health quickly but hangs on the operation call."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/apps":
            return _apps_ok()
        if request.url.path == "/api/health":
            return httpx.Response(200, json={"ok": True})
        await asyncio.sleep(1.0)  # hang past the deadline
        return httpx.Response(200, json={})


def test_deadline_on_hang() -> None:
    app, _ = _arxiv()
    slow = AppOperation(
        name="slow",
        description="d",
        method="GET",
        path="/api/slow",
        timeout_s=0.05,
        destructive=False,
        idempotency="none",
        retry=RetrySpec(0, 0.0),
    )

    async def go() -> CallResult:
        async with httpx.AsyncClient(transport=_HangTransport()) as c:
            return await call_operation(app, slow, {}, client=c)

    res = asyncio.run(go())
    assert res.ok is False
    assert "deadline" in (res.error or "")


def test_retry_then_success() -> None:
    app, _ = _arxiv()
    flaky = AppOperation(
        name="flaky",
        description="d",
        method="GET",
        path="/api/flaky",
        timeout_s=2.0,
        destructive=False,
        idempotency="supported",
        retry=RetrySpec(2, 0.01),
    )
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/api/apps":
            return _apps_ok()
        if req.url.path == "/api/health":
            return httpx.Response(200, json={"ok": True})
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503)  # transient -> retried
        return httpx.Response(200, json={"ok": True})

    async def go() -> CallResult:
        async with _client(handler) as c:
            return await call_operation(app, flaky, {}, client=c)

    res = asyncio.run(go())
    assert res.ok is True
    assert calls["n"] == 3


def test_4xx_is_fatal_not_retried() -> None:
    app, _ = _arxiv()
    op = AppOperation(
        name="missing",
        description="d",
        method="GET",
        path="/api/missing",
        timeout_s=2.0,
        destructive=False,
        idempotency="supported",
        retry=RetrySpec(2, 0.01),
    )
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/api/apps":
            return _apps_ok()
        if req.url.path == "/api/health":
            return httpx.Response(200, json={"ok": True})
        calls["n"] += 1
        return httpx.Response(404)

    async def go() -> CallResult:
        async with _client(handler) as c:
            return await call_operation(app, op, {}, client=c)

    res = asyncio.run(go())
    assert res.ok is False
    assert res.status_code == 404
    assert calls["n"] == 1  # fatal -> not retried


def test_circuit_open_skips_call() -> None:
    app, op = _arxiv()
    breaker = CircuitBreaker(threshold=1)
    breaker.record_failure(app.id)  # already open

    def handler(_req: httpx.Request) -> httpx.Response:
        raise AssertionError("must not be called when circuit is open")

    async def go() -> CallResult:
        async with _client(handler) as c:
            return await call_operation(app, op, {"query": "x"}, client=c, breaker=breaker)

    res = asyncio.run(go())
    assert res.ok is False
    assert "circuit open" in (res.error or "")


def test_launcher_unreachable_falls_back_to_registry_port() -> None:
    app, op = _arxiv()

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/api/apps":
            return httpx.Response(500)  # launcher down -> fall back to registry port (8002)
        if req.url.path == "/api/health":
            return httpx.Response(200, json={"ok": True})
        if req.url.path == "/api/papers/search":
            return httpx.Response(200, json={"papers": []})
        return httpx.Response(404)

    async def go() -> CallResult:
        async with _client(handler) as c:
            return await call_operation(app, op, {"query": "x"}, client=c)

    res = asyncio.run(go())
    assert res.ok is True
    assert res.url.startswith("http://127.0.0.1:8002")


def test_app_without_port_errors() -> None:
    op = AppOperation(
        name="op",
        description="d",
        method="GET",
        path="/x",
        timeout_s=1.0,
        destructive=False,
        idempotency="supported",
        retry=RetrySpec(0, 0.0),
    )
    portless = AppEntry(
        "ghost", "Ghost", "d", (), (), False, port=None, health=None, operations=(op,)
    )

    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"apps": []})  # not found in launcher

    async def go() -> CallResult:
        async with _client(handler) as c:
            return await call_operation(portless, op, {}, client=c)

    res = asyncio.run(go())
    assert res.ok is False
    assert "no port" in (res.error or "")


def test_call_result_to_dict_rounds_duration() -> None:
    r = CallResult("arxiv-papers", "search", "http://x", True, 200, {"a": 1}, None, 1.2345)
    d = r.to_dict()
    assert d["app_id"] == "arxiv-papers"
    assert d["ok"] is True
    assert d["duration_s"] == 1.234


def test_launcher_picks_matching_entry_among_others() -> None:
    app, op = _arxiv()

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/api/apps":
            return httpx.Response(
                200,
                json={
                    "apps": [
                        {"id": "other", "backend_port": 9999},
                        {"id": "arxiv-papers", "backend_port": 8002},
                    ]
                },
            )
        if req.url.path == "/api/health":
            return httpx.Response(200, json={"ok": True})
        if req.url.path == "/api/papers/search":
            return httpx.Response(200, json={"papers": []})
        return httpx.Response(404)

    async def go() -> CallResult:
        async with _client(handler) as c:
            return await call_operation(app, op, {"query": "x"}, client=c)

    res = asyncio.run(go())
    assert res.ok is True
    assert res.url.startswith("http://127.0.0.1:8002")


def test_no_health_path_skips_health_check() -> None:
    op = AppOperation(
        name="ping",
        description="d",
        method="GET",
        path="/ping",
        timeout_s=2.0,
        destructive=False,
        idempotency="supported",
        retry=RetrySpec(0, 0.0),
    )
    app = AppEntry(
        "nohealth", "NoHealth", "d", (), (), False, port=8080, health=None, operations=(op,)
    )

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/api/apps":
            return httpx.Response(500)  # fall back to the registry port
        if req.url.path == "/ping":
            return httpx.Response(200, json={"pong": True})
        return httpx.Response(404)

    async def go() -> CallResult:
        async with _client(handler) as c:
            return await call_operation(app, op, {}, client=c)

    res = asyncio.run(go())
    assert res.ok is True
    assert res.data == {"pong": True}


def test_health_check_exception_is_unhealthy() -> None:
    app, op = _arxiv()

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/api/apps":
            return _apps_ok()
        raise RuntimeError("connection dropped")  # health GET raises

    async def go() -> CallResult:
        async with _client(handler) as c:
            return await call_operation(app, op, {"query": "x"}, client=c)

    res = asyncio.run(go())
    assert res.ok is False
    assert "health check failed" in (res.error or "")


# --- bugfix: per-operation timeout + non-empty error rendering (app-caller-timeout task) ---


def _slow_op(timeout_s: float) -> AppOperation:
    return AppOperation(
        name="analyze",
        description="LLM-backed, legitimately slow",
        method="POST",
        path="/api/ai/analyze",
        timeout_s=timeout_s,
        destructive=False,
        idempotency="none",
        retry=RetrySpec(0, 0.0),
    )


def test_operation_timeout_is_passed_to_httpx() -> None:
    # Regression: httpx's 5s default must NOT shadow the operation's own (larger) budget.
    app, _ = _arxiv()
    op = _slow_op(90.0)
    seen: dict[str, object] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if p == "/api/apps":
            return _apps_ok()
        if p == "/api/health":
            return httpx.Response(200, json={"ok": True})
        seen["timeout"] = req.extensions.get("timeout")
        return httpx.Response(200, json={"ok": True})

    async def go() -> CallResult:
        async with _client(handler) as c:
            return await call_operation(app, op, {"arxiv_id": "x", "mode": "takeaways"}, client=c)

    res = asyncio.run(go())
    assert res.ok is True
    assert isinstance(seen["timeout"], dict)
    assert seen["timeout"]["read"] == 90.0  # the op's budget, not httpx's 5s default


class _EmptyErrorTransport(httpx.AsyncBaseTransport):
    """Serves launcher/health, then raises an empty-message error on the operation call."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/apps":
            return _apps_ok()
        if request.url.path == "/api/health":
            return httpx.Response(200, json={"ok": True})
        raise httpx.ReadTimeout("")  # empty message, like a real per-read timeout


def test_empty_error_message_includes_exception_type() -> None:
    # Regression: a blank exception string must not render as a bare "fatal:".
    app, _ = _arxiv()
    op = _slow_op(1.0)

    async def go() -> CallResult:
        async with httpx.AsyncClient(transport=_EmptyErrorTransport()) as c:
            return await call_operation(app, op, {}, client=c)

    res = asyncio.run(go())
    assert res.ok is False
    assert (res.error or "").strip() != "fatal:"
    assert "ReadTimeout" in (res.error or "")


# --- auto-start a down app (the user never starts apps by hand) ---------------


def test_call_auto_starts_down_app(monkeypatch: pytest.MonkeyPatch) -> None:
    app, op = _arxiv()
    state = {"up": False}  # the app is down until "started"

    def handler(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if p == "/api/apps":
            return _apps_ok()
        if p == "/api/health":
            return httpx.Response(200 if state["up"] else 500)
        if p == "/api/papers/search":
            return httpx.Response(200, json={"papers": []})
        return httpx.Response(404)

    async def _fake_ensure(_app: object, _client: object, **_kw: object) -> bool:
        state["up"] = True  # "starting" the backend makes the next health check pass
        return True

    monkeypatch.setattr("orchestrator.app_caller.ensure_started", _fake_ensure)

    async def go() -> CallResult:
        async with _client(handler) as c:
            return await call_operation(app, op, {"query": "x"}, client=c)

    res = asyncio.run(go())
    assert res.ok is True  # down app was auto-started, then the call succeeded
    assert res.data == {"papers": []}


def test_call_errors_when_autostart_fails() -> None:
    # autouse _autostart_offline keeps ensure_started False; health stays down -> clean error
    app, op = _arxiv()

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/api/apps":
            return _apps_ok()
        return httpx.Response(500)  # health never comes up

    async def go() -> CallResult:
        async with _client(handler) as c:
            return await call_operation(app, op, {"query": "x"}, client=c)

    res = asyncio.run(go())
    assert res.ok is False
    assert "health check failed" in (res.error or "")


# --- AppEndpoints: cache the launcher-resolve + health per run (cache-endpoint-per-run task) ----


def _counting_arxiv_handler(counts: dict[str, int]) -> Handler:
    def handler(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if p == "/api/apps":
            counts["apps"] = counts.get("apps", 0) + 1
            return _apps_ok()
        if p == "/api/health":
            counts["health"] = counts.get("health", 0) + 1
            return httpx.Response(200, json={"ok": True})
        if p == "/api/papers/search":
            counts["op"] = counts.get("op", 0) + 1
            return httpx.Response(200, json={"papers": []})
        return httpx.Response(404)

    return handler


def test_shared_endpoints_dedupes_resolve_and_health() -> None:
    # A shared AppEndpoints resolves the launcher and checks health ONCE across repeated calls,
    # while every operation call still fires — the poll-loop amplification fix.
    app, op = _arxiv()
    counts: dict[str, int] = {}

    async def go() -> None:
        eps = AppEndpoints()
        async with _client(_counting_arxiv_handler(counts)) as c:
            for _ in range(3):
                await call_operation(app, op, {"query": "x"}, client=c, endpoints=eps)

    asyncio.run(go())
    assert counts["op"] == 3  # every operation call still goes through
    assert counts["apps"] == 1  # launcher resolved once, then cached
    assert counts["health"] == 1  # health checked once, then cached


def test_no_shared_endpoints_resolves_each_call() -> None:
    # Backward compatible: with no shared cache (endpoints=None), each call resolves + health-checks
    # exactly as before.
    app, op = _arxiv()
    counts: dict[str, int] = {}

    async def go() -> None:
        async with _client(_counting_arxiv_handler(counts)) as c:
            for _ in range(3):
                await call_operation(app, op, {"query": "x"}, client=c)

    asyncio.run(go())
    assert counts["op"] == 3
    assert counts["apps"] == 3  # resolved every call (unchanged behaviour)
    assert counts["health"] == 3
