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

# Deliberately NOT selectable: unsafe duplicates of a safe pipeline. Both sync blog-generate
# endpoints expose 7 type-risky fields that the trimmed generate_blog_async deliberately hides,
# so offering them made op choice a lottery between a safe path and a 422->web-fallback path
# (task 20260724-selector-schema-safety; guarded by test_blogs_single_generate_op).
_DELIBERATELY_UNWIRED: set[tuple[str, str]] = {
    ("POST", "/api/blog/generate"),
    ("POST", "/api/blog/generate/streaming"),
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
                if key in _DEFERRED_STREAMING or key in _DELIBERATELY_UNWIRED or key in wired:
                    continue
                unwired.append(f"{app.id}: {method} {endpoint_path}")
    assert not unwired, "unwired non-streaming endpoints:\n" + "\n".join(sorted(unwired))


def _op(app_id: str, op_name: str):
    app = _REGISTRY.get(app_id)
    assert app is not None, f"missing app {app_id}"
    return next(o for o in app.operations if o.name == op_name)


def test_blog_import_publishes_fast_without_inline_critique() -> None:
    """Regression: Blogs Playground must PUBLISH, not error at the deadline.

    /api/blog/import runs an inline StyleCritic+Verifier (~30-60s+, two LLM calls) when
    ``run_critique`` is true (the app defaults it True), which blew the op's hard 60s deadline. The
    contract now (1) defaults ``run_critique=false`` so import takes the instant path and is sent
    in the POST body, (2) drops ``run_critique`` from the model-filled ``request_fields`` so it
    can't be turned back on, and (3) keeps a generous anti-hang backstop deadline.
    """
    op = _op("blogs-playground", "post_blog_import")
    assert op.defaults.get("run_critique") is False, "import must default to the fast publish path"
    assert "run_critique" not in op.request_fields, "run_critique must not be model-selectable"
    assert op.timeout_s >= 120, "keep a generous anti-hang backstop for a slow save"
