"""Unit tests for observability — building, saving, and reloading a run record.

All offline (tmp_path, no network). These prove Step A of the observability plan: every run is
saved in the standard trace/step shape, to all three sinks, best-effort (a failing sink never
raises), and without touching any LLM request hash.
"""

from __future__ import annotations

import json
import sqlite3

from orchestrator.llm.base import LLMRequest
from orchestrator.models import AppSelection, Plan, PlanResult, Subtask, SubtaskResult
from orchestrator.observability import (
    build_run_record,
    get_run,
    record_run,
    save_run,
)
from orchestrator.synthesis import Synthesis


def _app(
    app_id: str = "stanford-llm", name: str = "Stanford LLM", fb: bool = False
) -> AppSelection:
    return AppSelection(
        app_id=app_id, app_name=name, rationale="best fit", confidence=0.9, fallback=fb
    )


def _plan() -> Plan:
    subs = (
        Subtask("t1", "Learn basics", "desc-1", (), _app()),
        Subtask("t2", "Search web", "desc-2", ("t1",), _app("web-search", "Web Search", fb=True)),
    )
    return Plan(
        task="learn transformers",
        intent="learning plan",
        subtasks=subs,
        model="claude-opus-4-6",
        prompt_version="1",
    )


def _result() -> PlanResult:
    results = (
        SubtaskResult(
            "t1",
            "stanford-llm",
            "Stanford LLM",
            "ok",
            "get_course",
            {"text": "lesson"},
            "http://app/1",
            None,
            1.234,
            args={"topic": "transformers"},
        ),
        SubtaskResult(
            "t2",
            "web-search",
            "Web Search",
            "ok",
            "web_search",
            {"text": "web"},
            "http://web/2",
            None,
            0.5,
        ),
    )
    return PlanResult(task="learn transformers", intent="learning plan", results=results)


def _synthesis() -> Synthesis:
    return Synthesis(
        answer="Here is your plan.", mode="synthesized", sources=("http://app/1", "http://web/2")
    )


def _record(
    result: PlanResult | None = None,
    synthesis: Synthesis | None = None,
    *,
    dry_run: bool = False,
) -> dict:
    """Build a record from the standard fixtures. dry_run=True omits result + synthesis."""
    res = None if dry_run else (result or _result())
    syn = None if dry_run else (synthesis or _synthesis())
    return build_run_record(
        _plan(),
        res,
        syn,
        mode="replay",
        model="claude-opus-4-6",
        exit_code=0,
        started_at=1000.0,
        ended_at=1002.5,
    )


# --- AC1: record shape -------------------------------------------------------


def test_build_run_record_shape() -> None:
    record = _record()
    assert len(record["run_id"]) == 32
    int(record["run_id"], 16)  # valid hex
    assert record["task"] == "learn transformers"
    assert record["n_subtasks"] == 2
    assert record["duration_s"] == 2.5
    assert record["status"] == "ok"
    assert record["answer"]["mode"] == "synthesized"
    assert record["answer"]["n_sources"] == 2
    assert record["counts"]["ok"] == 2
    assert record["counts"]["fallback"] == 1

    step = record["steps"][0]
    assert len(step["step_id"]) == 16
    int(step["step_id"], 16)
    assert step["parent_id"] == record["run_id"]
    assert step["type"] == "execute"
    assert step["app_id"] == "stanford-llm"
    assert step["status"] == "ok"
    assert step["duration_s"] == 1.234
    assert step["input"] == {"topic": "transformers"}
    assert step["output"] == {"text": "lesson"}
    assert step["source"] == "http://app/1"
    assert step["routing"] == {"rationale": "best fit", "confidence": 0.9, "fallback": False}
    # the fallback-routed subtask is typed as a fallback step
    assert record["steps"][1]["type"] == "fallback"


def test_dry_run_record_has_planned_steps() -> None:
    record = _record(dry_run=True)
    assert record["answer"] is None
    assert all(s["status"] == "planned" for s in record["steps"])
    assert all(s["output"] is None for s in record["steps"])
    assert record["counts"]["planned"] == 2


# --- AC2: save + reload round-trip ------------------------------------------


def test_save_and_reload_round_trip(tmp_path) -> None:
    record = _record()
    save_run(record, root=tmp_path)
    rid = record["run_id"]

    # JSON file
    assert (tmp_path / "runs" / f"{rid}.json").exists()
    assert get_run(rid, root=tmp_path) == json.loads(json.dumps(record))

    # SQLite rows
    conn = sqlite3.connect(tmp_path / "observability.db")
    run_row = conn.execute(
        "SELECT task, status, n_subtasks FROM runs WHERE run_id=?", (rid,)
    ).fetchone()
    assert run_row == ("learn transformers", "ok", 2)
    n_steps = conn.execute("SELECT COUNT(*) FROM steps WHERE run_id=?", (rid,)).fetchone()[0]
    assert n_steps == 2
    conn.close()

    # event log line
    lines = (tmp_path / "logs" / "events.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["run_id"] == rid


def test_get_run_missing_returns_none(tmp_path) -> None:
    assert get_run("deadbeef", root=tmp_path) is None


# --- AC3: best-effort (a failing sink never raises) -------------------------


def test_save_run_swallows_disk_error(tmp_path) -> None:
    # Point the root at a *file*, so every sink's mkdir raises NotADirectoryError.
    blocked = tmp_path / "not-a-dir"
    blocked.write_text("x")
    save_run(_record(), root=blocked)  # must not raise


def test_record_run_disabled_writes_nothing(tmp_path) -> None:
    rid = record_run(
        _plan(),
        _result(),
        _synthesis(),
        mode="replay",
        model="m",
        exit_code=0,
        started_at=1.0,
        ended_at=2.0,
        root=tmp_path,
        enabled=False,
    )
    assert rid is None
    assert not (tmp_path / "runs").exists()
    assert not (tmp_path / "observability.db").exists()


def test_record_run_enabled_returns_id_and_saves(tmp_path) -> None:
    rid = record_run(
        _plan(),
        _result(),
        _synthesis(),
        mode="replay",
        model="m",
        exit_code=0,
        started_at=1.0,
        ended_at=2.0,
        root=tmp_path,
        enabled=True,
    )
    assert rid is not None
    assert get_run(rid, root=tmp_path) is not None


# --- AC4: recording does not touch any LLM request hash ---------------------


def test_recording_does_not_touch_request_hash(tmp_path) -> None:
    request = LLMRequest(model="m", system="sys", messages=({"role": "user", "content": "hi"},))
    before = json.dumps(request.to_dict(), sort_keys=True)
    record_run(
        _plan(),
        _result(),
        _synthesis(),
        mode="replay",
        model="m",
        exit_code=0,
        started_at=1.0,
        ended_at=2.0,
        root=tmp_path,
    )
    after = json.dumps(request.to_dict(), sort_keys=True)
    assert before == after
