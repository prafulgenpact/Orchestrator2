# Task: selection-structured-output

<!-- Fill Goal/Type/Scope/Acceptance BEFORE any code. This file IS the plan for
     this task; drift_check.py enforces the Scope line mechanically. -->

Status: DONE
Type: bugfix
Scope: src/orchestrator/**, tests/unit/**
Phase: Phase 2 — accuracy/robustness (fewer web fallbacks; serves AC-1)

## Goal

The operation-selector's LLM call can no longer produce unparseable JSON for a
code-heavy argument. It uses Anthropic **tool-use (forced structured output)** so the
returned `{operation, arguments}` is always valid JSON, the per-call token budget is
raised so multi-section code fits, and a genuine `max_tokens` truncation is detected and
degrades cleanly (disclosed web fallback) instead of crashing or silently truncating.

Before: a task like "code blocks for all sections" made the selector emit a huge `code`
string that overflowed `max_tokens=2000`, truncating the JSON mid-string
(`Unterminated string starting at ... char 52`); all 3 retries truncated identically →
web fallback. After: the app (e.g. Simulated Learning `execute_code`) actually runs.

## Acceptance criteria

Each one names the test that proves it.

1. `LLMRequest` carries optional `tools` + `tool_choice`; `to_dict()` serializes them ONLY
   when set, so a tools-free request (planner/grounding/synthesis) hashes byte-identically
   to today → no fixture re-recording — proven by
   `tests/unit/test_foundry.py::test_to_dict_omits_tool_fields_when_unset` and
   `::test_to_dict_includes_tool_fields_when_set`.
2. A Foundry tool-use response is turned into canonical JSON (`json.dumps(tool_use.input)`),
   and a `max_tokens` truncation or a missing `tool_use` block raises a clear `LLMError`
   (pure helper `_extract_text`; the network `complete` line stays `# pragma: no cover`) —
   proven by `tests/unit/test_foundry.py::test_extract_tool_use_returns_json`,
   `::test_extract_raises_on_truncation`, `::test_extract_raises_when_no_tool_use`.
3. `select_operation` issues the call as forced tool-use (one `select_operation` tool →
   `{operation, arguments}`) with `_MAX_TOKENS` raised 2000→8000; all existing selector
   tests stay green (parsing is unchanged, defense-in-depth for non-Foundry clients) —
   proven by `tests/unit/test_selector.py::test_select_requests_structured_tool_output`.
4. A selection-time `LLMError` (e.g. truncation) is caught at the call site → clean subtask
   error → the existing web safety net fires WITH disclosure (no crash, no silent fallback)
   — proven by `tests/unit/test_executor.py::test_selection_llm_error_becomes_clean_error`.
5. `make verify` PASS (>=90% cov); decomposition eval unchanged (planner untouched) — the
   e2e + eval fixtures are NOT re-recorded (guaranteed by AC-1's hash-identity test).

## Plan (before coding)

1. Write the failing tests first (AC 1-4).
2. `src/orchestrator/llm/base.py` — add `tools: tuple[dict, ...] = ()` and
   `tool_choice: dict | None = None` to `LLMRequest`; `to_dict()` adds each key only when set.
3. `src/orchestrator/llm/foundry.py` — new pure `_extract_text(message, *, expect_tool)`:
   tool path returns `json.dumps(tool_use.input)`, raises `LLMError` on `stop_reason ==
   "max_tokens"` or a missing tool_use block; text path unchanged. `complete()` passes
   `tools`/`tool_choice` when present and calls the helper.
4. `src/orchestrator/selector.py` — `_MAX_TOKENS` 2000->8000; `_selection_tool()` schema;
   set `tools`/`tool_choice` on the `LLMRequest`. Parsing/retry/grounding untouched.
5. `src/orchestrator/executor.py` — widen the selection `except SelectionError` to also
   catch `LLMError`, so a truncation becomes a clean error result (-> web safety net).
6. `make verify`; update STATE.md; mark this file Done with the proof commit.

## Failure analysis

<!-- MANDATORY when the same check fails 3x (doom-loop protocol). -->
(none — verify failed twice on lint only: test-stub params shadowing builtins (A002) and a
`dict()` call vs literal (C408); both fixed, not a logic doom-loop.)

## Done

All ACs met. make verify PASS. VERIFIED LIVE: the five-stage training-script task executes on
Simulated Learning (`op=execute_code status=ok`, real stdout, source :8001/api/execute) with no
web fallback — the exact failure class from the reported run.

Proof commit: sealed locally (make verify auto-seal → proof: commit), NOT pushed (per human).
Auditor verdict: <pending>   Docs updated: n-a (behavior internal to the LLM boundary)
