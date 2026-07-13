"""Unit tests for the plan data model — construction, serialization, immutability."""

from __future__ import annotations

import dataclasses

import pytest

from orchestrator.models import (
    SCHEMA_VERSION,
    AppSelection,
    Plan,
    PlanResult,
    Subtask,
    SubtaskResult,
)


def _app() -> AppSelection:
    return AppSelection(
        app_id="stanford-llm",
        app_name="Stanford LLM Course",
        rationale="covers transformer fundamentals",
        confidence=0.92,
        fallback=False,
    )


def _plan() -> Plan:
    t1 = Subtask("t1", "Fundamentals", "learn the basics", (), _app())
    t2 = Subtask(
        "t2",
        "Practice",
        "hands-on",
        ("t1",),
        AppSelection("web-search", "Web Search (fallback)", "no app fits", 0.4, True),
    )
    return Plan(
        task="learn transformers",
        intent="build a learning plan",
        subtasks=(t1, t2),
        model="claude-opus-4-6",
        prompt_version="1",
    )


def test_app_selection_round_trip() -> None:
    app = _app()
    assert AppSelection.from_dict(app.to_dict()) == app


def test_subtask_round_trip_with_dependencies() -> None:
    sub = _plan().subtasks[1]
    restored = Subtask.from_dict(sub.to_dict())
    assert restored == sub
    assert restored.depends_on == ("t1",)


def test_subtask_from_dict_defaults_depends_on_to_empty() -> None:
    data = {
        "id": "t1",
        "title": "x",
        "description": "y",
        "app": _app().to_dict(),
    }
    assert Subtask.from_dict(data).depends_on == ()


def test_plan_round_trip_preserves_everything() -> None:
    plan = _plan()
    assert Plan.from_dict(plan.to_dict()) == plan


def test_plan_defaults_schema_version() -> None:
    plan = _plan()
    assert plan.schema_version == SCHEMA_VERSION
    data = plan.to_dict()
    del data["schema_version"]
    assert Plan.from_dict(data).schema_version == SCHEMA_VERSION


def test_plan_to_dict_shape() -> None:
    data = _plan().to_dict()
    assert data["task"] == "learn transformers"
    assert data["subtasks"][0]["app"]["app_id"] == "stanford-llm"
    assert data["subtasks"][1]["app"]["fallback"] is True


def test_models_are_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        _app().confidence = 0.1  # type: ignore[misc]


def test_from_dict_coerces_scalar_types() -> None:
    data = _app().to_dict()
    data["confidence"] = "0.5"  # string from loosely-typed JSON
    data["fallback"] = 1
    restored = AppSelection.from_dict(data)
    assert restored.confidence == 0.5
    assert restored.fallback is True


def _subtask_result(status: str = "ok") -> SubtaskResult:
    return SubtaskResult(
        subtask_id="t1",
        app_id="arxiv-papers",
        app_name="ArXiv Paper Guide",
        status=status,
        operation="search_papers_by_query",
        output={"papers": []},
        source="http://127.0.0.1:8002/api/papers/search",
        error=None,
        duration_s=1.2345,
    )


def test_subtask_result_to_dict_rounds_duration() -> None:
    d = _subtask_result().to_dict()
    assert d["app_id"] == "arxiv-papers"
    assert d["status"] == "ok"
    assert d["operation"] == "search_papers_by_query"
    assert d["duration_s"] == 1.234  # rounded to 3 dp


def test_subtask_result_note_in_to_dict() -> None:
    assert _subtask_result().to_dict()["note"] is None  # default: no note
    noted = SubtaskResult(
        subtask_id="t1",
        app_id="web-search",
        app_name="Web Search (fallback)",
        status="ok",
        operation="web_search",
        output={},
        source=None,
        error=None,
        duration_s=0.1,
        note="'Stats' could not handle this; used web",
    )
    assert noted.to_dict()["note"] == "'Stats' could not handle this; used web"


def test_plan_result_to_dict_nests_results() -> None:
    pr = PlanResult(task="t", intent="i", results=(_subtask_result("ok"), _subtask_result("error")))
    d = pr.to_dict()
    assert d["task"] == "t"
    assert [r["status"] for r in d["results"]] == ["ok", "error"]


def test_result_models_are_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        _subtask_result().status = "error"  # type: ignore[misc]
