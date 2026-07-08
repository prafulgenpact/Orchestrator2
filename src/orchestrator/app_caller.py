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
) -> CallResult:
    """Invoke one operation on ``app`` and return a CallResult. Never raises."""
    cb = breaker or CircuitBreaker()
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
        base_url = await _resolve_base_url(app, client, launcher_url)
        if not await _is_healthy(base_url, app, client):
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
