"""Save every run so history, audit, and (later) a dashboard are possible.

Today a run prints an answer and is forgotten. This module captures each run in a standard
trace/step shape (a run is one trace; each subtask is a nested step — the shape Langfuse,
Arize Phoenix, and the OpenTelemetry GenAI conventions use), and writes it to three sinks:

* ``runs/<run_id>.json`` — the full-detail record (drill-down + audit source);
* ``observability.db`` — a SQLite summary row per run and per step (fast KPI queries);
* ``logs/events.jsonl`` — an append-only, hash-chained event line per run (a tamper-evident
  audit trail; ``verify_chain`` detects any edit or deletion of a past record).

Secrets (API keys, bearer tokens, emails) are masked by ``redact`` before anything is written, so
run data can be kept without storing credentials (disable with ``ORCHESTRATOR_OBS_REDACT=0``).

Every write is BEST-EFFORT: recording must never change a run's answer or exit code, so a disk
or database failure is logged and swallowed, never raised. Nothing here touches the planner /
selector / judge, so LLM request hashes — and the recorded eval fixtures — are unaffected.

The reusable entry point is ``record_run(...)``: the CLI calls it today and a future UI backend
can call the same function unchanged.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
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


def _quality(steps: list[dict[str, Any]]) -> dict[str, Any] | None:
    """A per-run quality score derived from what executed — no LLM/executor change needed.

    ``score`` = clean-ok steps / executed steps, where a *clean* ok step returned data and was NOT
    flagged by the advisory relevance judge (it carries no caution ``note``). None for a dry run
    (nothing executed), so planned-only runs don't drag the quality average down."""
    executed = [s for s in steps if s["status"] != "planned"]
    if not executed:
        return None
    clean_ok = sum(1 for s in executed if s["status"] == "ok" and not s.get("note"))
    return {
        "score": round(clean_ok / len(executed), 3),
        "executed": len(executed),
        "clean_ok": clean_ok,
        "cautions": sum(1 for s in executed if s["status"] == "ok" and s.get("note")),
        "no_match": sum(1 for s in executed if s["status"] == "no_match"),
        "errors": sum(1 for s in executed if s["status"] == "error"),
    }


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
        "quality": _quality(steps),
        "answer": answer,
        "steps": steps,
    }


# --- redaction ---------------------------------------------------------------

_REDACT_ENV = "ORCHESTRATOR_OBS_REDACT"
_REDACTED = "[REDACTED]"
# A conservative pack — high-precision secret shapes only, so ordinary run content is left intact.
_SECRET_PATTERNS = (
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),  # email address
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),  # OpenAI / Anthropic-style API key
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key id
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+"),  # bearer token
)


def _redaction_enabled() -> bool:
    """Redaction is on unless ORCHESTRATOR_OBS_REDACT is set to a falsey value."""
    return (os.environ.get(_REDACT_ENV) or "1").lower() not in ("0", "false", "no")


def _redact_str(text: str) -> str:
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(_REDACTED, text)
    return text


def redact(value: Any) -> Any:
    """Recursively mask secrets (emails, API keys, bearer tokens) in a JSON-like value.

    Only string leaves are scanned; numbers, bools, and None pass through. Applied before a run is
    written to disk so a credential embedded in an app's output or args is never persisted."""
    if isinstance(value, str):
        return _redact_str(value)
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [redact(item) for item in value]
    return value


# --- tamper-evidence (hash-chained event log) --------------------------------

_GENESIS_HASH = "0" * 64
_CHAIN_FIELDS = ("seq", "prev_hash", "hash")


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _chain_hash(prev_hash: str, seq: int, payload: dict[str, Any]) -> str:
    """This link's hash = sha256(prev_hash + seq + canonical(payload)). Editing any past payload
    (or its seq/order) changes every downstream hash, so tampering is detectable."""
    material = f"{prev_hash}{seq}{_canonical(payload)}".encode()
    return hashlib.sha256(material).hexdigest()


def _last_chain_link(path: Path) -> tuple[int, str]:
    """(seq, hash) of the last event line, or (0, genesis) when the log is empty or missing."""
    if not path.exists():
        return 0, _GENESIS_HASH
    last: str | None = None
    with path.open() as fh:
        for raw in fh:
            stripped = raw.strip()
            if stripped:
                last = stripped
    if last is None:
        return 0, _GENESIS_HASH
    row = json.loads(last)
    return int(row["seq"]), str(row["hash"])


def verify_chain(root: str | os.PathLike[str] | None = None) -> tuple[bool, int | None]:
    """Check the event log's hash chain.

    Returns ``(True, None)`` when the whole log verifies, else ``(False, seq)`` at the first line
    whose sequence, prev-link, or recomputed hash does not match — i.e. an edited or deleted past
    record. (Truncating the newest lines off the tail is not detectable without a separate anchor.)
    """
    path = _resolve_root(root) / "logs" / "events.jsonl"
    if not path.exists():
        return True, None
    prev_hash = _GENESIS_HASH
    expected_seq = 1
    with path.open() as fh:
        for raw in fh:
            stripped = raw.strip()
            if not stripped:
                continue
            row = json.loads(stripped)
            payload = {k: v for k, v in row.items() if k not in _CHAIN_FIELDS}
            seq = int(row.get("seq", -1))
            if seq != expected_seq or row.get("prev_hash") != prev_hash:
                return False, seq
            if row.get("hash") != _chain_hash(prev_hash, seq, payload):
                return False, seq
            prev_hash = str(row["hash"])
            expected_seq += 1
    return True, None


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
    n_sources INTEGER,
    quality_score REAL
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


# Columns added after the initial schema shipped — applied to pre-existing local DBs on open so an
# older observability.db is migrated forward instead of failing the insert. (table, column, type)
_ADDED_COLUMNS = (("runs", "quality_score", "REAL"),)


def _connect(root: Path) -> sqlite3.Connection:
    """Open observability.db under ``root``, creating the schema (and migrating it) on first use."""
    root.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_db_path(root))
    conn.executescript(_DDL)
    for table, column, coltype in _ADDED_COLUMNS:
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
    conn.commit()
    return conn


def _insert_rows(record: dict[str, Any], root: Path) -> None:
    counts = record["counts"]
    answer = record["answer"] or {}
    quality = record.get("quality") or {}
    conn = _connect(root)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
                quality.get("score"),
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
    """Append one hash-chained event line, linked to the previous line (genesis if the log is new).

    A single line, so the whole run isn't duplicated here — the full record lives in runs/<id>.json;
    this log is the tamper-evident index of what ran and when."""
    logs_dir = root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    path = logs_dir / "events.jsonl"
    payload = {
        "run_id": record["run_id"],
        "task": record["task"],
        "status": record["status"],
        "exit_code": record["exit_code"],
        "duration_s": record["duration_s"],
        "n_subtasks": record["n_subtasks"],
        "ended_at": record["ended_at"],
    }
    prev_seq, prev_hash = _last_chain_link(path)
    seq = prev_seq + 1
    line = {
        "seq": seq,
        "prev_hash": prev_hash,
        "hash": _chain_hash(prev_hash, seq, payload),
        **payload,
    }
    with path.open("a") as fh:
        fh.write(json.dumps(line, default=str) + "\n")


def save_run(record: dict[str, Any], *, root: str | os.PathLike[str] | None = None) -> None:
    """Write the record to all three sinks. Each is independent and best-effort: one failing sink
    is logged and skipped so the others still persist, and no failure ever reaches the caller."""
    base = _resolve_root(root)
    payload = redact(record) if _redaction_enabled() else record
    for name, sink in (("json", _write_json), ("sqlite", _insert_rows), ("events", _append_event)):
        try:
            sink(payload, base)
        except Exception as exc:  # recording must never break a run
            _log.warning(
                "observability %s sink failed for run %s: %s", name, payload.get("run_id"), exc
            )


def get_run(run_id: str, *, root: str | os.PathLike[str] | None = None) -> dict[str, Any] | None:
    """Reload a saved run's full JSON record, or None if it was never saved."""
    path = _resolve_root(root) / "runs" / f"{run_id}.json"
    if not path.exists():
        return None
    data: dict[str, Any] = json.loads(path.read_text())
    return data


# --- read service (UI-agnostic; the CLI now and a future dashboard both bind to this) ---

_RUN_SUMMARY_COLS = (
    "run_id",
    "started_at",
    "task",
    "status",
    "exit_code",
    "duration_s",
    "n_subtasks",
    "quality_score",
    "model",
    "mode",
)


def _open_db(root: str | os.PathLike[str] | None) -> sqlite3.Connection | None:
    """Open the store read-only-ish, or None if it was never created."""
    path = _db_path(_resolve_root(root))
    if not path.exists():
        return None
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def list_runs(
    root: str | os.PathLike[str] | None = None,
    *,
    limit: int = 20,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """Recent runs as summary dicts, newest first. Empty list when nothing has been saved yet."""
    conn = _open_db(root)
    if conn is None:
        return []
    try:
        sql = f"SELECT {', '.join(_RUN_SUMMARY_COLS)} FROM runs"
        params: list[Any] = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)
        return [dict(row) for row in conn.execute(sql, params)]
    finally:
        conn.close()


def _percentile(values: list[float], q: float) -> float:
    """Linear-interpolated q-quantile (q in [0,1]); 0.0 for an empty list."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 3)
    pos = (len(ordered) - 1) * q
    low = int(pos)
    high = min(low + 1, len(ordered) - 1)
    interp = ordered[low] + (ordered[high] - ordered[low]) * (pos - low)
    return round(interp, 3)


def _empty_kpis() -> dict[str, Any]:
    return {
        "total_runs": 0,
        "success_rate": 0.0,
        "status_counts": {},
        "latency_s": {"p50": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0},
        "per_app": [],
        "avg_confidence": 0.0,
        "fallback_rate": 0.0,
        "no_match_rate": 0.0,
        "quality": {"avg_score": None, "scored_runs": 0, "by_day": {}},
        "runs_by_day": {},
    }


def _quality_aggregate(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Average quality overall and per day, over runs that executed (score is not None)."""
    scored = [(r["started_at"], r["quality_score"]) for r in runs if r["quality_score"] is not None]
    if not scored:
        return {"avg_score": None, "scored_runs": 0, "by_day": {}}
    by_day: dict[str, list[float]] = {}
    for started_at, score in scored:
        if started_at is not None:
            by_day.setdefault(_day(started_at), []).append(score)
    return {
        "avg_score": round(sum(s for _, s in scored) / len(scored), 3),
        "scored_runs": len(scored),
        "by_day": {day: round(sum(v) / len(v), 3) for day, v in sorted(by_day.items())},
    }


def _day(epoch: float) -> str:
    """UTC date (YYYY-MM-DD) for a run's start time — the bucket key for runs-per-day."""
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d")


def _per_app(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    apps: dict[str, dict[str, Any]] = {}
    for step in steps:
        bucket = apps.setdefault(
            step["app_id"],
            {"app_id": step["app_id"], "calls": 0, "ok": 0, "error": 0, "no_match": 0, "_dur": 0.0},
        )
        bucket["calls"] += 1
        bucket["_dur"] += step["duration_s"] or 0.0
        if step["status"] in ("ok", "error", "no_match"):
            bucket[step["status"]] += 1
    rows = []
    for bucket in sorted(apps.values(), key=lambda b: b["calls"], reverse=True):
        calls = bucket["calls"]
        rows.append(
            {
                "app_id": bucket["app_id"],
                "calls": calls,
                "ok": bucket["ok"],
                "error": bucket["error"],
                "no_match": bucket["no_match"],
                "avg_duration_s": round(bucket["_dur"] / calls, 3) if calls else 0.0,
            }
        )
    return rows


def kpis(root: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Aggregate the whole store into headline KPIs. An empty store returns zeros, not an error.

    Reads the SQLite summary tables (never scans the JSON files), so it stays fast as history grows.
    Cost/token KPIs are added once token capture lands (a separate task)."""
    conn = _open_db(root)
    if conn is None:
        return _empty_kpis()
    try:
        runs = [dict(row) for row in conn.execute("SELECT * FROM runs")]
        steps = [dict(row) for row in conn.execute("SELECT * FROM steps")]
    finally:
        conn.close()
    if not runs:
        return _empty_kpis()

    total = len(runs)
    status_counts: dict[str, int] = {}
    for run in runs:
        status_counts[run["status"]] = status_counts.get(run["status"], 0) + 1
    durations = [run["duration_s"] for run in runs if run["duration_s"] is not None]
    runs_by_day: dict[str, int] = {}
    for run in runs:
        if run["started_at"] is not None:
            day = _day(run["started_at"])
            runs_by_day[day] = runs_by_day.get(day, 0) + 1

    n_steps = len(steps) or 1  # guard div-by-zero; rates read 0 when there are no steps
    confidences = [s["confidence"] for s in steps if s["confidence"] is not None]
    return {
        "total_runs": total,
        "success_rate": round(status_counts.get("ok", 0) / total, 3),
        "status_counts": status_counts,
        "latency_s": {
            "p50": _percentile(durations, 0.50),
            "p95": _percentile(durations, 0.95),
            "p99": _percentile(durations, 0.99),
            "max": round(max(durations), 3) if durations else 0.0,
        },
        "per_app": _per_app(steps),
        "avg_confidence": round(sum(confidences) / len(confidences), 3) if confidences else 0.0,
        "fallback_rate": round(sum(1 for s in steps if s["type"] == "fallback") / n_steps, 3),
        "no_match_rate": round(sum(1 for s in steps if s["status"] == "no_match") / n_steps, 3),
        "quality": _quality_aggregate(runs),
        "runs_by_day": dict(sorted(runs_by_day.items())),
    }


# --- health alerts -----------------------------------------------------------

# Fixed thresholds are intentionally conservative defaults for a local tool; pass your own to
# alerts(). A breach is a "warning" (2x over → "critical"). quality_drop compares the recent half of
# scored runs against the older half — a rolling-baseline regression signal, not an absolute floor.
DEFAULT_THRESHOLDS: dict[str, float] = {
    "error_rate": 0.2,
    "no_match_rate": 0.2,
    "fallback_rate": 0.5,
    "p95_latency_s": 60.0,
    "min_quality": 0.7,
    "quality_drop": 0.15,
}


def _alert(metric: str, value: float, threshold: float, message: str) -> dict[str, Any]:
    level = "critical" if value >= threshold * 2 else "warning"
    return {
        "level": level,
        "metric": metric,
        "value": round(value, 3),
        "threshold": threshold,
        "message": message,
    }


def _quality_drop(runs: list[dict[str, Any]]) -> float:
    """How far the recent half of scored runs has fallen below the older half (0 if not enough data
    or no drop). Runs must be time-ordered oldest→newest by the caller."""
    scores = [r["quality_score"] for r in runs if r["quality_score"] is not None]
    if len(scores) < 4:
        return 0.0
    mid = len(scores) // 2
    older = sum(scores[:mid]) / mid
    recent = sum(scores[mid:]) / (len(scores) - mid)
    return float(max(0.0, round(older - recent, 3)))


def alerts(
    root: str | os.PathLike[str] | None = None,
    *,
    thresholds: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Health alerts for the whole store: one entry per breached threshold, empty when healthy.

    Reads the same SQLite summary as kpis(), so it is cheap and offline. Signals: run error rate,
    step no-match/fallback rates, p95 latency, an absolute quality floor, and a recent-vs-older
    quality drop."""
    limits = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    k = kpis(root)
    if k["total_runs"] == 0:
        return []
    conn = _open_db(root)
    runs: list[dict[str, Any]] = []
    if conn is not None:
        try:
            runs = [dict(r) for r in conn.execute("SELECT * FROM runs ORDER BY started_at")]
        finally:
            conn.close()

    fired: list[dict[str, Any]] = []
    error_rate = k["status_counts"].get("error", 0) / k["total_runs"]
    if error_rate > limits["error_rate"]:
        fired.append(
            _alert("error_rate", error_rate, limits["error_rate"], "run error rate is high")
        )
    if k["no_match_rate"] > limits["no_match_rate"]:
        fired.append(
            _alert(
                "no_match_rate",
                k["no_match_rate"],
                limits["no_match_rate"],
                "steps often return no match",
            )
        )
    if k["fallback_rate"] > limits["fallback_rate"]:
        fired.append(
            _alert(
                "fallback_rate",
                k["fallback_rate"],
                limits["fallback_rate"],
                "steps often fall back to web",
            )
        )
    p95 = k["latency_s"]["p95"]
    if p95 > limits["p95_latency_s"]:
        fired.append(
            _alert("p95_latency_s", p95, limits["p95_latency_s"], "p95 run latency is high")
        )
    avg_q = k["quality"]["avg_score"]
    if avg_q is not None and avg_q < limits["min_quality"]:
        fired.append(
            _alert(
                "min_quality", avg_q, limits["min_quality"], "average quality is below the floor"
            )
        )
    drop = _quality_drop(runs)
    if drop > limits["quality_drop"]:
        fired.append(
            _alert(
                "quality_drop", drop, limits["quality_drop"], "quality is dropping vs the baseline"
            )
        )
    return fired


def _log_run_alerts(record: dict[str, Any]) -> None:
    """Emit a per-run WARNING when the just-recorded run itself looks unhealthy (failed steps or low
    quality). Best-effort and store-independent — a quick heads-up in the logs at record time."""
    quality = record.get("quality") or {}
    if quality.get("errors") or quality.get("no_match"):
        _log.warning(
            "run %s had %s failed and %s no-match step(s)",
            record["run_id"],
            quality.get("errors", 0),
            quality.get("no_match", 0),
        )
    score = quality.get("score")
    if score is not None and score < DEFAULT_THRESHOLDS["min_quality"]:
        _log.warning(
            "run %s quality score %.2f is below %.2f",
            record["run_id"],
            score,
            DEFAULT_THRESHOLDS["min_quality"],
        )


# --- terminal rendering ------------------------------------------------------


def _clock(epoch: float | None) -> str:
    if epoch is None:
        return "—"
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def _clip(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def render_runs_list(rows: list[dict[str, Any]]) -> str:
    """A compact table of recent runs for `orchestrator runs list`."""
    if not rows:
        return "No runs recorded yet."
    header = f"{'WHEN':<16}  {'RUN':<12}  {'STATUS':<8}  {'TIME':>7}  {'STEPS':>5}  TASK"
    lines = [header, "-" * len(header)]
    for row in rows:
        lines.append(
            f"{_clock(row['started_at']):<16}  "
            f"{row['run_id'][:12]:<12}  "
            f"{row['status']:<8}  "
            f"{row['duration_s']:>6.1f}s  "
            f"{row['n_subtasks']:>5}  "
            f"{_clip(row['task'], 48)}"
        )
    return "\n".join(lines)


def render_run_detail(record: dict[str, Any]) -> str:
    """One run's full drill-down for `orchestrator runs show <id>`."""
    lines = [
        f"Run {record['run_id']}",
        f"  task     : {record['task']}",
        f"  when     : {_clock(record.get('started_at'))}   ({record['duration_s']:.1f}s)",
        f"  status   : {record['status']}  (exit {record['exit_code']})",
        f"  model    : {record['model']}   mode={record['mode']}",
        f"  subtasks : {record['n_subtasks']}   counts={record['counts']}",
        "",
        "Steps:",
    ]
    for i, step in enumerate(record["steps"], start=1):
        routing = step.get("routing") or {}
        lines.append(
            f"  {i}. [{step['status']}] {step['app_id']}"
            f" — op={step['operation']}  ({step['duration_s']:.1f}s)"
            f"  confidence={routing.get('confidence')}"
        )
        if routing.get("rationale"):
            lines.append(f"       why : {_clip(routing['rationale'], 90)}")
        if step.get("error"):
            lines.append(f"       error: {_clip(str(step['error']), 90)}")
        if step.get("note"):
            lines.append(f"       note : {_clip(str(step['note']), 90)}")
    return "\n".join(lines)


def render_alerts(fired: list[dict[str, Any]]) -> str:
    """Health alerts for `orchestrator runs alerts`."""
    if not fired:
        return "No alerts — the store looks healthy."
    lines = [f"{len(fired)} alert(s):"]
    for a in fired:
        lines.append(
            f"  [{a['level'].upper()}] {a['metric']} = {a['value']} "
            f"(threshold {a['threshold']}) — {a['message']}"
        )
    return "\n".join(lines)


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
    try:
        _log_run_alerts(record)
    except Exception as exc:  # a logging helper must never break a run either
        _log.warning("observability could not check run alerts: %s", exc)
    run_id_out: str = record["run_id"]
    return run_id_out
