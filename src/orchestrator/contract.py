"""Validate that every wired registry operation matches its app's real HTTP API.

The registry is hand-authored; an app's ``/openapi.json`` is the ground truth. A typo in a path, a
wrong method, or a stale field name would sail through record/replay tests (a fixture just replays a
recorded response) yet 404/422 against the live app. This module closes that gap: it compares each
``AppOperation`` against a committed *slim snapshot* of the app's OpenAPI, so the mismatch is caught
deterministically and offline (as a unit test, hence inside ``make verify``).

Snapshot shape (one file per app, written by ``tools.refresh_openapi``)::

    { "<path>": { "<METHOD>": { "params": [...], "required": [...], "types": {field: type} } } }

``params`` is every field a caller can send for that endpoint — path params + query params + request
body properties — so an op field that is not in ``params`` is a typo or points at a field the API
does not have. ``types`` maps each field to its JSON-schema type (integer/boolean/…) so the selector
can fill values correctly instead of 422-ing the app with a wrongly-typed guess (live proof:
"short blog" → ``word_count_target: "short"`` → 422 → web fallback). Older snapshots without
``types`` stay valid. Kept pure (no I/O beyond ``load_snapshot``) so the matching logic is
unit-testable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from orchestrator.registry import AppOperation

# A slim per-app contract: path -> METHOD -> {"params": [...], "required": [...], "types": {...}}.
Snapshot = dict[str, dict[str, dict[str, Any]]]

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
    if op.stream == "ws":
        return []  # WebSocket ops are not in any /openapi.json — nothing to validate against
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


def field_types(op: AppOperation, snapshot: Snapshot) -> dict[str, str]:
    """The ``{field: json-type}`` map for one op's endpoint; empty when unknown (old snapshot)."""
    endpoint = snapshot.get(op.path, {}).get(op.method.upper(), {})
    types = endpoint.get("types")
    return dict(types) if isinstance(types, dict) else {}


def slim_from_openapi(openapi: dict[str, Any]) -> Snapshot:
    """Reduce a full OpenAPI document to the slim contract we validate against.

    For each path+method: collect path/query parameter names (with their required flags), each
    field's JSON-schema type, and, when a JSON request body references a component schema, that
    schema's property names + required set. Pure so ``tools.refresh_openapi`` and tests can both
    use it.
    """
    schemas = openapi.get("components", {}).get("schemas", {})

    def _resolve(schema: dict[str, Any]) -> dict[str, Any]:
        ref = schema.get("$ref")
        comp: dict[str, Any] = schemas.get(ref.split("/")[-1], {}) if ref else schema
        return comp

    def _schema_type(schema: dict[str, Any] | None) -> str | None:
        # FastAPI renders Optional[int] as anyOf[{integer},{null}] — take the first non-null arm.
        if not isinstance(schema, dict):
            return None
        comp = _resolve(schema)
        comp_type = comp.get("type")
        if isinstance(comp_type, str):
            return comp_type
        for arm in comp.get("anyOf", []):
            arm_type = _schema_type(arm)
            if arm_type and arm_type != "null":
                return arm_type
        return None

    def body_fields(operation: dict[str, Any]) -> tuple[list[str], list[str], dict[str, str]]:
        # A request body may be JSON, multipart (file uploads), or urlencoded — collect fields from
        # whichever content types are present, resolving a $ref or reading an inline schema.
        props: list[str] = []
        required: list[str] = []
        types: dict[str, str] = {}
        content = operation.get("requestBody", {}).get("content", {})
        for media in _BODY_MEDIA:
            schema = content.get(media, {}).get("schema")
            if not schema:
                continue
            comp = _resolve(schema)
            for name, prop in comp.get("properties", {}).items():
                props.append(name)
                prop_type = _schema_type(prop)
                if prop_type:
                    types.setdefault(name, prop_type)
            required.extend(comp.get("required", []))
        return props, required, types

    slim: Snapshot = {}
    for path, methods in openapi.get("paths", {}).items():
        for method, operation in methods.items():
            if method.upper() not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                continue
            params, required = [], []
            types: dict[str, str] = {}
            for param in operation.get("parameters", []):
                name = param.get("name")
                if not name:
                    continue
                params.append(name)
                if param.get("required"):
                    required.append(name)
                param_type = _schema_type(param.get("schema"))
                if param_type:
                    types.setdefault(name, param_type)
            bprops, breq, btypes = body_fields(operation)
            params.extend(bprops)
            required.extend(breq)
            for name, prop_type in btypes.items():
                types.setdefault(name, prop_type)
            slim.setdefault(path, {})[method.upper()] = {
                "params": list(dict.fromkeys(params)),
                "required": list(dict.fromkeys(required)),
                "types": dict(sorted(types.items())),
            }
    return slim
