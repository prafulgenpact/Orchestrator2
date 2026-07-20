"""Refresh the committed OpenAPI snapshots the contract test validates against.

Fetches each non-fallback app's live ``/openapi.json`` and writes a slim snapshot to
``tests/contract/openapi/<app_id>.json``. This is the deliberate "reconcile with live reality" step
(the analogue of re-recording replay fixtures): a real API change shows up as a reviewable snapshot
diff, and the contract test then flags any registry op that no longer matches.

Not part of the enforcement layer (``scripts/``) — a developer tool. Run from the repo root::

    PYTHONPATH=src python3 tools/refresh_openapi.py            # all reachable apps
    PYTHONPATH=src python3 tools/refresh_openapi.py arxiv-papers coding-playground

Unreachable apps are skipped with a warning (their existing snapshot, if any, is kept), so this is
safe to run when only some sibling apps are up.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow running as a plain script from the repo root (src/ on path for the orchestrator package).
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import httpx  # noqa: E402

from orchestrator.contract import slim_from_openapi, snapshot_path  # noqa: E402
from orchestrator.registry import load_registry  # noqa: E402

_TIMEOUT_S = 10.0


def refresh(app_ids: list[str] | None = None) -> int:
    """Write snapshots for the requested apps (default: all non-fallback). Returns files written."""
    registry = load_registry()
    out_dir = snapshot_path("_", None).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    with httpx.Client(timeout=_TIMEOUT_S) as client:
        for app in registry.apps:
            if app.fallback or app.base_url is None:
                continue
            if app_ids and app.id not in app_ids:
                continue
            url = f"{app.base_url}/openapi.json"
            try:
                resp = client.get(url)
                resp.raise_for_status()
                slim = slim_from_openapi(resp.json())
            except Exception as exc:  # unreachable / bad response — keep any existing snapshot
                print(f"  SKIP {app.id}: {url} unreachable ({type(exc).__name__})")
                continue
            path = snapshot_path(app.id)
            # sort_keys for stable, reviewable diffs across refreshes
            path.write_text(json.dumps(slim, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(f"  wrote {path.relative_to(out_dir.parents[2])} ({len(slim)} paths)")
            written += 1
    print(f"[refresh-openapi] {written} snapshot(s) written to {out_dir}")
    return written


if __name__ == "__main__":
    refresh(sys.argv[1:] or None)
