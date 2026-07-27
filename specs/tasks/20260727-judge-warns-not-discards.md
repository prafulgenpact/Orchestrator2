# Task: judge-warns-not-discards

Status: in progress
Type: bugfix
Scope: src/orchestrator/grounding.py, src/orchestrator/executor.py, tests/unit/**, STATE.md
Phase: Phase 2 — Fix 3 of the web-fallback deep-dive (plan: ~/.claude/plans/before-going-to-solutions-modular-lampson.md)

## Goal

The relevance judge becomes ADVISORY, not a deleter. When it flags an app's non-empty output as a
possible mismatch, the orchestrator KEEPS the app's answer (status ok) and attaches a visible
caution — instead of discarding it (which today drops it to no_match). The judge is a single
stochastic LLM opinion and is sometimes wrong; a wrong discard is itself an inaccuracy, and the
apps are tuned to the user (AC-4). Genuinely EMPTY output stays an honest failure (nothing to keep).

## Acceptance criteria

Each one names the test that proves it.

1. An off-topic-but-non-empty result is KEPT: status "ok", output preserved, with a caution note —
   proven by `tests/unit/test_executor.py::test_irrelevant_result_kept_with_caution`.
2. A genuinely blank result stays an honest failure (no_match), output None, nothing fabricated —
   proven by `tests/unit/test_executor.py::test_blank_result_is_no_match`.
3. A relevant (PASS) result carries NO note (clean answer) —
   proven by `tests/unit/test_executor.py::test_relevant_result_has_no_note`.
4. The caution renders under the answer as a heads-up —
   proven by `tests/unit/test_render.py::test_caution_note_renders_as_heads_up`.
5. `make verify` PASS; decomposition eval unchanged.
6. Live: a normal task still answers from its app with no spurious caution (no regression).

## Plan (before coding)

1. grounding.py: expose `is_blank` (rename `_is_blank`; keep the internal call). check_relevance's
   (bool, reason) contract is UNCHANGED — the keep-vs-discard policy lives in the executor.
2. executor.py `_run_app_op`, the `if not relevant` branch:
   - `is_blank(result.data)` → no_match (honest empty failure, output None) — unchanged.
   - else → status "ok", output PRESERVED, artifacts included, note = caution string built from the
     judge's reason. The judge advises; it no longer deletes.
3. tests: flip test_execute_irrelevant_becomes_no_match → kept-with-caution; flip
   test_app_no_match_is_not_web_rescued (irrelevant-with-content → ok+note); add blank→no_match and
   relevant→no-note; add a render test for the caution heads-up.
4. `make verify`; live sanity run; STATE.md.

## Notes / decisions

- check_relevance stays (bool, reason) so grounding tests are untouched; only the executor's
  reaction to a FAIL changes (discard → keep+warn). Blank output is the one hard FAIL that remains.

## Failure analysis

(none — clean run)

## Done

grounding exposes `is_blank`; executor keeps a judge-flagged non-empty result as ok + caution note
(blank stays no_match). make verify PASS (fingerprint 6b853bdf71cb). Tests: irrelevant-with-content
kept+cautioned, blank→no_match, relevant→no note, caution renders as heads-up. Live sanity: normal
blog task answered by the app, no spurious caution.

Proof commit: <this commit>   Auditor verdict: <pending>   Docs updated: STATE.md
