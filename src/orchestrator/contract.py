"""Validate that every wired registry operation matches its app's real HTTP API.

The registry is hand-authored; an app's ``/openapi.json`` is the ground truth. A typo in a path, a
wrong method, or a stale field name would sail through record/replay tests (a fixture just replays a
recorded response) yet 404/422 against the live app. This module closes that gap: it compares each
``AppOperation`` against a committed *slim snapshot* of the app's OpenAPI, so the mismatch is caught
deterministically and offline (as a unit test, hence inside ``make verify``).

Snapshot shape (one file per app, written by ``tools.refresh_openapi``)::

    { "<path>": { "<METHOD>": { "params": [...all field names...], "required": [...] } } }

``params`` is every field a caller can send for that endpoint — path params + query params + request
body properties — so an op field that is not in ``params`` is a typo or points at a field the API
does not have. Kept pure (no I/O beyond ``load_snapshot``) so the matching logic is unit-testable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from orchestrator.registry import AppOperation

# A slim per-app contract: path -> METHOD -> {"params": [...], "required": [...]}.
Snapshot = dict[str, dict[str, dict[str, list[str]]]]

# Request-body media types we extract fields from (JSON, file uploads, HTML forms).
_BODY_MEDIA = ("application/json", "multipart/form-data", "application/x-www-form-urlencoded")

_DEFAULT_SNAPSHOT_DIR = Path(__file__).resolve().parents[2] / "tests" / "contract" / "openapi"


def snapshot_dir() -> Path:
    """Where committed OpenAPI snapshots live (``tests/contract/openapi``)."""
    return _DEFAULT_SNAPSHOT_DIR


def snapshot_path(app_id: str, base: Path | None = None) -> Path:
    return (base or snapshot_dir()) / f"{app_id}.json"


def load_snapshot(path: Path) -> Snapshot:
    """Read a slim snapshot file. Raises if malformed — a broken contract must not pass silently."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"snapshot {path} is not an object")
    return data


def check_op(op: AppOperation, snapshot: Snapshot) -> list[str]:
    """Return human-readable mismatches between ``op`` and the app contract; empty list == conforms.

    Three kinds of defect, each a hard error:
      * the op's path is not an endpoint the app exposes;
      * the app exposes that path but not with the op's HTTP method;
      * the op names a request/required field the endpoint does not accept (typo or stale field).
    """
    problems: list[str] = []
    methods = snapshot.get(op.path)
    if methods is None:
        return [f"{op.name}: path {op.path!r} is not in the app API"]
    method = op.method.upper()
    endpoint = methods.get(method)
    if endpoint is None:
        offered = ", ".join(sorted(methods)) or "none"
        return [f"{op.name}: {method} {op.path!r} not offered (app offers: {offered})"]
    known = set(endpoint.get("params", []))
    # every request_fields / required_fields entry must be a real field of this endpoint.
    for field in dict.fromkeys((*op.request_fields, *op.required_fields)):  # de-dupe, keep order
        if field not in known:
            problems.append(
                f"{op.name}: field {field!r} is not accepted by {method} {op.path} "
                f"(known: {', '.join(sorted(known)) or 'none'})"
            )
    return problems


def check_app(operations: tuple[AppOperation, ...], snapshot: Snapshot) -> list[str]:
    """All mismatches for one app's operations against its snapshot (flattened)."""
    out: list[str] = []
    for op in operations:
        out.extend(check_op(op, snapshot))
    return out


def slim_from_openapi(openapi: dict[str, Any]) -> Snapshot:
    """Reduce a full OpenAPI document to the slim contract we validate against.

    For each path+method: collect path/query parameter names (with their required flags) and, when a
    JSON request body references a component schema, that schema's property names + required set.
    Pure so ``tools.refresh_openapi`` and tests can both use it.
    """
    schemas = openapi.get("components", {}).get("schemas", {})

    def _resolve(schema: dict[str, Any]) -> dict[str, Any]:
        ref = schema.get("$ref")
        comp: dict[str, Any] = schemas.get(ref.split("/")[-1], {}) if ref else schema
        return comp

    def body_fields(operation: dict[str, Any]) -> tuple[list[str], list[str]]:
        # A request body may be JSON, multipart (file uploads), or urlencoded — collect fields from
        # whichever content types are present, resolving a $ref or reading an inline schema.
        props: list[str] = []
        required: list[str] = []
        content = operation.get("requestBody", {}).get("content", {})
        for media in _BODY_MEDIA:
            schema = content.get(media, {}).get("schema")
            if not schema:
                continue
            comp = _resolve(schema)
            props.extend(comp.get("properties", {}).keys())
            required.extend(comp.get("required", []))
        return props, required

    slim: Snapshot = {}
    for path, methods in openapi.get("paths", {}).items():
        for method, operation in methods.items():
            if method.upper() not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                continue
            params, required = [], []
            for param in operation.get("parameters", []):
                name = param.get("name")
                if not name:
                    continue
                params.append(name)
                if param.get("required"):
                    required.append(name)
            bprops, breq = body_fields(operation)
            params.extend(bprops)
            required.extend(breq)
            slim.setdefault(path, {})[method.upper()] = {
                "params": list(dict.fromkeys(params)),
                "required": list(dict.fromkeys(required)),
            }
    return slim
