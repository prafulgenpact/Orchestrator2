"""Call one app operation over HTTP, wrapped in the block-B no-hang safety layer.

Resolves the app's live base URL (via the launcher, falling back to the registry port),
health-checks it, then performs a single HTTP call under a hard wall-clock deadline, bounded
transient retries, and a per-app circuit breaker. Returns a ``CallResult`` and never raises —
the executor decides what to do with a failed call.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

from orchestrator.launcher import ensure_started
from orchestrator.registry import AppEntry, AppOperation
from orchestrator.resilience import (
    CircuitBreaker,
    classify_error,
    retry_async,
    run_with_deadline,
)

DEFAULT_LAUNCHER_URL = "http://127.0.0.1:5050"
_HEALTH_TIMEOUT_S = 5.0

# The launcher registered research-assistant under a misspelled id.
_LAUNCHER_APP_ID = {"research-assistant": "reseacrh-assistant"}


@dataclass(frozen=True)
class CallResult:
    """The outcome of a single HTTP call to an app operation (never raised)."""

    app_id: str
    operation: str
    url: str
    ok: bool
    status_code: int | None
    data: Any
    error: str | None
    duration_s: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "app_id": self.app_id,
            "operation": self.operation,
            "url": self.url,
            "ok": self.ok,
            "status_code": self.status_code,
            "data": self.data,
            "error": self.error,
            "duration_s": round(self.duration_s, 3),
        }


def _status_of(exc: BaseException) -> int | None:
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return status if isinstance(status, int) and not isinstance(status, bool) else None


def _parse_body(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return resp.text


async def _resolve_base_url(app: AppEntry, client: httpx.AsyncClient, launcher_url: str) -> str:
    """Prefer the launcher's live backend_port; fall back to the registry port."""
    launcher_id = _LAUNCHER_APP_ID.get(app.id, app.id)
    try:
        resp = await run_with_deadline(client.get(f"{launcher_url}/api/apps"), _HEALTH_TIMEOUT_S)
        payload: Any = resp.json()
        for entry in payload.get("apps", []):
            if entry.get("id") == launcher_id and isinstance(entry.get("backend_port"), int):
                return f"http://127.0.0.1:{entry['backend_port']}"
    except Exception:
        pass  # launcher unreachable/misbehaving — fall back to the registry port
    if app.base_url is None:
        raise ValueError(f"app {app.id!r} has no port to call")
    return app.base_url


async def _is_healthy(base_url: str, app: AppEntry, client: httpx.AsyncClient) -> bool:
    if app.health is None:
        return True
    try:
        resp = await run_with_deadline(client.get(f"{base_url}{app.health}"), _HEALTH_TIMEOUT_S)
    except Exception:
        return False
    return resp.status_code < 500


class AppEndpoints:
    """Per-run cache of resolved base URLs + confirmed health, keyed by app id.

    Without it, every ``call_operation`` re-issues ``GET /api/apps`` (launcher resolve) and
    ``GET {health}`` before the real request — cheap once, but on the async poll path
    (``_run_async`` calls ``call_operation`` for the start AND every poll) it becomes ~2 wasted
    round-trips per poll. Sharing one instance across a run resolves + health-confirms each app
    ONCE (auto-starting a down app on first miss, exactly as before) and reuses both. The safety is
    unchanged: an app is still confirmed alive once, and any later death still surfaces on the real
    request (circuit breaker / clean error). Not thread-safe by design — it lives on the asyncio
    loop, where coroutines interleave only at await points; a duplicate probe under a race is just
    a redundant GET, never a correctness issue.
    """

    def __init__(self) -> None:
        self._base: dict[str, str] = {}
        self._healthy: set[str] = set()

    async def base_url(self, app: AppEntry, client: httpx.AsyncClient, launcher_url: str) -> str:
        if app.id not in self._base:
            self._base[app.id] = await _resolve_base_url(app, client, launcher_url)
        return self._base[app.id]

    async def ensure_healthy(self, base_url: str, app: AppEntry, client: httpx.AsyncClient) -> bool:
        """True if the app is healthy (cached after the first success). On a first-time miss, try
        to auto-start it and re-check — the user never starts apps by hand."""
        if app.id in self._healthy:
            return True
        if not await _is_healthy(base_url, app, client):
            await ensure_started(app, client)
            if not await _is_healthy(base_url, app, client):
                return False
        self._healthy.add(app.id)
        return True


def _build_request(
    base_url: str, op: AppOperation, args: dict[str, Any]
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Return (url, query_params, json_body). Path params are substituted into the path."""
    path = op.path
    rest = dict(args)
    for key in list(rest):
        placeholder = "{" + key + "}"
        if placeholder in path:
            path = path.replace(placeholder, str(rest.pop(key)))
    url = f"{base_url}{path}"
    if op.method == "GET":
        return url, rest, {}
    return url, {}, rest


async def call_operation(
    app: AppEntry,
    op: AppOperation,
    args: dict[str, Any],
    *,
    client: httpx.AsyncClient,
    breaker: CircuitBreaker | None = None,
    launcher_url: str = DEFAULT_LAUNCHER_URL,
    endpoints: AppEndpoints | None = None,
) -> CallResult:
    """Invoke one operation on ``app`` and return a CallResult. Never raises.

    Pass a shared ``endpoints`` to reuse the resolved base URL + health across calls in one run
    (see ``AppEndpoints``); the default creates a throwaway one, i.e. resolve + health every call.
    """
    cb = breaker or CircuitBreaker()
    eps = endpoints or AppEndpoints()
    key = app.id
    start = time.monotonic()
    if cb.is_open(key):
        return CallResult(
            app.id,
            op.name,
            "",
            False,
            None,
            None,
            "circuit open: app skipped after repeated failures",
            0.0,
        )
    url = ""
    try:
        base_url = await eps.base_url(app, client, launcher_url)
        # Resolve + health-confirm once per app per run (auto-starting a down app on first miss);
        # a shared ``endpoints`` means repeated calls (esp. the poll loop) skip the duplicate pings.
        if not await eps.ensure_healthy(base_url, app, client):
            raise ConnectionError(f"health check failed for {app.id} at {base_url}{app.health}")
        url, params, body = _build_request(base_url, op, args)

        async def attempt() -> httpx.Response:
            resp = await run_with_deadline(
                # timeout=op.timeout_s: httpx's own per-read timeout must match the operation's
                # budget, else its 5s default fires first on slow (e.g. LLM-backed) calls. The
                # run_with_deadline wrapper remains the HARD total cap (the anti-hang guarantee).
                client.request(
                    op.method,
                    url,
                    params=params or None,
                    json=body or None,
                    timeout=op.timeout_s,
                ),
                op.timeout_s,
            )
            resp.raise_for_status()
            return resp

        resp = await retry_async(
            attempt, transient_max=op.retry.transient_max, backoff_s=op.retry.backoff_s
        )
        cb.record_success(key)
        return CallResult(
            app.id,
            op.name,
            url,
            True,
            resp.status_code,
            _parse_body(resp),
            None,
            time.monotonic() - start,
        )
    except Exception as exc:
        cb.record_failure(key)
        # Fall back to the exception type when its message is empty (e.g. httpx.ReadTimeout('')),
        # so the error is never a bare "fatal:" with no detail.
        detail = str(exc) or type(exc).__name__
        return CallResult(
            app.id,
            op.name,
            url,
            False,
            _status_of(exc),
            None,
            f"{classify_error(exc)}: {detail}",
            time.monotonic() - start,
        )
