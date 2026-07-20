"""Coverage ratchet: every non-internal, non-streaming endpoint of every app must be wired.

"Expose all capabilities" is only true if it is tested. This walks each app's committed OpenAPI
snapshot and asserts the registry wires every endpoint that is not internal (health/root/docs/SPA)
and not deferred streaming (SSE/WebSocket, which need transport code, tracked separately). If a new
endpoint appears in a refreshed snapshot, this test fails until it is wired or explicitly deferred.
"""

from __future__ import annotations

import json

from orchestrator.contract import snapshot_path
from orchestrator.registry import load_registry

_REGISTRY = load_registry()

# Deferred: Server-Sent-Events / WebSocket endpoints need new transport code, not just wiring.
# Tracked in specs/tasks (SSE + WS follow-on tasks). Keep in sync with the wiring generator.
_DEFERRED_STREAMING = {
    ("POST", "/api/build/suggest"),
    ("POST", "/api/chat/code"),
    ("POST", "/api/chat/cross-repo"),
    ("POST", "/api/chat/repo"),
    ("POST", "/api/compare/"),
    ("POST", "/api/blog/generate/streaming"),
    ("GET", "/api/stream/{run_id}"),
    ("GET", "/api/runs/{run_id}/events"),
}


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
