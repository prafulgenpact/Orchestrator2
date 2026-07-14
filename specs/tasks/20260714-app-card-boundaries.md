# Task: app-card-boundaries

Status: in progress
Type: feature
Scope: registry/apps.json, src/orchestrator/**, tests/**, specs/tasks/**, STATE.md
Phase: Phase 2 — depth (better decomposition via richer app cards; serves AC-1)

<!-- Bundles the still-unsealed decomposition-eval deliverable (tests/eval/**) with this
     change — they push together. The eval is the referee for this task. -->

## Goal

Each app card carries an explicit `when_not` boundary (situations it is the WRONG choice,
naming the better specialist), and the planner is told to honour it — so routing at the
app collisions (teach-me vs stanford-llm vs stats-teacher; news vs social; blogs vs research;
code vs coding-playground) is grounded in the card, not a guess. Proven to NOT regress by the
decomposition eval.

## Acceptance criteria

1. Every non-fallback app in `registry/apps.json` has a non-empty `when_not` list; the loader
   parses it and `to_prompt_dict` exposes it — proven by `tests/unit/test_registry.py`
   (`test_when_not_parsed_and_in_prompt_dict`, updated `test_to_prompt_dict_is_compact`).
2. Planner prompt bumped to v3 with a rule to honour `when_not`; `PROMPT_VERSION = "3"` —
   existing `tests/unit/test_planner.py` stays green.
3. `make verify` PASS (>=90% cov). e2e dry-run fixture re-recorded for the new prompt/registry;
   stale fixture deleted.
4. Decomposition eval re-recorded and re-scored: **>= 16/16** (no regression). Scorecard in Done.

## Plan (before coding)

1. `registry/apps.json` — add `when_not` to all 11 non-fallback apps (short, each names the
   better app for the excluded case).
2. `registry.py` — parse `when_not` (list of strings, default empty); add to `AppEntry` and
   `to_prompt_dict`.
3. `planner_system.md` → v3: one rule — never choose an app for a case its `when_not` rules out;
   follow the pointer to the named specialist. `planner.py`: `PROMPT_VERSION = "3"`.
4. `test_registry.py`: update the compact-keys test; add a `when_not` parse+prompt test.
5. Re-record: eval fixtures (`bash tests/eval/record.sh`) + the e2e dry-run fixture
   (`AGENT_LLM_MODE=record ... python -m orchestrator [--json] "plan my week of learning transformers"`);
   delete the stale e2e fixture.
6. `make verify`; re-score eval; write scorecard. Stop for review before seal/push.

## Failure analysis

(none)

## Scorecard (after adding when_not boundaries, prompt v3)

Re-recorded live (`claude-opus-4-6`, prompt v3, when_not on every card) and re-scored:
**16/16 — no regression** vs the v2 baseline. All collisions still route correctly. Honest
read: on this set v2 was already 16/16, so the boundaries show no *measurable* gain here — their
value is robustness (they make each card self-explanatory about where it stops) and insurance
for harder/adjacent queries and future apps. To *prove* a gain, add harder ambiguous cases and
A/B with the field on vs off (follow-up). `make verify` PASS; e2e dry-run fixture re-recorded
(prompt v3); 66 unit tests pass.

## Done

Proof commit: <pending seal/push>   Auditor verdict: <pending>   Docs updated: yes (registry cards)
