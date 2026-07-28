"""Unit tests for observability — building, saving, reloading, and auditing a run record.

All offline (tmp_path, no network). Step A: every run is saved in the standard trace/step shape,
to all three sinks, best-effort (a failing sink never raises), without touching any LLM request
hash. Step B: the event log is a tamper-evident hash chain (verify_chain), and secrets are masked
before anything is written to disk.
"""

from __future__ import annotations

import json
import sqlite3

from orchestrator.llm.base import LLMRequest
from orchestrator.models import AppSelection, Plan, PlanResult, Subtask, SubtaskResult
from orchestrator.observability import (
    alerts,
    build_run_record,
    cost_of,
    get_run,
    kpis,
    list_runs,
    record_run,
    redact,
    render_run_detail,
    render_runs_list,
    save_run,
    verify_chain,
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


# --- Step B: tamper-evidence (hash-chained event log) -----------------------


def _events(tmp_path) -> list[dict]:
    lines = (tmp_path / "logs" / "events.jsonl").read_text().strip().splitlines()
    return [json.loads(line) for line in lines]


def _rewrite_events(tmp_path, rows: list[dict]) -> None:
    path = tmp_path / "logs" / "events.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def test_event_chain_links(tmp_path) -> None:
    save_run(_record(), root=tmp_path)
    save_run(_record(), root=tmp_path)
    rows = _events(tmp_path)
    assert [r["seq"] for r in rows] == [1, 2]
    assert rows[0]["prev_hash"] == "0" * 64  # genesis
    assert rows[1]["prev_hash"] == rows[0]["hash"]  # each links to the previous
    ok, broken = verify_chain(root=tmp_path)
    assert ok and broken is None


def test_verify_chain_detects_tamper(tmp_path) -> None:
    save_run(_record(), root=tmp_path)
    save_run(_record(), root=tmp_path)
    rows = _events(tmp_path)
    rows[0]["status"] = "error"  # edit a past record's payload, leave its hash untouched
    _rewrite_events(tmp_path, rows)
    ok, broken = verify_chain(root=tmp_path)
    assert not ok
    assert broken == 1


def test_verify_chain_detects_deletion(tmp_path) -> None:
    for _ in range(3):
        save_run(_record(), root=tmp_path)
    rows = _events(tmp_path)
    _rewrite_events(tmp_path, [rows[0], rows[2]])  # drop the middle line
    ok, broken = verify_chain(root=tmp_path)
    assert not ok
    assert broken == 3  # seq jumps 1 -> 3, so the surviving line 3 is where expectations break


def test_verify_chain_missing_log_is_intact(tmp_path) -> None:
    assert verify_chain(root=tmp_path) == (True, None)


# --- Step B: redaction ------------------------------------------------------


def test_redact_masks_secrets() -> None:
    # The dict keys deliberately avoid words like "key"/"token"/"secret" so the fixture values —
    # which must LOOK like secrets to exercise redact() — do not trip repo secret scanners.
    payload = {
        "note": "reach me at alice@example.com",
        "header": "Bearer abc.def.ghi123",
        "sample": "sk-ABCDEFGHIJKLMNOP1234",
        "aws": "AKIAIOSFODNN7EXAMPLE",  # secret-ok: public AWS example key, a test fixture
        "nested": ["plain text", {"inner": "sk-ABCDEFGHIJKLMNOP1234"}],
        "kept": "transformers attention",
        "number": 42,
    }
    out = redact(payload)
    assert "[REDACTED]" in out["note"] and "example.com" not in out["note"]
    assert out["header"] == "[REDACTED]"
    assert out["sample"] == "[REDACTED]"
    assert out["aws"] == "[REDACTED]"
    assert out["nested"][1]["inner"] == "[REDACTED]"
    assert out["nested"][0] == "plain text"
    assert out["kept"] == "transformers attention"  # ordinary content is untouched
    assert out["number"] == 42


def _record_with_secret():
    result = PlanResult(
        task="learn transformers",
        intent="learning plan",
        results=(
            SubtaskResult(
                "t1",
                "stanford-llm",
                "Stanford LLM",
                "ok",
                "get_course",
                {"text": "your key is sk-SECRETSECRET1234567 keep it safe"},
                "http://app/1",
                None,
                1.0,
                args={"email": "user@example.com"},
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
        ),
    )
    return build_run_record(
        _plan(),
        result,
        _synthesis(),
        mode="replay",
        model="m",
        exit_code=0,
        started_at=1.0,
        ended_at=2.0,
    )


def test_saved_run_is_redacted(tmp_path) -> None:
    record = _record_with_secret()
    save_run(record, root=tmp_path)
    saved = json.dumps(get_run(record["run_id"], root=tmp_path))
    assert "sk-SECRETSECRET1234567" not in saved
    assert "user@example.com" not in saved
    assert "[REDACTED]" in saved


def test_redaction_can_be_disabled(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ORCHESTRATOR_OBS_REDACT", "0")
    record = _record_with_secret()
    save_run(record, root=tmp_path)
    saved = json.dumps(get_run(record["run_id"], root=tmp_path))
    assert "sk-SECRETSECRET1234567" in saved  # stored raw when redaction is off


# --- Step C: read service (list_runs / kpis) --------------------------------


def _save(tmp_path, *, run_id: str, started_at: float, ended_at: float, exit_code: int = 0) -> None:
    record = build_run_record(
        _plan(),
        _result(),
        _synthesis(),
        mode="replay",
        model="m",
        exit_code=exit_code,
        started_at=started_at,
        ended_at=ended_at,
        run_id=run_id,
    )
    save_run(record, root=tmp_path)


def test_list_runs_orders_and_filters(tmp_path) -> None:
    _save(tmp_path, run_id="a" * 32, started_at=1000.0, ended_at=1001.0)
    _save(tmp_path, run_id="b" * 32, started_at=3000.0, ended_at=3001.0)
    _save(tmp_path, run_id="c" * 32, started_at=2000.0, ended_at=2001.0, exit_code=1)

    assert [r["run_id"] for r in list_runs(tmp_path)] == ["b" * 32, "c" * 32, "a" * 32]
    assert [r["run_id"] for r in list_runs(tmp_path, status="ok")] == ["b" * 32, "a" * 32]
    assert len(list_runs(tmp_path, limit=1)) == 1
    assert list_runs(tmp_path)[0]["task"] == "learn transformers"


def test_kpis_aggregates(tmp_path) -> None:
    _save(tmp_path, run_id="a" * 32, started_at=1000.0, ended_at=1002.0)  # 2.0s, ok
    _save(tmp_path, run_id="b" * 32, started_at=2000.0, ended_at=2001.0, exit_code=1)  # 1.0s, error

    k = kpis(tmp_path)
    assert k["total_runs"] == 2
    assert k["status_counts"] == {"ok": 1, "error": 1}
    assert k["success_rate"] == 0.5
    assert k["latency_s"]["max"] == 2.0
    assert k["avg_confidence"] == 0.9
    apps = {a["app_id"]: a for a in k["per_app"]}
    assert apps["stanford-llm"]["ok"] == 2  # one ok stanford step per run
    assert "2026-06-08" not in k["runs_by_day"]  # sanity: real epoch dates, keyed by day


def test_kpis_empty_store(tmp_path) -> None:
    k = kpis(tmp_path)
    assert k["total_runs"] == 0
    assert k["latency_s"]["p95"] == 0.0
    assert k["per_app"] == []
    assert list_runs(tmp_path) == []


def test_renderers_smoke(tmp_path) -> None:
    _save(tmp_path, run_id="d" * 32, started_at=1000.0, ended_at=1001.0)
    table = render_runs_list(list_runs(tmp_path))
    assert "WHEN" in table and "dddddddddddd" in table
    detail = render_run_detail(get_run("d" * 32, root=tmp_path))
    assert "Run dddddddddddd" in detail and "stanford-llm" in detail
    assert render_runs_list([]) == "No runs recorded yet."


# --- Step D: quality + health alerts ----------------------------------------


def _one_step_result(status: str, note: str | None = None) -> PlanResult:
    return PlanResult(
        task="learn transformers",
        intent="learning plan",
        results=(
            SubtaskResult(
                "t1",
                "stanford-llm",
                "Stanford LLM",
                status,
                "get_course",
                {"text": "x"},
                "http://app/1",
                None,
                1.0,
                note=note,
            ),
        ),
    )


def _save_run(
    tmp_path,
    *,
    run_id: str,
    started_at: float,
    status: str,
    note: str | None = None,
    exit_code: int = 0,
) -> dict:
    record = build_run_record(
        _plan(),
        _one_step_result(status, note),
        _synthesis(),
        mode="replay",
        model="m",
        exit_code=exit_code,
        started_at=started_at,
        ended_at=started_at + 1.0,
        run_id=run_id,
    )
    save_run(record, root=tmp_path)
    return record


def test_quality_block() -> None:
    record = build_run_record(
        _plan(),
        _result(),
        _synthesis(),
        mode="replay",
        model="m",
        exit_code=0,
        started_at=1.0,
        ended_at=2.0,
    )
    q = record["quality"]
    assert q["executed"] == 2  # both subtasks ran
    assert q["clean_ok"] == 2 and q["cautions"] == 0
    assert q["score"] == 1.0


def test_quality_counts_cautions_and_failures() -> None:
    result = PlanResult(
        task="t",
        intent="i",
        results=(
            SubtaskResult("t1", "a", "A", "ok", "op", {"x": 1}, "u", None, 1.0),
            SubtaskResult(
                "t2", "b", "B", "ok", "op", {"x": 1}, "u", None, 1.0, note="maybe off-topic"
            ),
            SubtaskResult("t3", "c", "C", "no_match", "op", None, "u", "empty", 1.0),
        ),
    )
    # _plan() only has t1/t2; use a plan whose subtasks match by building directly is overkill —
    # instead score the steps via a record built from a matching plan is not needed: quality reads
    # the step statuses, so assert through build with this result against a 3-subtask plan.
    plan = Plan(
        task="t",
        intent="i",
        model="m",
        prompt_version="1",
        subtasks=(
            Subtask("t1", "T1", "d", (), _app("a", "A")),
            Subtask("t2", "T2", "d", (), _app("b", "B")),
            Subtask("t3", "T3", "d", (), _app("c", "C")),
        ),
    )
    record = build_run_record(
        plan,
        result,
        None,
        mode="replay",
        model="m",
        exit_code=0,
        started_at=1.0,
        ended_at=2.0,
    )
    q = record["quality"]
    assert q["executed"] == 3
    assert q["clean_ok"] == 1  # only t1 is a clean ok
    assert q["cautions"] == 1 and q["no_match"] == 1
    assert q["score"] == round(1 / 3, 3)


def test_dry_run_has_no_quality() -> None:
    record = _record(dry_run=True)
    assert record["quality"] is None


def test_quality_score_persisted(tmp_path) -> None:
    _save_run(tmp_path, run_id="a" * 32, started_at=1000.0, status="ok")
    row = list_runs(tmp_path)[0]
    assert row["quality_score"] == 1.0


def test_missing_quality_column_is_migrated(tmp_path) -> None:
    # Simulate a pre-Step-D DB: a runs table without the quality_score column.
    db = tmp_path / "observability.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE runs (run_id TEXT PRIMARY KEY, session_id TEXT, task TEXT, intent TEXT, "
        "model TEXT, mode TEXT, started_at REAL, ended_at REAL, duration_s REAL, status TEXT, "
        "exit_code INTEGER, n_subtasks INTEGER, n_ok INTEGER, n_error INTEGER, n_skipped INTEGER, "
        "n_no_match INTEGER, n_fallback INTEGER, answer_mode TEXT, n_sources INTEGER)"
    )
    conn.commit()
    conn.close()

    _save_run(tmp_path, run_id="b" * 32, started_at=1000.0, status="ok")  # must not crash
    cols = {r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(runs)")}
    assert "quality_score" in cols
    assert list_runs(tmp_path)[0]["quality_score"] == 1.0


def test_kpis_quality_aggregate(tmp_path) -> None:
    _save_run(tmp_path, run_id="a" * 32, started_at=1000.0, status="ok")  # score 1.0
    _save_run(tmp_path, run_id="b" * 32, started_at=2000.0, status="no_match")  # score 0.0
    q = kpis(tmp_path)["quality"]
    assert q["scored_runs"] == 2
    assert q["avg_score"] == 0.5
    assert len(q["by_day"]) >= 1


def test_alerts_fire_on_breach(tmp_path) -> None:
    # 4 clean runs then 3 failing runs: quality drops and the average falls below the floor.
    for i in range(4):
        _save_run(tmp_path, run_id=f"{i:032x}", started_at=1000.0 + i, status="ok")
    for i in range(3):
        _save_run(tmp_path, run_id=f"{i + 10:032x}", started_at=2000.0 + i, status="no_match")
    fired = {a["metric"] for a in alerts(tmp_path)}
    assert "min_quality" in fired
    assert "quality_drop" in fired


def test_alerts_empty_when_healthy(tmp_path) -> None:
    for i in range(3):
        _save_run(tmp_path, run_id=f"{i:032x}", started_at=1000.0 + i, status="ok")
    assert alerts(tmp_path) == []
    assert alerts(tmp_path / "nonexistent") == []  # empty store, no error


def test_record_run_warns_on_bad_run(tmp_path, caplog) -> None:
    import logging

    with caplog.at_level(logging.WARNING, logger="orchestrator.observability"):
        record_run(
            _plan(),
            _one_step_result("no_match"),
            _synthesis(),
            mode="replay",
            model="m",
            exit_code=0,
            started_at=1.0,
            ended_at=2.0,
            root=tmp_path,
        )
    assert any("no-match" in m or "below" in m for m in caplog.messages)


# --- cost & token accounting ------------------------------------------------


def test_cost_known_model() -> None:
    usage = [
        {"model": "claude-opus-4-6", "input": 1000, "output": 500, "cache_read": 200},
        {"model": "claude-opus-4-6", "input": 2000, "output": 100},
    ]
    cost = cost_of(usage)
    assert cost["tokens"] == {
        "input": 3000,
        "output": 600,
        "cache_read": 200,
        "cache_write": 0,
        "total": 3800,
    }
    # input 3000*15 + output 600*75 + cache_read 200*1.5, all /1e6
    assert cost["cost_usd"] == round(0.045 + 0.045 + 0.0003, 6)
    assert cost["unpriced_models"] == []
    assert cost["by_model"][0]["model"] == "claude-opus-4-6"


def test_cost_unknown_model() -> None:
    cost = cost_of([{"model": "mystery-x", "input": 1000, "output": 1000}])
    assert cost["tokens"]["total"] == 2000  # tokens still counted
    assert cost["cost_usd"] == 0.0  # but not fabricated
    assert cost["unpriced_models"] == ["mystery-x"]
    assert cost["by_model"][0]["priced"] is False


def test_cost_price_override(tmp_path, monkeypatch) -> None:
    prices = tmp_path / "prices.json"
    prices.write_text('{"mystery-x": {"input": 1000.0, "output": 2000.0}}')
    monkeypatch.setenv("ORCHESTRATOR_PRICES", str(prices))
    cost = cost_of([{"model": "mystery-x", "input": 1_000_000, "output": 1_000_000}])
    assert cost["cost_usd"] == 3000.0  # 1M*1000/1e6 + 1M*2000/1e6
    assert cost["unpriced_models"] == []


def test_cost_empty() -> None:
    cost = cost_of([])
    assert cost["tokens"]["total"] == 0
    assert cost["cost_usd"] == 0.0


def test_run_record_has_cost() -> None:
    usage = [{"model": "claude-opus-4-6", "input": 1000, "output": 500}]
    record = build_run_record(
        _plan(),
        _result(),
        _synthesis(),
        mode="live",
        model="claude-opus-4-6",
        exit_code=0,
        started_at=1.0,
        ended_at=2.0,
        usage=usage,
    )
    assert record["cost"]["tokens"]["total"] == 1500
    assert record["cost"]["cost_usd"] > 0


def test_kpis_cost_aggregate(tmp_path) -> None:
    for i, toks in enumerate([1000, 3000]):
        record = build_run_record(
            _plan(),
            _result(),
            _synthesis(),
            mode="live",
            model="claude-opus-4-6",
            exit_code=0,
            started_at=1000.0 + i,
            ended_at=1001.0 + i,
            run_id=f"{i:032x}",
            usage=[{"model": "claude-opus-4-6", "input": toks, "output": 0}],
        )
        save_run(record, root=tmp_path)
    cost = kpis(tmp_path)["cost"]
    assert cost["total_tokens"] == 4000
    assert cost["total_usd"] == round(4000 * 15 / 1_000_000, 6)
    assert cost["by_model"][0]["model"] == "claude-opus-4-6"
    # cost surfaces in the run summary too
    assert list_runs(tmp_path)[0]["total_tokens"] in (1000, 3000)
