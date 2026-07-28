"""Unit tests for the CLI — output modes, exit codes, and wiring (no network)."""

from __future__ import annotations

import importlib
import json
from typing import Any

import pytest
from conftest import FakeLLM

from orchestrator.app_caller import CallResult
from orchestrator.cli import _readiness_note, main
from orchestrator.llm.base import LLMError, LLMRequest


@pytest.fixture(autouse=True)
def _stub_outset_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep --execute tests network-free: stub the outset app preflight as all-ready."""

    async def _all_ready(_apps: Any, _client: Any, **_kw: Any) -> dict[str, bool]:
        return {"arxiv-papers": True}

    monkeypatch.setattr("orchestrator.cli.start_all", _all_ready)


def test_readiness_note_branches() -> None:
    assert _readiness_note({}) == ""  # nothing to report
    assert _readiness_note({"a": True, "b": True}) == "Apps ready: 2/2"
    mixed = _readiness_note({"a": True, "b": False})
    assert "Apps ready: 1/2" in mixed
    assert "unavailable: b" in mixed


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
_RELEVANT_RESPONSE = '{"verdict": "PASS", "reason": "on topic"}'
# A structured (non-prose) single result is synthesized -> one final synthesis LLM call.
_SYNTHESIS_RESPONSE = "Recent work surveys mixture-of-experts routing."


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
    client = FakeLLM(
        [_arxiv_plan_response(), _SELECTOR_RESPONSE, _RELEVANT_RESPONSE, _SYNTHESIS_RESPONSE]
    )
    rc = main(["find moe papers", "--execute"], client=client)
    out = capsys.readouterr().out
    assert rc == 0
    assert "Apps ready: 1/1" in out  # the outset preflight reported readiness
    assert "Answer:" in out  # the grounded answer leads
    assert "Recent work surveys mixture-of-experts routing." in out
    assert "Plan — 1 subtask(s)" in out
    assert "ArXiv Paper Guide  (confidence 0.95)" in out
    assert "why: searches arxiv" in out
    assert "papers" in out  # real output shown
    assert "op=" not in out  # clean by default (no operational detail)
    assert "no apps were invoked" not in out  # NOT the dry-run banner


def test_execute_streams_answer_to_stdout(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The answer is streamed to stdout (via synthesize's on_delta) and NOT repeated by the render
    # block below it — so it appears exactly once.
    async def _call(app: Any, op: Any, _args: Any, **_kw: Any) -> CallResult:
        return CallResult(app.id, op.name, "http://x", True, 200, {"papers": ["s"]}, None, 0.5)

    monkeypatch.setattr("orchestrator.executor.call_operation", _call)
    client = FakeLLM(
        [_arxiv_plan_response(), _SELECTOR_RESPONSE, _RELEVANT_RESPONSE, _SYNTHESIS_RESPONSE]
    )
    rc = main(["find moe papers", "--execute"], client=client)
    out = capsys.readouterr().out
    assert rc == 0
    assert _SYNTHESIS_RESPONSE in out  # the streamed answer is present
    assert out.count(_SYNTHESIS_RESPONSE) == 1  # once only — not duplicated by the render block
    assert "Answer:" in out
    assert "Plan —" in out  # the supporting detail still renders below the answer


def test_execute_progress_goes_to_stderr(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Progress lines go to stderr so stdout stays clean (the answer / --json). The user still sees
    # live activity, but piping stdout is unaffected.
    async def _call(app: Any, op: Any, _args: Any, **_kw: Any) -> CallResult:
        return CallResult(app.id, op.name, "http://x", True, 200, {"papers": ["s"]}, None, 0.5)

    monkeypatch.setattr("orchestrator.executor.call_operation", _call)
    client = FakeLLM(
        [_arxiv_plan_response(), _SELECTOR_RESPONSE, _RELEVANT_RESPONSE, _SYNTHESIS_RESPONSE]
    )
    rc = main(["find moe papers", "--execute"], client=client)
    captured = capsys.readouterr()
    assert rc == 0
    assert "Starting apps" in captured.err  # progress on stderr
    assert "Find MoE papers" in captured.err  # per-subtask progress line (the subtask title)
    assert "Answer:" in captured.out  # the result still lands on stdout
    assert "Starting apps" not in captured.out  # progress does NOT pollute stdout


def test_execute_fallback_skipped(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # no search key -> the web fallback skips cleanly (and makes no network call in this test)
    monkeypatch.setattr("orchestrator.executor.resolve_search_key", lambda: None)
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
    # The web fallback itself could not run (no key) -> the Answer honestly says so (naming the
    # web-search app + the missing-key reason), with no synthesis LLM call.
    assert "Answer:" in out
    assert "could not be completed" in out
    assert "TAVILY_API_KEY" in out


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
    client = FakeLLM(
        [_arxiv_plan_response(), _SELECTOR_RESPONSE, _RELEVANT_RESPONSE, _SYNTHESIS_RESPONSE]
    )
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


def test_execute_selector_error_is_honest_not_web(capsys: pytest.CaptureFixture[str]) -> None:
    # A mid-execution selector LLM error is now handled HONESTLY per subtask: the chosen app is
    # reported as unable to complete the task — never silently answered from the web, and the run
    # does not crash. (Planner-stage LLM errors still exit 4: test_planner_failure_returns_4.)
    rc = main(["find moe papers", "--execute"], client=_PlanThenLLMError(_arxiv_plan_response()))
    out = capsys.readouterr().out
    assert rc == 0
    assert "could not be completed" in out
    assert "ArXiv Paper Guide" in out
    assert "Web Search" not in out  # no web substitution


# --- `orchestrator runs` command (Step C) -----------------------------------


def _seed_run(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> str:
    """Record one dry-run into tmp_path and return its run_id (no network; uses FakeLLM)."""
    from orchestrator.observability import list_runs

    monkeypatch.setenv("ORCHESTRATOR_OBS_ROOT", str(tmp_path))
    assert main(["learn transformers"], client=FakeLLM([_valid_response()])) == 0
    return list_runs(str(tmp_path))[0]["run_id"]


def test_runs_list_command(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rid = _seed_run(tmp_path, monkeypatch)
    capsys.readouterr()  # discard the seed run's output
    rc = main(["runs", "--root", str(tmp_path), "list"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "WHEN" in out
    assert rid[:12] in out


def test_runs_list_kpis(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _seed_run(tmp_path, monkeypatch)
    capsys.readouterr()
    rc = main(["runs", "--root", str(tmp_path), "list", "--kpis"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Runs" in out and "Latency" in out


def test_runs_show_command(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rid = _seed_run(tmp_path, monkeypatch)
    capsys.readouterr()
    rc = main(["runs", "--root", str(tmp_path), "show", rid])
    out = capsys.readouterr().out
    assert rc == 0
    assert f"Run {rid}" in out
    assert "Steps:" in out


def test_runs_show_unknown_id(tmp_path: Any, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["runs", "--root", str(tmp_path), "show", "deadbeef"])
    err = capsys.readouterr().err
    assert rc == 5
    assert "no run" in err


def test_runs_command_offline_empty(tmp_path: Any, capsys: pytest.CaptureFixture[str]) -> None:
    # No client, no registry, no network: an empty store lists cleanly.
    rc = main(["runs", "--root", str(tmp_path), "list"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "No runs recorded yet." in out


def test_runs_alerts_command(tmp_path: Any, capsys: pytest.CaptureFixture[str]) -> None:
    from orchestrator.models import AppSelection, Plan, PlanResult, Subtask, SubtaskResult
    from orchestrator.observability import build_run_record, save_run

    def _save(run_id: str, started_at: float, status: str) -> None:
        app = AppSelection(app_id="a", app_name="A", rationale="r", confidence=0.9, fallback=False)
        plan = Plan(
            task="t",
            intent="i",
            model="m",
            prompt_version="1",
            subtasks=(Subtask("t1", "T", "d", (), app),),
        )
        result = PlanResult(
            task="t",
            intent="i",
            results=(SubtaskResult("t1", "a", "A", status, "op", {"x": 1}, "u", None, 1.0),),
        )
        record = build_run_record(
            plan,
            result,
            None,
            mode="replay",
            model="m",
            exit_code=0,
            started_at=started_at,
            ended_at=started_at + 1.0,
            run_id=run_id,
        )
        save_run(record, root=str(tmp_path))

    # Empty store: no alerts.
    assert main(["runs", "--root", str(tmp_path), "alerts"]) == 0
    assert "No alerts" in capsys.readouterr().out

    # 4 clean then 3 no-match runs -> quality alerts fire.
    for i in range(4):
        _save(f"{i:032x}", 1000.0 + i, "ok")
    for i in range(3):
        _save(f"{i + 10:032x}", 2000.0 + i, "no_match")
    rc = main(["runs", "--root", str(tmp_path), "alerts"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "alert(s):" in out
    assert "quality" in out
