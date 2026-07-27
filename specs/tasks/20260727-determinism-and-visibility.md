# Task: determinism-and-visibility

Status: in progress
Type: feature
Scope: src/orchestrator/llm/base.py, src/orchestrator/llm/foundry.py, src/orchestrator/executor.py, src/orchestrator/models.py, src/orchestrator/render.py, tests/unit/**, STATE.md
Phase: Phase 2 — Fix 5 of the web-fallback deep-dive (plan: ~/.claude/plans/before-going-to-solutions-modular-lampson.md)

## Goal

Three visibility/determinism improvements: (1) every LLM call runs at temperature 0 so the same
task decomposes/selects/judges the same way run-to-run (today it is the SDK default 1.0 — a per-run
lottery); (2) a web-sourced answer is clearly labelled in the output (today a planner-routed web
answer has no marker beyond a Sources URL); (3) `--verbose` shows the exact arguments sent to each
app, so a guessed/defaulted input is auditable instead of invisible.

## Acceptance criteria

Each one names the test that proves it.

1. `LLMRequest.temperature` defaults to 0.0 and FoundryClient passes it to the API — proven by
   `tests/unit/test_foundry.py::test_request_temperature_is_sent`.
2. Temperature is NOT part of the request hash, so recorded fixtures still resolve (no re-record) —
   proven by `tests/unit/test_llm_replay.py::test_temperature_not_in_request_hash`.
3. A web-sourced result is labelled in the rendered output ("answered from a web search") —
   proven by `tests/unit/test_render.py::test_web_sourced_answer_is_labelled`.
4. `--verbose` shows the arguments sent to each app; non-verbose does not — proven by
   `tests/unit/test_render.py::test_verbose_shows_args` and `::test_clean_hides_args`.
5. `make verify` PASS; decomposition eval unchanged (temperature not in hash → fixtures intact).
6. Live: the same task run 3x is stable; a no-app task's answer is labelled web-sourced; a
   --verbose run shows the args sent.

## Plan (before coding)

1. llm/base.py: add `temperature: float = 0.0` to LLMRequest. Do NOT add it to `to_dict()` — the
   hash (replay key) must stay stable and temperature does not affect replay determinism. Document
   why, mirroring the existing tools/tool_choice omission precedent.
2. llm/foundry.py: add `kwargs["temperature"] = request.temperature` in complete_stream.
3. models.py: add `args: dict[str, Any] | None = None` (trailing default) to SubtaskResult +
   include in to_dict.
4. executor.py `_run_app_op`: pass `args=args` on the ok/caution result (and the skip result where
   the args exist) so the arguments are carried for rendering.
5. render.py: (a) verbose — print `args: {...}` per result when present; (b) label a web-sourced
   result (operation == "web_search") with an "answered from a web search" heads-up near the answer.
6. tests + `make verify` + live checks (criterion 6); STATE.md.

## Notes / decisions

- temperature 0 applies to synthesis too (the user prioritizes determinism/accuracy over answer
  variety; apps carry the user's voice — AC-4). Revisit only if the fused answer reads flat.

## Failure analysis

(none — clean run)

## Done

LLMRequest.temperature=0.0 (excluded from to_dict → fixtures intact); FoundryClient sends it;
SubtaskResult carries args; render labels web-sourced results and shows args in --verbose.
make verify PASS (fingerprint 77e49402ef88); eval unchanged. Tests: temperature sent + default +
not-in-hash, web label, verbose args on/off. Live: routing stable across 3 runs; web answer
labelled; --verbose shows args.

Proof commit: <this commit>   Auditor verdict: <pending>   Docs updated: STATE.md
