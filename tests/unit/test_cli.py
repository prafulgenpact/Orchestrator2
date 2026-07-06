"""Unit tests for the CLI — output modes, exit codes, and wiring (no network)."""

from __future__ import annotations

import importlib
import json

import pytest
from conftest import FakeLLM

from orchestrator.cli import main


def _valid_response() -> str:
    return json.dumps(
        {
            "intent": "build a learning plan",
            "subtasks": [
                {
                    "id": "t1",
                    "title": "Fundamentals",
                    "description": "attention basics",
                    "depends_on": [],
                    "app": {
                        "app_id": "stanford-llm",
                        "rationale": "course covers it",
                        "confidence": 0.9,
                    },
                }
            ],
        }
    )


def test_human_output_success(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["learn transformers"], client=FakeLLM([_valid_response()]))
    out = capsys.readouterr().out
    assert rc == 0
    assert "Intent: build a learning plan" in out
    assert "-> Stanford LLM Course" in out
    assert "no apps were invoked" in out


def test_json_output_success(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["learn transformers", "--json"], client=FakeLLM([_valid_response()]))
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)  # stdout is exactly one JSON document
    assert data["intent"] == "build a learning plan"
    assert data["subtasks"][0]["app"]["app_id"] == "stanford-llm"


def test_model_override_flows_into_plan(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["x", "--json", "--model", "custom-model"], client=FakeLLM([_valid_response()]))
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["model"] == "custom-model"


def test_registry_error_returns_3(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["x", "--registry", "/no/such/apps.json"], client=FakeLLM([_valid_response()]))
    assert rc == 3
    assert "error:" in capsys.readouterr().err


def test_planner_failure_returns_4(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["x"], client=FakeLLM(["bad", "bad", "bad"]))
    assert rc == 4
    assert "valid plan" in capsys.readouterr().err


def test_credential_error_returns_3(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for var in ("ANTHROPIC_FOUNDRY_API_KEY", "ANTHROPIC_FOUNDRY_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("ORCHESTRATOR_FALLBACK_ENV", "/no/such/.env")
    rc = main(["x", "--mode", "live"])  # no injected client -> real get_client path
    assert rc == 3
    assert "credentials" in capsys.readouterr().err


def test_max_retries_zero_single_attempt() -> None:
    client = FakeLLM(["bad"])
    assert main(["x", "--max-retries", "0"], client=client) == 4
    assert len(client.requests) == 1


def test_missing_task_is_usage_error() -> None:
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2


def test_entry_point_module_imports() -> None:
    # importing __main__ must not raise (guarded run block is skipped on import)
    assert importlib.import_module("orchestrator.__main__") is not None
