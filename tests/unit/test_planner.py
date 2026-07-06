"""Unit tests for the planner — success, retry-on-invalid, and exhaustion."""

from __future__ import annotations

import json

import pytest
from conftest import FakeLLM

from orchestrator.planner import (
    PROMPT_VERSION,
    PlannerError,
    build_user_message,
    load_system_prompt,
    plan_task,
)
from orchestrator.registry import load_registry

REGISTRY = load_registry()


def _valid_response() -> str:
    return json.dumps(
        {
            "intent": "learn transformers over a week",
            "subtasks": [
                {
                    "id": "t1",
                    "title": "Fundamentals",
                    "description": "attention basics",
                    "depends_on": [],
                    "app": {
                        "app_id": "stanford-llm",
                        "rationale": "the CME 295 course covers this",
                        "confidence": 0.9,
                    },
                },
                {
                    "id": "t2",
                    "title": "Practice",
                    "description": "implement attention",
                    "depends_on": ["t1"],
                    "app": {
                        "app_id": "coding-playground",
                        "rationale": "persistent kernel for practice",
                        "confidence": 0.8,
                    },
                },
            ],
        }
    )


def test_load_system_prompt_mentions_json() -> None:
    prompt = load_system_prompt()
    assert "JSON" in prompt
    assert prompt.startswith("version:")


def test_build_user_message_includes_registry_and_task() -> None:
    msg = build_user_message(REGISTRY, "plan my week")
    assert "AVAILABLE APPS" in msg
    assert "stanford-llm" in msg
    assert "plan my week" in msg


def test_plan_task_success() -> None:
    client = FakeLLM([_valid_response()])
    plan = plan_task(client, REGISTRY, "learn transformers", model="claude-opus-4-6")
    assert plan.intent.startswith("learn transformers")
    assert plan.prompt_version == PROMPT_VERSION
    assert plan.model == "claude-opus-4-6"
    assert len(plan.subtasks) == 2
    # one request, carrying the system prompt and the user message
    assert len(client.requests) == 1
    assert client.requests[0].system == load_system_prompt()
    assert client.requests[0].model == "claude-opus-4-6"


def test_plan_task_retries_then_succeeds() -> None:
    client = FakeLLM(["not json at all", _valid_response()])
    plan = plan_task(client, REGISTRY, "learn transformers", model="m", max_retries=2)
    assert len(plan.subtasks) == 2
    # two attempts; the second request carries the correction conversation
    assert len(client.requests) == 2
    second = client.requests[1].messages
    assert len(second) == 3  # user, assistant(bad), user(correction)
    assert "was invalid" in second[2]["content"]


def test_plan_task_exhausts_retries() -> None:
    client = FakeLLM(["bad", "bad", "bad"])
    with pytest.raises(PlannerError, match="after 3 attempts"):
        plan_task(client, REGISTRY, "learn transformers", model="m", max_retries=2)
    assert len(client.requests) == 3


def test_plan_task_no_retries_budget() -> None:
    client = FakeLLM(["bad"])
    with pytest.raises(PlannerError, match="after 1 attempts"):
        plan_task(client, REGISTRY, "x", model="m", max_retries=0)
    assert len(client.requests) == 1
