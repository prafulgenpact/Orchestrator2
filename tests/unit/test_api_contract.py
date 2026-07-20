"""Contract guardrail: every wired registry op must match its app's real HTTP API.

Validates the hand-authored registry against committed slim OpenAPI snapshots
(``tests/contract/openapi/<app_id>.json``, produced by ``tools.refresh_openapi``). Because this
runs under ``py-unit`` it is enforced by ``make verify`` — a wrong method/path/field can no longer
be sealed. An app with no snapshot yet SKIPS (never errors), mirroring the eval's missing fixture.
"""

from __future__ import annotations

import pytest

from orchestrator.contract import (
    check_op,
    load_snapshot,
    slim_from_openapi,
    snapshot_path,
)
from orchestrator.registry import AppOperation, load_registry

_REGISTRY = load_registry()


def _op_cases() -> list:
    cases: list = []
    for app in _REGISTRY.apps:
        if app.fallback:
            continue
        path = snapshot_path(app.id)
        if not path.exists():
            continue
        snap = load_snapshot(path)
        for op in app.operations:
            if op.stream == "ws":
                continue  # WebSocket ops are not HTTP endpoints; not in any /openapi.json
            cases.append(pytest.param(app.id, op, snap, id=f"{app.id}:{op.name}"))
    return cases


_CASES = _op_cases()


def _make_op(method: str, path: str, *, request_fields: tuple[str, ...] = ()) -> AppOperation:
    return AppOperation(
        name="synthetic",
        description="",
        method=method,
        path=path,
        timeout_s=10,
        destructive=False,
        idempotency="none",
        request_fields=request_fields,
    )


def test_contract_has_meaningful_coverage() -> None:
    """The guardrail must not silently no-op if snapshots go missing (vacuous-pass guard)."""
    assert len(_CASES) >= 50, f"expected the contract test to validate 50+ ops, got {len(_CASES)}"


@pytest.mark.parametrize("app_id,op,snap", _CASES)
def test_every_op_path_and_method_exists(app_id: str, op: AppOperation, snap: dict) -> None:
    assert op.path in snap, f"{app_id}.{op.name}: path {op.path!r} is not in the app API"
    methods = snap[op.path]
    assert (
        op.method.upper() in methods
    ), f"{app_id}.{op.name}: {op.method} {op.path} not offered (app offers {sorted(methods)})"


@pytest.mark.parametrize("app_id,op,snap", _CASES)
def test_op_fields_exist_in_schema(app_id: str, op: AppOperation, snap: dict) -> None:
    # Only assert on field-level problems here; path/method are covered by the test above.
    field_problems = [p for p in check_op(op, snap) if "field" in p]
    assert not field_problems, f"{app_id}: " + "\n".join(field_problems)


def test_bogus_op_is_rejected() -> None:
    """The guardrail actually bites: bad path / method / field are each caught."""
    snap = {"/real": {"GET": {"params": ["a"], "required": ["a"]}}}
    assert check_op(_make_op("GET", "/real", request_fields=("a",)), snap) == []
    assert check_op(_make_op("GET", "/nope"), snap)  # unknown path
    assert check_op(_make_op("POST", "/real"), snap)  # wrong method
    assert check_op(_make_op("GET", "/real", request_fields=("zzz",)), snap)  # unknown field


def test_slim_from_openapi_reads_json_multipart_and_params() -> None:
    """The extractor captures path/query params, JSON body, and multipart (file-upload) fields."""
    openapi = {
        "paths": {
            "/eda/{ds}/dist": {
                "get": {"parameters": [{"name": "ds", "required": True}, {"name": "col"}]},
            },
            "/train": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/T"}}
                        }
                    }
                }
            },
            "/upload": {
                "post": {
                    "requestBody": {
                        "content": {
                            "multipart/form-data": {"schema": {"$ref": "#/components/schemas/U"}}
                        }
                    }
                }
            },
        },
        "components": {
            "schemas": {
                "T": {"properties": {"a": {}, "b": {}}, "required": ["a"]},
                "U": {"properties": {"file": {}}, "required": ["file"]},
            }
        },
    }
    slim = slim_from_openapi(openapi)
    assert slim["/eda/{ds}/dist"]["GET"]["params"] == ["ds", "col"]
    assert slim["/eda/{ds}/dist"]["GET"]["required"] == ["ds"]
    assert set(slim["/train"]["POST"]["params"]) == {"a", "b"}
    assert slim["/train"]["POST"]["required"] == ["a"]
    assert slim["/upload"]["POST"]["params"] == ["file"]  # multipart body captured
