"""Coverage ratchet: every non-internal endpoint of every app must be wired (100%).

"Expose all capabilities" is only true if it is tested. This walks each app's committed OpenAPI
snapshot and asserts the registry wires every endpoint that is not internal (health/root/docs/SPA) —
including SSE endpoints, now reachable via the ``stream="sse"`` transport. If a new endpoint appears
in a refreshed snapshot, this test fails until it is wired. (The WebSocket kernel is not in any
app's ``/openapi.json`` and so is outside this snapshot-based denominator.)
"""

from __future__ import annotations

import json

from orchestrator.contract import snapshot_path
from orchestrator.registry import load_registry

_REGISTRY = load_registry()

# Nothing is deferred any more: SSE endpoints are wired via the stream="sse" transport, so 100% of
# non-internal endpoints must be exposed. A non-empty set here would carve out an exception.
_DEFERRED_STREAMING: set[tuple[str, str]] = set()


def _is_internal(path: str) -> bool:
    p = path.lower()
    return "health" in p or "{full_path}" in p or p in ("/", "/docs", "/redoc", "/openapi.json")


def test_all_non_streaming_endpoints_wired() -> None:
    unwired: list[str] = []
    for app in _REGISTRY.apps:
        if app.fallback:
            continue
        path = snapshot_path(app.id)
        if not path.exists():
            continue
        snap = json.loads(path.read_text())
        wired = {(o.method.upper(), o.path) for o in app.operations}
        for endpoint_path, methods in snap.items():
            if _is_internal(endpoint_path):
                continue
            for method in methods:
                key = (method, endpoint_path)
                if key in _DEFERRED_STREAMING or key in wired:
                    continue
                unwired.append(f"{app.id}: {method} {endpoint_path}")
    assert not unwired, "unwired non-streaming endpoints:\n" + "\n".join(sorted(unwired))
