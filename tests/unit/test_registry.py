"""Unit tests for the app registry loader — real file load plus every error branch."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from orchestrator.registry import (
    AppEntry,
    AppOperation,
    Registry,
    RegistryError,
    RetrySpec,
    load_registry,
)

VALID_OP = {
    "name": "start_topic",
    "description": "start a topic",
    "method": "POST",
    "path": "/api/topics",
    "timeout_s": 30,
    "destructive": False,
    "idempotency": "none",
    "retry": {"transient_max": 2, "backoff_s": 3},
    "request_fields": ["title"],
}
VALID_APP = {
    "id": "teach-me",
    "name": "Teach Me",
    "description": "first-principles learning",
    "capabilities": ["start a topic"],
    "example_tasks": ["teach me X"],
    "fallback": False,
    "port": 8008,
    "health": "/api/health",
    "operations": [VALID_OP],
}
FALLBACK_APP = {
    "id": "web-search",
    "name": "Web Search",
    "description": "general web lookup",
    "capabilities": ["fetch facts"],
    "example_tasks": [],
    "fallback": True,
}


def _write(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "apps.json"
    path.write_text(json.dumps(data))
    return path


def _registry(apps: list[Any]) -> dict:
    return {"schema_version": 1, "apps": apps}


def _without(d: dict, key: str) -> dict:
    return {k: v for k, v in d.items() if k != key}


# --- happy path against the real shipped registry ---------------------------


def test_loads_real_registry_with_all_apps() -> None:
    reg = load_registry()
    assert len(reg.apps) == 12
    assert "stanford-llm" in reg.ids()
    assert reg.fallback_id == "web-search"


def test_get_returns_entry_or_none() -> None:
    reg = load_registry()
    entry = reg.get("arxiv-papers")
    assert entry is not None
    assert entry.name == "ArXiv Paper Guide"
    assert reg.get("does-not-exist") is None


def test_to_prompt_dict_is_compact() -> None:
    reg = load_registry()
    entry = reg.get("teach-me")
    assert entry is not None
    d = entry.to_prompt_dict()
    assert set(d) == {"id", "name", "description", "capabilities", "example_tasks", "fallback"}


def test_exactly_one_fallback_in_real_registry() -> None:
    reg = load_registry()
    assert sum(1 for a in reg.apps if a.fallback) == 1


def test_real_registry_call_specs_complete() -> None:
    """AC-4/A2: every non-fallback app in the shipped registry has a complete call-spec."""
    reg = load_registry()
    non_fallback = [a for a in reg.apps if not a.fallback]
    assert len(non_fallback) == 11
    for app in non_fallback:
        assert app.port is not None, app.id
        assert app.health and app.health.startswith("/"), app.id
        assert app.base_url == f"http://127.0.0.1:{app.port}", app.id
        assert app.operations, app.id
        for op in app.operations:
            assert op.method in {"GET", "POST", "PUT", "PATCH", "DELETE"}, (app.id, op.name)
            assert op.path.startswith("/"), (app.id, op.name)
            assert op.timeout_s > 0, (app.id, op.name)
            assert op.idempotency in {"supported", "none"}, (app.id, op.name)


# --- call-spec parsing (A1) --------------------------------------------------


def test_operation_fields_parsed(tmp_path: Path) -> None:
    reg = load_registry(_write(tmp_path, _registry([VALID_APP, FALLBACK_APP])))
    app = reg.get("teach-me")
    assert app is not None
    assert app.port == 8008
    assert app.health == "/api/health"
    assert app.base_url == "http://127.0.0.1:8008"
    op = app.operation("start_topic")
    assert op is not None
    assert op.method == "POST"
    assert op.path == "/api/topics"
    assert op.idempotency == "none"
    assert op.destructive is False
    assert op.retry.transient_max == 2
    assert op.retry.backoff_s == 3.0
    assert op.request_fields == ("title",)
    assert app.operation("missing") is None


def test_operation_required_fields_parsed(tmp_path: Path) -> None:
    op = {**VALID_OP, "required_fields": ["title"]}
    app = {**VALID_APP, "operations": [op]}
    reg = load_registry(_write(tmp_path, _registry([app, FALLBACK_APP])))
    parsed = reg.get("teach-me").operation("start_topic")  # type: ignore[union-attr]
    assert parsed is not None
    assert parsed.required_fields == ("title",)


def test_operation_required_fields_default_empty(tmp_path: Path) -> None:
    reg = load_registry(_write(tmp_path, _registry([VALID_APP, FALLBACK_APP])))
    parsed = reg.get("teach-me").operation("start_topic")  # type: ignore[union-attr]
    assert parsed is not None
    assert parsed.required_fields == ()


def test_operation_defaults_parsed(tmp_path: Path) -> None:
    op = {**VALID_OP, "defaults": {"title": "T"}}
    app = {**VALID_APP, "operations": [op]}
    reg = load_registry(_write(tmp_path, _registry([app, FALLBACK_APP])))
    parsed = reg.get("teach-me").operation("start_topic")  # type: ignore[union-attr]
    assert parsed is not None
    assert parsed.defaults == {"title": "T"}
    assert parsed.to_dict()["defaults"] == {"title": "T"}


def test_operation_defaults_default_empty(tmp_path: Path) -> None:
    reg = load_registry(_write(tmp_path, _registry([VALID_APP, FALLBACK_APP])))
    assert reg.get("teach-me").operation("start_topic").defaults == {}  # type: ignore[union-attr]


def test_operation_defaults_must_be_object(tmp_path: Path) -> None:
    bad = {**VALID_APP, "operations": [{**VALID_OP, "defaults": [1, 2]}]}
    with pytest.raises(RegistryError, match="defaults must be an object"):
        load_registry(_write(tmp_path, _registry([bad, FALLBACK_APP])))


def test_stats_has_module_defaults() -> None:
    """Stats Teacher needs a course module; a default one lets it answer plain questions (used
    instead of the web fallback)."""
    op = load_registry().get("stats-teacher").operation("ask_question")  # type: ignore[union-attr]
    assert op is not None
    assert op.defaults == {
        "module_id": 1,
        "module_title": "General Statistics",
        "module_part": "Overview",
    }


def test_stats_requires_module_context() -> None:
    """Stats Teacher answers within a specific module — those fields are marked required so the
    executor skips (not 422s) a free-form question that supplies no module."""
    op = load_registry().get("stats-teacher").operation("ask_question")  # type: ignore[union-attr]
    assert op is not None
    assert set(op.required_fields) == {"module_id", "module_title", "module_part"}


def test_coding_playground_is_rest_only() -> None:
    """Coding Playground's REST surface is kernel-control + datasets; it must NOT advertise running
    code (execution is WebSocket-only), so code tasks route to Simulated Learning instead."""
    cp = load_registry().get("coding-playground")
    assert cp is not None
    blob = " ".join((*cp.capabilities, *cp.example_tasks, cp.description)).lower()
    assert "execute python" not in blob
    assert "prototype" not in blob
    assert "train a model" not in blob
    assert any("dataset" in c.lower() for c in cp.capabilities)  # real capabilities kept
    assert any("kernel" in c.lower() for c in cp.capabilities)


def test_fallback_has_no_call_spec(tmp_path: Path) -> None:
    reg = load_registry(_write(tmp_path, _registry([VALID_APP, FALLBACK_APP])))
    fb = reg.get("web-search")
    assert fb is not None
    assert fb.base_url is None
    assert fb.operations == ()


def test_operation_defaults_retry_when_absent(tmp_path: Path) -> None:
    op_no_retry = _without(VALID_OP, "retry")
    app = {**VALID_APP, "operations": [op_no_retry]}
    reg = load_registry(_write(tmp_path, _registry([app, FALLBACK_APP])))
    op = reg.get("teach-me").operation("start_topic")  # type: ignore[union-attr]
    assert op is not None
    assert op.retry == RetrySpec()


def test_dataclass_to_dict() -> None:
    op = AppOperation(
        name="x",
        description="d",
        method="GET",
        path="/x",
        timeout_s=10,
        destructive=False,
        idempotency="supported",
    )
    d = op.to_dict()
    assert d["method"] == "GET"
    assert d["retry"] == {"transient_max": 2, "backoff_s": 3.0}
    assert d["request_fields"] == []


# --- completeness / exclusion rules ------------------------------------------


def test_non_fallback_requires_call_spec(tmp_path: Path) -> None:
    bad = {**VALID_APP, "operations": []}
    with pytest.raises(RegistryError, match="at least one operation"):
        load_registry(_write(tmp_path, _registry([bad, FALLBACK_APP])))


def test_non_fallback_requires_port(tmp_path: Path) -> None:
    with pytest.raises(RegistryError, match="must declare a 'port'"):
        load_registry(_write(tmp_path, _registry([_without(VALID_APP, "port"), FALLBACK_APP])))


def test_non_fallback_requires_health(tmp_path: Path) -> None:
    with pytest.raises(RegistryError, match="must declare a 'health'"):
        load_registry(_write(tmp_path, _registry([_without(VALID_APP, "health"), FALLBACK_APP])))


def test_fallback_must_not_declare_operations(tmp_path: Path) -> None:
    bad = {**FALLBACK_APP, "operations": [VALID_OP]}
    with pytest.raises(RegistryError, match="must not declare operations"):
        load_registry(_write(tmp_path, _registry([VALID_APP, bad])))


# --- operation-level schema errors -------------------------------------------


def test_operations_must_be_list(tmp_path: Path) -> None:
    bad = {**VALID_APP, "operations": {"nope": 1}}
    with pytest.raises(RegistryError, match="operations must be a list"):
        load_registry(_write(tmp_path, _registry([bad, FALLBACK_APP])))


def test_operation_must_be_object(tmp_path: Path) -> None:
    bad = {**VALID_APP, "operations": [5]}
    with pytest.raises(RegistryError, match="must be a JSON object"):
        load_registry(_write(tmp_path, _registry([bad, FALLBACK_APP])))


def test_operation_bad_method(tmp_path: Path) -> None:
    bad = {**VALID_APP, "operations": [{**VALID_OP, "method": "FETCH"}]}
    with pytest.raises(RegistryError, match="method must be one of"):
        load_registry(_write(tmp_path, _registry([bad, FALLBACK_APP])))


def test_operation_bad_idempotency(tmp_path: Path) -> None:
    bad = {**VALID_APP, "operations": [{**VALID_OP, "idempotency": "maybe"}]}
    with pytest.raises(RegistryError, match="idempotency must be one of"):
        load_registry(_write(tmp_path, _registry([bad, FALLBACK_APP])))


def test_operation_path_must_be_absolute(tmp_path: Path) -> None:
    bad = {**VALID_APP, "operations": [{**VALID_OP, "path": "topics"}]}
    with pytest.raises(RegistryError, match="path must start with"):
        load_registry(_write(tmp_path, _registry([bad, FALLBACK_APP])))


def test_operation_timeout_must_be_positive(tmp_path: Path) -> None:
    bad = {**VALID_APP, "operations": [{**VALID_OP, "timeout_s": 0}]}
    with pytest.raises(RegistryError, match="timeout_s must be > 0"):
        load_registry(_write(tmp_path, _registry([bad, FALLBACK_APP])))


def test_operation_timeout_must_be_number(tmp_path: Path) -> None:
    bad = {**VALID_APP, "operations": [{**VALID_OP, "timeout_s": "slow"}]}
    with pytest.raises(RegistryError, match="timeout_s must be a number"):
        load_registry(_write(tmp_path, _registry([bad, FALLBACK_APP])))


def test_operation_request_fields_must_be_string_list(tmp_path: Path) -> None:
    bad = {**VALID_APP, "operations": [{**VALID_OP, "request_fields": [1, 2]}]}
    with pytest.raises(RegistryError, match="request_fields must be a list of strings"):
        load_registry(_write(tmp_path, _registry([bad, FALLBACK_APP])))


def test_duplicate_operation_names(tmp_path: Path) -> None:
    bad = {**VALID_APP, "operations": [VALID_OP, VALID_OP]}
    with pytest.raises(RegistryError, match="operation names must be unique"):
        load_registry(_write(tmp_path, _registry([bad, FALLBACK_APP])))


def test_retry_must_be_object(tmp_path: Path) -> None:
    bad = {**VALID_APP, "operations": [{**VALID_OP, "retry": 5}]}
    with pytest.raises(RegistryError, match="retry must be an object"):
        load_registry(_write(tmp_path, _registry([bad, FALLBACK_APP])))


def test_retry_transient_max_negative(tmp_path: Path) -> None:
    bad = {**VALID_APP, "operations": [{**VALID_OP, "retry": {"transient_max": -1}}]}
    with pytest.raises(RegistryError, match="transient_max must be a non-negative"):
        load_registry(_write(tmp_path, _registry([bad, FALLBACK_APP])))


def test_retry_backoff_negative(tmp_path: Path) -> None:
    bad = {**VALID_APP, "operations": [{**VALID_OP, "retry": {"backoff_s": -0.5}}]}
    with pytest.raises(RegistryError, match="backoff_s must be a non-negative"):
        load_registry(_write(tmp_path, _registry([bad, FALLBACK_APP])))


# --- app-level call-spec field errors ----------------------------------------


def test_port_must_be_int(tmp_path: Path) -> None:
    with pytest.raises(RegistryError, match="port must be an integer"):
        load_registry(_write(tmp_path, _registry([{**VALID_APP, "port": "8008"}, FALLBACK_APP])))


def test_port_rejects_bool(tmp_path: Path) -> None:
    with pytest.raises(RegistryError, match="port must be an integer"):
        load_registry(_write(tmp_path, _registry([{**VALID_APP, "port": True}, FALLBACK_APP])))


def test_port_out_of_range(tmp_path: Path) -> None:
    with pytest.raises(RegistryError, match="port must be in"):
        load_registry(_write(tmp_path, _registry([{**VALID_APP, "port": 70000}, FALLBACK_APP])))


def test_health_must_be_absolute(tmp_path: Path) -> None:
    with pytest.raises(RegistryError, match="health must start with"):
        load_registry(
            _write(tmp_path, _registry([{**VALID_APP, "health": "health"}, FALLBACK_APP]))
        )


# --- error branches (pre-existing) -------------------------------------------


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(RegistryError, match="cannot read"):
        load_registry(tmp_path / "nope.json")


def test_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "apps.json"
    path.write_text("{not json")
    with pytest.raises(RegistryError, match="not valid JSON"):
        load_registry(path)


def test_root_not_object(tmp_path: Path) -> None:
    with pytest.raises(RegistryError, match="root must be a JSON object"):
        load_registry(_write(tmp_path, [1, 2, 3]))


def test_bad_schema_version(tmp_path: Path) -> None:
    with pytest.raises(RegistryError, match="schema_version"):
        load_registry(_write(tmp_path, {"schema_version": 2, "apps": [FALLBACK_APP]}))


def test_apps_not_list_or_empty(tmp_path: Path) -> None:
    with pytest.raises(RegistryError, match="non-empty list"):
        load_registry(_write(tmp_path, {"schema_version": 1, "apps": []}))


def test_app_not_object(tmp_path: Path) -> None:
    with pytest.raises(RegistryError, match="must be a JSON object"):
        load_registry(_write(tmp_path, _registry(["oops"])))


def test_app_missing_required_field(tmp_path: Path) -> None:
    with pytest.raises(RegistryError, match="missing a required field"):
        load_registry(_write(tmp_path, _registry([{"id": "x", "name": "X"}])))


def test_app_empty_string_field(tmp_path: Path) -> None:
    bad = {**VALID_APP, "name": "  "}
    with pytest.raises(RegistryError, match="non-empty string"):
        load_registry(_write(tmp_path, _registry([bad, FALLBACK_APP])))


def test_capabilities_must_be_string_list(tmp_path: Path) -> None:
    bad = {**VALID_APP, "capabilities": [1, 2]}
    with pytest.raises(RegistryError, match="capabilities must be a list of strings"):
        load_registry(_write(tmp_path, _registry([bad, FALLBACK_APP])))


def test_example_tasks_must_be_string_list(tmp_path: Path) -> None:
    bad = {**VALID_APP, "example_tasks": "nope"}
    with pytest.raises(RegistryError, match="example_tasks must be a list of strings"):
        load_registry(_write(tmp_path, _registry([bad, FALLBACK_APP])))


def test_duplicate_ids(tmp_path: Path) -> None:
    with pytest.raises(RegistryError, match="unique"):
        load_registry(_write(tmp_path, _registry([VALID_APP, VALID_APP, FALLBACK_APP])))


def test_no_fallback(tmp_path: Path) -> None:
    with pytest.raises(RegistryError, match="exactly one fallback"):
        load_registry(_write(tmp_path, _registry([VALID_APP])))


def test_two_fallbacks(tmp_path: Path) -> None:
    second = {**FALLBACK_APP, "id": "web-search-2"}
    with pytest.raises(RegistryError, match="exactly one fallback"):
        load_registry(_write(tmp_path, _registry([FALLBACK_APP, second])))


def test_fallback_id_raises_when_constructed_without_one() -> None:
    reg = Registry(apps=(AppEntry("a", "A", "d", (), (), False),))
    with pytest.raises(RegistryError, match="no fallback"):
        _ = reg.fallback_id
