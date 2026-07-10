# Task: web-search-fallback

Status: in progress
Type: feature
Scope: src/orchestrator/web_search.py, src/orchestrator/executor.py, tests/unit/test_web_search.py, tests/unit/test_executor.py, tests/unit/test_cli.py, .env, STATE.md
Phase: Phase 2 — depth (plan-depth-orchestration.md Task 4; serves the objective's "no app -> fetch from the web")

## Goal

Subtasks that route to the web-search fallback now get a REAL grounded answer with citations
instead of being skipped. When a subtask's chosen app is the fallback, the executor runs a Tavily
web search (reusing the shared TAVILY_API_KEY the sibling apps already use), returning the grounded
answer + source URLs, which then flow into synthesis like any other result. This makes "give it any
task" work for general-knowledge intents (e.g. "what is a p-value?") that no specialized app can
serve. Still bounded by the hard wall-clock deadline (no hang); degrades to a clean "skipped" if no
search key is configured.

## Acceptance criteria

Each one names the test that proves it.

1. `search_web` calls Tavily and returns the answer + citation URLs; non-2xx or answerless
   responses raise `WebSearchError` — proven by `tests/unit/test_web_search.py::test_search_web_success`
   and `::test_search_web_error`.
2. `resolve_search_key` reads TAVILY_API_KEY (process env > project .env > sibling), None when
   absent — proven by `tests/unit/test_web_search.py::test_resolve_search_key_*`.
3. The executor runs the fallback: ok result with answer+citation on success; "skipped" when no key;
   "error" when the search fails — proven by
   `tests/unit/test_executor.py::test_web_fallback_success`, `::test_web_fallback_no_key`,
   `::test_web_fallback_error`.
4. `make verify` PASS (>=90% cov; dry-run e2e unchanged). Live: "what is a p-value?" (no app named)
   now returns a grounded, cited answer via the fallback.

## Plan (before coding)

1. `web_search.py`: `WebResult(answer, citations)`; `WebSearchError`; `resolve_search_key()` (env
   chain, reusing foundry's `_parse_env_file`/paths); `async search_web(query, *, client, api_key,
   max_results, timeout_s)` -> POST Tavily `/search` with `include_answer`.
2. `executor.py`: replace the fallback "skipped (deferred)" branch with `_run_web_fallback` —
   resolve key (skip if none), run `search_web` under `run_with_deadline`, return ok result
   (output={answer, citations}, source=first citation) or error on failure.
3. Tests: new test_web_search.py; add web-fallback executor tests (replace the old skip test);
   monkeypatch the fallback in the cli fallback test so no network is hit.
4. `make verify`, commit, seal, push. Live-verify a bare general-knowledge task.

## Failure analysis

## Done

Proof commit: <sha>   Auditor verdict: <pending>   Docs updated: yes/no
