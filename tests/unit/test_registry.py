"""Unit tests for the app registry loader — real file load plus every error branch."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from orchestrator.registry import (
    AppEntry,
    Registry,
    RegistryError,
    load_registry,
)

VALID_APP = {
    "id": "teach-me",
    "name": "Teach Me",
    "description": "first-principles learning",
    "capabilities": ["start a topic"],
    "example_tasks": ["teach me X"],
    "fallback": False,
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


# --- error branches ----------------------------------------------------------


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
