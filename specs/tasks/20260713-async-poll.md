# Task: async-poll

Status: in progress
Type: feature
Scope: src/orchestrator/registry.py, src/orchestrator/executor.py, registry/apps.json, tests/unit/test_registry.py, tests/unit/test_executor.py, STATE.md
Phase: Phase 2 — depth (mini-task T4 of the 3 user asks; makes Blogs & Research do the work, not the web)

## Goal

Operations that kick off an async job (start → poll a run until done) are now driven to completion
by the executor, so Blogs Playground actually writes the blog and Research Assistant runs the
research — instead of returning a bare run id (and falling back to the web). An operation can carry
a `poll` spec (poll op, run-id field, status path + terminal values, result path); when present the
executor calls the start op, then polls the run op until a terminal state, extracting the final
content. Bounded by an overall wait cap so it can never hang (AC-2); a failed/timed-out run errors
cleanly (and the web safety net + disclosure still apply).

## Acceptance criteria

Each one names the test that proves it.

1. `AppOperation` parses an optional `poll`/`AsyncSpec` (poll_op, run_id_field, run_id_arg,
   status_path, done_values, failed_values, result_path) — proven by
   `tests/unit/test_registry.py::test_operation_poll_spec_parsed` and the shipped
   Blogs/Research specs by `::test_async_specs_present`.
2. The executor runs an async op to completion: start → poll until done → returns the resolved
   result content — proven by `tests/unit/test_executor.py::test_async_runs_to_completion`.
3. Failure modes error cleanly: missing run id, a failed terminal status, and a wait-cap timeout —
   proven by `::test_async_missing_run_id`, `::test_async_failed_status`, `::test_async_times_out`.
4. `make verify` PASS (>=90% cov; dry-run e2e unchanged). Live: "write a short blog about X" is
   produced by Blogs Playground (auto-started), not the web.

## Plan (before coding)

1. registry.py: `AsyncSpec` dataclass + `AppOperation.poll: AsyncSpec | None`; parse/validate the
   `poll` object; include in `to_dict`.
2. executor.py: `_dig(obj, dotted_path)` (dict keys + list indices incl. negatives); `_run_async`
   (start via call_operation → extract run_id → poll the run op until a terminal status, bounded by
   `_ASYNC_MAX_WAIT_S`/`_ASYNC_POLL_INTERVAL_S`); `_run_app_op` routes to it when `op.poll` is set.
3. apps.json: add `poll` to Blogs `generate_blog_async` + `iterate_blog_async` and Research
   `start_research`.
4. tests: registry parse + shipped specs; executor async happy path + 3 failure modes (call
   monkeypatched; interval monkeypatched to ~0). `make verify`, commit, seal, push. Live-verify a blog.

## Failure analysis

## Done

Proof commit: <sha>   Auditor verdict: <pending>   Docs updated: yes/no
