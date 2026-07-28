"""Save every run so history, audit, and (later) a dashboard are possible.

Today a run prints an answer and is forgotten. This module captures each run in a standard
trace/step shape (a run is one trace; each subtask is a nested step — the shape Langfuse,
Arize Phoenix, and the OpenTelemetry GenAI conventions use), and writes it to three sinks:

* ``runs/<run_id>.json`` — the full-detail record (drill-down + audit source);
* ``observability.db`` — a SQLite summary row per run and per step (fast KPI queries);
* ``logs/events.jsonl`` — an append-only event line per run (the running audit trail).

Every write is BEST-EFFORT: recording must never change a run's answer or exit code, so a disk
or database failure is logged and swallowed, never raised. Nothing here touches the planner /
selector / judge, so LLM request hashes — and the recorded eval fixtures — are unaffected.

The reusable entry point is ``record_run(...)``: the CLI calls it today and a future UI backend
can call the same function unchanged.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from orchestrator.models import Plan, PlanResult
from orchestrator.synthesis import Synthesis

RUN_SCHEMA = "orchestrator.run/v1"

# Where runs/, logs/, and observability.db live. Defaults to the current directory (mirrors
# orchestrator-output/); override with ORCHESTRATOR_OBS_ROOT. All three are gitignored.
_ROOT_ENV = "ORCHESTRATOR_OBS_ROOT"

_log = logging.getLogger("orchestrator.observability")


# --- ids ---------------------------------------------------------------------


def new_run_id() -> str:
    """A 32-hex run id (W3C trace-id shape), so any OTel-aware tool understands it later."""
    return uuid.uuid4().hex


def _new_step_id() -> str:
    """A 16-hex step id (W3C span-id shape)."""
    return os.urandom(8).hex()


# --- record building ---------------------------------------------------------


def _resolve_root(root: str | os.PathLike[str] | None) -> Path:
    if root is not None:
        return Path(root)
    return Path(os.environ.get(_ROOT_ENV) or ".")


def _run_status(exit_code: int, steps: list[dict[str, Any]]) -> str:
    """Roll per-step outcomes into one run status: ``ok`` / ``partial`` / ``error``."""
    if exit_code != 0:
        return "error"
    if any(s["status"] in ("error", "no_match") for s in steps):
        return "partial"
    return "ok"


def _step_records(plan: Plan, result: PlanResult | None, run_id: str) -> list[dict[str, Any]]:
    """One step per subtask, joining the routing decision (Plan) with its outcome (PlanResult).

    On a dry run ``result`` is None, so steps carry the plan only (status ``planned``, no output).
    Routing rationale + confidence are kept on every step — the "why this app?" provenance an
    orchestrator needs — since the fields are already produced by the planner for free.
    """
    by_id = {r.subtask_id: r for r in result.results} if result is not None else {}
    steps: list[dict[str, Any]] = []
    for sub in plan.subtasks:
        outcome = by_id.get(sub.id)
        steps.append(
            {
                "step_id": _new_step_id(),
                "run_id": run_id,
                # flat under the run root for now; nesting grows in later steps
                "parent_id": run_id,
                "type": "fallback" if sub.app.fallback else "execute",
                "subtask_id": sub.id,
                "title": sub.title,
                "depends_on": list(sub.depends_on),
                "app_id": sub.app.app_id,
                "app_name": sub.app.app_name,
                "routing": {
                    "rationale": sub.app.rationale,
                    "confidence": sub.app.confidence,
                    "fallback": sub.app.fallback,
                },
                "operation": outcome.operation if outcome else None,
                "status": outcome.status if outcome else "planned",
                "duration_s": round(outcome.duration_s, 3) if outcome else 0.0,
                "input": outcome.args if outcome else None,
                "output": outcome.output if outcome else None,
                "error": outcome.error if outcome else None,
                "note": outcome.note if outcome else None,
                "source": outcome.source if outcome else None,
            }
        )
    return steps


def _counts(steps: list[dict[str, Any]]) -> dict[str, int]:
    keys = ("ok", "error", "skipped", "no_match", "planned")
    counts = {k: 0 for k in keys}
    for step in steps:
        counts[step["status"]] = counts.get(step["status"], 0) + 1
    counts["fallback"] = sum(1 for s in steps if s["routing"]["fallback"])
    return counts


def build_run_record(
    plan: Plan,
    result: PlanResult | None,
    synthesis: Synthesis | None,
    *,
    mode: str,
    model: str,
    exit_code: int,
    started_at: float,
    ended_at: float,
    run_id: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Assemble one run record in the standard trace/step shape from what the CLI already holds."""
    rid = run_id or new_run_id()
    steps = _step_records(plan, result, rid)
    counts = _counts(steps)
    answer = None
    if synthesis is not None:
        answer = {
            "mode": synthesis.mode,
            "sources": list(synthesis.sources),
            "n_sources": len(synthesis.sources),
        }
    return {
        "schema": RUN_SCHEMA,
        "run_id": rid,
        "session_id": session_id,
        "task": plan.task,
        "intent": plan.intent,
        "model": model,
        "mode": mode,
        "started_at": round(started_at, 3),
        "ended_at": round(ended_at, 3),
        "duration_s": round(ended_at - started_at, 3),
        "status": _run_status(exit_code, steps),
        "exit_code": exit_code,
        "n_subtasks": len(steps),
        "counts": counts,
        "answer": answer,
        "steps": steps,
    }


# --- persistence (best-effort) -----------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    session_id TEXT,
    task TEXT,
    intent TEXT,
    model TEXT,
    mode TEXT,
    started_at REAL,
    ended_at REAL,
    duration_s REAL,
    status TEXT,
    exit_code INTEGER,
    n_subtasks INTEGER,
    n_ok INTEGER,
    n_error INTEGER,
    n_skipped INTEGER,
    n_no_match INTEGER,
    n_fallback INTEGER,
    answer_mode TEXT,
    n_sources INTEGER
);
CREATE TABLE IF NOT EXISTS steps (
    step_id TEXT PRIMARY KEY,
    run_id TEXT,
    parent_id TEXT,
    type TEXT,
    subtask_id TEXT,
    app_id TEXT,
    app_name TEXT,
    operation TEXT,
    status TEXT,
    duration_s REAL,
    confidence REAL,
    has_error INTEGER
);
CREATE INDEX IF NOT EXISTS ix_steps_run ON steps(run_id);
"""


def _db_path(root: Path) -> Path:
    return root / "observability.db"


def _connect(root: Path) -> sqlite3.Connection:
    """Open observability.db under ``root``, creating the schema on first use."""
    root.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_db_path(root))
    conn.executescript(_DDL)
    return conn


def _insert_rows(record: dict[str, Any], root: Path) -> None:
    counts = record["counts"]
    answer = record["answer"] or {}
    conn = _connect(root)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO runs VALUES " "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                record["run_id"],
                record["session_id"],
                record["task"],
                record["intent"],
                record["model"],
                record["mode"],
                record["started_at"],
                record["ended_at"],
                record["duration_s"],
                record["status"],
                record["exit_code"],
                record["n_subtasks"],
                counts.get("ok", 0),
                counts.get("error", 0),
                counts.get("skipped", 0),
                counts.get("no_match", 0),
                counts.get("fallback", 0),
                answer.get("mode"),
                answer.get("n_sources"),
            ),
        )
        conn.execute("DELETE FROM steps WHERE run_id = ?", (record["run_id"],))
        conn.executemany(
            "INSERT OR REPLACE INTO steps VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    s["step_id"],
                    s["run_id"],
                    s["parent_id"],
                    s["type"],
                    s["subtask_id"],
                    s["app_id"],
                    s["app_name"],
                    s["operation"],
                    s["status"],
                    s["duration_s"],
                    s["routing"]["confidence"],
                    1 if s["error"] else 0,
                )
                for s in record["steps"]
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _write_json(record: dict[str, Any], root: Path) -> None:
    runs_dir = root / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    path = runs_dir / f"{record['run_id']}.json"
    path.write_text(json.dumps(record, indent=2, default=str))


def _append_event(record: dict[str, Any], root: Path) -> None:
    logs_dir = root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    event = {
        "run_id": record["run_id"],
        "task": record["task"],
        "status": record["status"],
        "exit_code": record["exit_code"],
        "duration_s": record["duration_s"],
        "n_subtasks": record["n_subtasks"],
        "ended_at": record["ended_at"],
    }
    with (logs_dir / "events.jsonl").open("a") as fh:
        fh.write(json.dumps(event, default=str) + "\n")


def save_run(record: dict[str, Any], *, root: str | os.PathLike[str] | None = None) -> None:
    """Write the record to all three sinks. Each is independent and best-effort: one failing sink
    is logged and skipped so the others still persist, and no failure ever reaches the caller."""
    base = _resolve_root(root)
    for name, sink in (("json", _write_json), ("sqlite", _insert_rows), ("events", _append_event)):
        try:
            sink(record, base)
        except Exception as exc:  # recording must never break a run
            _log.warning(
                "observability %s sink failed for run %s: %s", name, record.get("run_id"), exc
            )


def get_run(run_id: str, *, root: str | os.PathLike[str] | None = None) -> dict[str, Any] | None:
    """Reload a saved run's full JSON record, or None if it was never saved."""
    path = _resolve_root(root) / "runs" / f"{run_id}.json"
    if not path.exists():
        return None
    data: dict[str, Any] = json.loads(path.read_text())
    return data


# --- reusable entry point ----------------------------------------------------


def record_run(
    plan: Plan,
    result: PlanResult | None,
    synthesis: Synthesis | None,
    *,
    mode: str,
    model: str,
    exit_code: int,
    started_at: float,
    ended_at: float,
    run_id: str | None = None,
    session_id: str | None = None,
    root: str | os.PathLike[str] | None = None,
    enabled: bool = True,
) -> str | None:
    """Build and persist one run; return its run_id (or None when recording is disabled).

    The single entry point the CLI uses now and a future UI backend reuses unchanged. Best-effort:
    a build or save failure is swallowed so the caller's result and exit code are never affected.
    """
    if not enabled:
        return None
    try:
        record = build_run_record(
            plan,
            result,
            synthesis,
            mode=mode,
            model=model,
            exit_code=exit_code,
            started_at=started_at,
            ended_at=ended_at,
            run_id=run_id,
            session_id=session_id,
        )
    except Exception as exc:  # recording must never break a run
        _log.warning("observability could not build a run record: %s", exc)
        return None
    save_run(record, root=root)
    run_id_out: str = record["run_id"]
    return run_id_out
