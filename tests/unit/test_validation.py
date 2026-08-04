"""Unit tests for plan validation — happy path, schema errors, and graph errors."""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from orchestrator.registry import load_registry
from orchestrator.validation import PlanValidationError, parse_plan

REGISTRY = load_registry()
CTX = {"task": "learn transformers", "model": "claude-opus-4-6", "prompt_version": "1"}


def _payload() -> dict[str, Any]:
    return {
        "intent": "build a transformer learning plan",
        "subtasks": [
            {
                "id": "t1",
                "title": "Fundamentals",
                "description": "learn attention basics",
                "depends_on": [],
                "app": {
                    "app_id": "stanford-llm",
                    "rationale": "course covers it",
                    "confidence": 0.9,
                },
            },
            {
                "id": "t2",
                "title": "Practice",
                "description": "implement attention",
                "depends_on": ["t1"],
                "app": {"app_id": "coding-playground", "rationale": "kernel", "confidence": 0.8},
            },
        ],
    }


def _parse(payload: Any) -> Any:
    return parse_plan(json.dumps(payload), REGISTRY, **CTX)


# --- happy path --------------------------------------------------------------


def test_valid_plan_builds_and_denormalizes() -> None:
    plan = _parse(_payload())
    assert plan.task == "learn transformers"
    assert plan.model == "claude-opus-4-6"
    assert plan.intent.startswith("build")
    assert len(plan.subtasks) == 2
    # app_name/fallback come from the registry, not the model's JSON
    assert plan.subtasks[0].app.app_name == "Stanford LLM Course"
    assert plan.subtasks[0].app.fallback is False
    assert plan.subtasks[1].depends_on == ("t1",)


def test_fallback_flag_denormalized_from_registry() -> None:
    payload = _payload()
    payload["subtasks"][1]["app"]["app_id"] = "web-search"
    plan = _parse(payload)
    assert plan.subtasks[1].app.fallback is True
    assert plan.subtasks[1].app.app_name == "Web Search (fallback)"


def test_markdown_fences_are_stripped() -> None:
    fenced = "```json\n" + json.dumps(_payload()) + "\n```"
    plan = parse_plan(fenced, REGISTRY, **CTX)
    assert len(plan.subtasks) == 2


def test_bare_fences_are_stripped() -> None:
    fenced = "```\n" + json.dumps(_payload()) + "\n```"
    assert len(parse_plan(fenced, REGISTRY, **CTX).subtasks) == 2


def test_opening_fence_without_closing_still_parses() -> None:
    fenced = "```json\n" + json.dumps(_payload())  # no trailing fence
    assert len(parse_plan(fenced, REGISTRY, **CTX).subtasks) == 2


def test_confidence_accepts_string_number() -> None:
    payload = _payload()
    payload["subtasks"][0]["app"]["confidence"] = "0.55"
    assert _parse(payload).subtasks[0].app.confidence == 0.55


# --- JSON / structure errors -------------------------------------------------


def test_not_json() -> None:
    with pytest.raises(PlanValidationError, match="not valid JSON"):
        parse_plan("this is not json", REGISTRY, **CTX)


def test_not_object() -> None:
    with pytest.raises(PlanValidationError, match="must be a JSON object"):
        parse_plan("[1, 2, 3]", REGISTRY, **CTX)


def test_intent_missing() -> None:
    payload = _payload()
    del payload["intent"]
    with pytest.raises(PlanValidationError, match="intent must be"):
        _parse(payload)


def test_subtasks_not_list_or_empty() -> None:
    payload = _payload()
    payload["subtasks"] = []
    with pytest.raises(PlanValidationError, match="subtasks must be a non-empty list"):
        _parse(payload)


def test_subtask_not_object() -> None:
    payload = _payload()
    payload["subtasks"][0] = "oops"
    with pytest.raises(PlanValidationError, match="must be an object"):
        _parse(payload)


def test_subtask_id_missing() -> None:
    payload = _payload()
    del payload["subtasks"][0]["id"]
    with pytest.raises(PlanValidationError, match="id must be"):
        _parse(payload)


def test_subtask_title_empty() -> None:
    payload = _payload()
    payload["subtasks"][0]["title"] = ""
    with pytest.raises(PlanValidationError, match="title must be"):
        _parse(payload)


def test_subtask_description_missing() -> None:
    payload = _payload()
    del payload["subtasks"][0]["description"]
    with pytest.raises(PlanValidationError, match="description must be"):
        _parse(payload)


def test_depends_on_not_string_list() -> None:
    payload = _payload()
    payload["subtasks"][0]["depends_on"] = [1, 2]
    with pytest.raises(PlanValidationError, match="depends_on must be a list"):
        _parse(payload)


# --- app selection errors ----------------------------------------------------


def test_app_not_object() -> None:
    payload = _payload()
    payload["subtasks"][0]["app"] = "stanford-llm"
    with pytest.raises(PlanValidationError, match="'app' must be an object"):
        _parse(payload)


def test_unknown_app_id() -> None:
    payload = _payload()
    payload["subtasks"][0]["app"]["app_id"] = "made-up-app"
    with pytest.raises(PlanValidationError, match="unknown app_id"):
        _parse(payload)


def test_rationale_empty() -> None:
    payload = _payload()
    payload["subtasks"][0]["app"]["rationale"] = "  "
    with pytest.raises(PlanValidationError, match="rationale must be"):
        _parse(payload)


def test_confidence_not_number() -> None:
    payload = _payload()
    payload["subtasks"][0]["app"]["confidence"] = "high"
    with pytest.raises(PlanValidationError, match="confidence must be a number"):
        _parse(payload)


def test_confidence_out_of_range() -> None:
    payload = _payload()
    payload["subtasks"][0]["app"]["confidence"] = 1.5
    with pytest.raises(PlanValidationError, match=r"confidence must be in \[0, 1\]"):
        _parse(payload)


# --- graph errors ------------------------------------------------------------


def test_duplicate_ids() -> None:
    payload = _payload()
    payload["subtasks"][1]["id"] = "t1"
    payload["subtasks"][1]["depends_on"] = []
    with pytest.raises(PlanValidationError, match="ids must be unique"):
        _parse(payload)


def test_dangling_dependency() -> None:
    payload = _payload()
    payload["subtasks"][1]["depends_on"] = ["nope"]
    with pytest.raises(PlanValidationError, match="depends on unknown id"):
        _parse(payload)


def test_cycle_detected() -> None:
    payload = _payload()
    payload["subtasks"][0]["depends_on"] = ["t2"]  # t1<->t2 cycle
    with pytest.raises(PlanValidationError, match="cycle"):
        _parse(payload)


def test_deep_copy_isolation() -> None:
    # sanity: the builder returns a fresh dict each time (tests don't leak state)
    assert _payload() is not _payload()
    assert copy.deepcopy(_payload()) == _payload()


# --- fix 5: collapse exact-duplicate subtasks -------------------------------

from orchestrator.validation import _dedupe_subtasks, _norm_title  # noqa: E402


def _dup_payload() -> dict[str, Any]:
    a = {"app_id": "arxiv-papers", "rationale": "search", "confidence": 0.9}
    return {
        "intent": "find and summarize papers",
        "subtasks": [
            {
                "id": "t1",
                "title": "Find research papers on X",
                "description": "d",
                "depends_on": [],
                "app": a,
            },
            # exact duplicate of t1 (case + trailing punctuation differ)
            {
                "id": "t2",
                "title": "find research papers on x.",
                "description": "d2",
                "depends_on": [],
                "app": a,
            },
            {
                "id": "t3",
                "title": "Summarize the papers",
                "description": "d3",
                "depends_on": ["t2"],
                "app": a,
            },
        ],
    }


def test_parse_plan_collapses_duplicate_subtasks() -> None:
    plan = _parse(_dup_payload())
    ids = [s.id for s in plan.subtasks]
    assert ids == ["t1", "t3"]  # the duplicate t2 was dropped
    t3 = next(s for s in plan.subtasks if s.id == "t3")
    assert t3.depends_on == (
        "t1",
    )  # its dependency on the dropped twin was rewired to the kept one


def test_parse_plan_keeps_distinct_subtasks() -> None:
    plan = _parse(_payload())
    assert len(plan.subtasks) == 2  # different apps/titles -> untouched


def test_norm_title_normalizes_case_space_punct() -> None:
    assert _norm_title("  Find   Papers on X. ") == "find papers on x"
    assert _norm_title("Summarize!!!") == "summarize"


def test_dedupe_is_noop_without_duplicates() -> None:
    plan = _parse(_payload())  # already parsed distinct plan
    assert _dedupe_subtasks(plan.subtasks) is plan.subtasks


def test_dedupe_different_app_same_title_not_merged() -> None:
    from orchestrator.models import AppSelection, Subtask

    def s(i: str, app: str) -> Subtask:
        return Subtask(i, "Do the thing", "d", (), AppSelection(app, "A", "r", 0.9, False))

    subs = (s("t1", "arxiv-papers"), s("t2", "teach-me"))
    assert len(_dedupe_subtasks(subs)) == 2  # same title but different app -> kept separate
