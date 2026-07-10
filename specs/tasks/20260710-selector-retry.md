# Task: selector-retry

Status: in progress
Type: fix
Scope: src/orchestrator/selector.py, tests/unit/test_selector.py, tests/unit/test_executor.py, STATE.md
Phase: Phase 2 — depth (all-11-apps robustness; serves AC-1 reliability)

## Goal

The operation selector self-corrects on malformed JSON, mirroring the planner's bounded retry.
Today `select_operation` makes ONE call and fails on the first bad response — so when the model
returns invalid JSON (e.g. multi-line Python with raw newlines inside a `code` string value), the
subtask dies with "operation selection was not valid JSON". After this fix, the selector re-prompts
with the concrete parse error plus an escape hint, up to `max_retries` times, before giving up; and
its per-call token budget is raised so long code arguments aren't truncated mid-string.

## Acceptance criteria

Each one names the test that proves it.

1. The selector retries a bad-then-good response and returns the valid selection — proven by
   `tests/unit/test_selector.py::test_select_retries_then_succeeds`.
2. The selector raises SelectionError (original message preserved) after exhausting retries —
   proven by `tests/unit/test_selector.py::test_select_exhausts_retries`.
3. Single-shot behavior is unchanged with `max_retries=0` (raises the original parse/validation
   error) — proven by the existing error tests, updated to pass `max_retries=0`.
4. `make verify` PASS (>=90% coverage; dry-run e2e unchanged — selector is not on that path). Live:
   a multi-line "run this Python …" task selects + executes without a JSON crash.

## Plan (before coding)

1. selector.py: extract the parse+validate body into `_parse_selection(raw, app)` (raises
   SelectionError). Wrap `select_operation` in a `max_retries`-bounded loop (default 2) that appends
   the assistant's bad reply + a corrective user turn (report the error; demand ONE raw JSON object;
   escape newlines in string values as \n). Re-raise the last SelectionError on exhaustion. Bump
   `_MAX_TOKENS` 1000 -> 2000.
2. tests: add the two retry tests; add `max_retries=0` to the single-shot error tests; fix the
   executor selection-error test to feed enough bad responses (executor uses the default budget).
3. `make verify`, commit, seal, push. Live re-verify.

## Failure analysis

## Done

Proof commit: <sha>   Auditor verdict: <pending>   Docs updated: yes/no
