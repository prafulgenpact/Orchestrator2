"""Unit tests for the CLI — output modes, exit codes, and wiring (no network)."""

from __future__ import annotations

import importlib
import json
from typing import Any

import pytest
from conftest import FakeLLM

from orchestrator.app_caller import CallResult
from orchestrator.cli import main
from orchestrator.llm.base import LLMError, LLMRequest


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


# --- --execute (real invocation path; HTTP call stubbed, no network) ---------


def _arxiv_plan_response() -> str:
    return json.dumps(
        {
            "intent": "find MoE papers",
            "subtasks": [
                {
                    "id": "t1",
                    "title": "Find MoE papers",
                    "description": "recent moe",
                    "depends_on": [],
                    "app": {
                        "app_id": "arxiv-papers",
                        "rationale": "searches arxiv",
                        "confidence": 0.95,
                    },
                }
            ],
        }
    )


_SELECTOR_RESPONSE = '{"operation": "search_papers_by_query", "arguments": {"query": "moe"}}'
_RELEVANT_RESPONSE = '{"relevant": true, "reason": "on topic"}'


def test_execute_success(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def _call(app: Any, op: Any, _args: Any, **_kw: Any) -> CallResult:
        return CallResult(
            app.id,
            op.name,
            "http://127.0.0.1:8002/api/papers/search",
            True,
            200,
            {"papers": ["MoE survey"]},
            None,
            0.5,
        )

    monkeypatch.setattr("orchestrator.executor.call_operation", _call)
    client = FakeLLM([_arxiv_plan_response(), _SELECTOR_RESPONSE, _RELEVANT_RESPONSE])
    rc = main(["find moe papers", "--execute"], client=client)
    out = capsys.readouterr().out
    assert rc == 0
    assert "Plan — 1 subtask(s)" in out
    assert "ArXiv Paper Guide  (confidence 0.95)" in out
    assert "why: searches arxiv" in out
    assert "papers" in out  # real output shown
    assert "op=" not in out  # clean by default (no operational detail)
    assert "no apps were invoked" not in out  # NOT the dry-run banner


def test_execute_fallback_skipped(capsys: pytest.CaptureFixture[str]) -> None:
    resp = json.dumps(
        {
            "intent": "obscure",
            "subtasks": [
                {
                    "id": "t1",
                    "title": "do it",
                    "description": "no app fits",
                    "depends_on": [],
                    "app": {
                        "app_id": "web-search",
                        "rationale": "no specialized app",
                        "confidence": 0.4,
                    },
                }
            ],
        }
    )
    rc = main(["something obscure", "--execute"], client=FakeLLM([resp]))
    out = capsys.readouterr().out
    assert rc == 0
    assert "Web Search (fallback)" in out
    assert "not executed" in out


def test_execute_verbose_shows_operational_detail(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def _call(app: Any, op: Any, _args: Any, **_kw: Any) -> CallResult:
        return CallResult(
            app.id,
            op.name,
            "http://127.0.0.1:8002/api/papers/search",
            True,
            200,
            {"papers": []},
            None,
            0.5,
        )

    monkeypatch.setattr("orchestrator.executor.call_operation", _call)
    client = FakeLLM([_arxiv_plan_response(), _SELECTOR_RESPONSE, _RELEVANT_RESPONSE])
    rc = main(["find moe papers", "--execute", "--verbose"], client=client)
    out = capsys.readouterr().out
    assert rc == 0
    assert "op=search_papers_by_query" in out
    assert "status=ok" in out


class _PlanThenLLMError:
    """Returns a valid plan on the first call, then fails (simulates a mid-execution LLM error)."""

    def __init__(self, planner_response: str) -> None:
        self._planner = planner_response
        self._calls = 0

    def complete(self, _request: LLMRequest) -> str:
        self._calls += 1
        if self._calls == 1:
            return self._planner
        raise LLMError("selector call failed")


def test_execute_llm_error_returns_4(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["find moe papers", "--execute"], client=_PlanThenLLMError(_arxiv_plan_response()))
    assert rc == 4
    assert "error:" in capsys.readouterr().err
