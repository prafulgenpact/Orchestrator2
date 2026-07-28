# Task: observability-save-runs

Status: DONE
Type: feature
Scope: src/orchestrator/observability.py, src/orchestrator/cli.py, tests/unit/test_observability.py, .gitignore, STATE.md, CLAUDE.md
Phase: Observability Step A — save every run (plan: ~/.claude/plans/i-need-to-build-validated-prism.md)

## Goal

Every orchestrator run is saved durably in a standard trace/step shape, so history, audit,
and (later) a dashboard are possible. Today a run prints an answer and is forgotten. When this
task is done, each run writes: one full-detail JSON file, one summary row in a local SQLite
database, and appended lines in a JSONL event log — driven by a reusable `record_run(...)` entry
point the CLI uses now and a future UI backend can reuse unchanged. Recording is best-effort: it
never changes the answer, the exit code, or the LLM request hashes (eval stays 16/16), and a disk
failure is swallowed.

## Acceptance criteria

Each one names the test that proves it.

1. `build_run_record(plan, result, synthesis, ...)` returns a run record with a 32-hex `run_id`,
   a step per subtask carrying `step_id`(16-hex)/`parent_id`/`type`/`app_id`/`status`/`duration_s`/
   `input`/`output`/`error`/`source`, plus rolled-up counts — proven by
   `tests/unit/test_observability.py::test_build_run_record_shape`.
2. `save_run(record, root=tmp)` writes `runs/<run_id>.json`, inserts a `runs` row + `steps` rows in
   `observability.db`, and appends to `logs/events.jsonl`; `get_run(run_id, root)` round-trips the
   saved JSON — proven by `::test_save_and_reload_round_trip`.
3. A failing sink never raises: `save_run` to a read-only/broken root returns without error and the
   caller is unaffected — proven by `::test_save_run_swallows_disk_error`.
4. Recording adds nothing to any LLM request hash (no planner/selector/judge change) — proven by
   `::test_recording_does_not_touch_request_hash` (build a record; assert a sample
   `LLMRequest.to_dict()` is unchanged before/after) and by the unchanged eval fixtures.
5. `make verify` PASS; decomposition eval unchanged at 16/16.
6. Live (replay mode): `--execute` on a recorded task creates a run JSON + DB row + event lines with
   every step's fields populated; `--no-record` skips all writes.

## Plan (before coding)

1. New `src/orchestrator/observability.py`:
   - id generator (uuid4 hex for run_id 32-hex; os.urandom(8).hex() for step_id 16-hex) — stdlib.
   - `build_run_record(plan, result, synthesis, *, mode, model, exit_code, started_at, ended_at,
     run_id=None, session_id=None)` → dict in the standard shape, from existing `to_dict()`s.
   - `save_run(record, *, root)` → JSON file + SQLite upsert + JSONL append; each wrapped so any
     OSError/sqlite error is logged and swallowed (best-effort).
   - `get_run(run_id, *, root)`, and a thin `record_run(...)` facade that stamps ids/timestamps and
     calls build+save (the reusable entry point).
   - `_connect(root)` creates the SQLite schema (`runs`, `steps`) on first use.
   - stdlib `logging` JSON formatter helper writing `logs/orchestrator.jsonl`.
2. `src/orchestrator/cli.py`: capture `started_at` at entry; call `record_run(...)` on execute
   success and on the dry-run path; add `--no-record` and `--run-id` flags. Keep executor untouched.
3. `.gitignore`: add `runs/`, `logs/`, `observability.db` (mirror `orchestrator-output/`).
4. Tests in `tests/unit/test_observability.py` (all offline, tmp_path — no network).
5. STATE.md: record the task.

Note on CLAUDE.md in Scope: the human edited CLAUDE.md this session (constitution wording); it is
listed in Scope to consciously acknowledge that pre-existing worktree change per drift_check.

## Failure analysis

<!-- MANDATORY when the same check fails 3x (doom-loop protocol). -->

## Done

Proof commit: <sha>   Auditor verdict: <>   Docs updated: <>
