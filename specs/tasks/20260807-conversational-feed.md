# Task: conversational-feed

Status: in progress
Type: feature
Scope: src/orchestrator/web.py, src/orchestrator/narrator.py, src/orchestrator/prompts/narrator_system.md, web/atelier-workspace.html, tests/unit/test_web.py, tests/unit/test_narrator.py, STATE.md, .gitignore
Phase: Phase 3 — web connector

## Goal

The left task panel talks to the user like an agent, not a checklist (user request, with
reference screenshots). Two parts:

1. **Plan as a chat message (no new LLM calls).** When the plan arrives, the panel shows a
   Master-Agent chat bubble in plain English: the recognized intent plus a numbered list of the
   steps (the plan's existing plain-English descriptions). The live step checklist stays below it.
2. **Live narration per finished step (one small LLM call each).** As each step's real result
   arrives, a new `narrate` SSE event carries 1–2 conversational sentences grounded ONLY in that
   step's actual output (real numbers, honest failures). The UI appends each as a chat bubble.
   Narration is garnish: it runs on the side, and any narration failure can never break, slow, or
   reorder the run itself.

## Acceptance criteria

1. `run_events` emits a `narrate` event (subtask_id + text) after a step's `result` and before
   `done` — proven by `tests/unit/test_web.py::test_run_events_emits_narrate`.
2. A narration failure (LLM error or bug) produces no narrate event and the stream still ends
   with `final` + `done` — proven by `tests/unit/test_web.py::test_narrate_failure_never_breaks_stream`
   and `tests/unit/test_narrator.py::test_narrate_result_swallows_llm_errors`.
3. The narrator prompt is grounded: the user message carries the task, step title/description,
   app name, status/error, and the step output truncated to a bounded size — proven by
   `tests/unit/test_narrator.py::test_build_user_message_*`.
4. The UI renders the plan bubble (intent + numbered steps) on the `plan` event and a Master-Agent
   bubble per `narrate` event; `make verify` PASS. Live proof: restart connector, run a real task
   headless via `/run?task=…`, observe interleaved `narrate` events with real output numbers.

## Plan (before coding)

1. `prompts/narrator_system.md` — system prompt: 1–2 plain-English sentences, first person,
   facts only from the provided output, honest on failure, no markdown.
2. `narrator.py` — `load_system_prompt`, `build_user_message` (bounded output excerpt),
   `narrate_result(client, *, model, task, result, step_title, step_description)` returning ""
   on any exception (never raises).
3. `web.py` — in `run_events`: per result, fire a daemon narration thread that puts
   `("narrate", {...})` on the bus; worker joins narration threads (bounded) before the sentinel
   so no narrate event is lost or lands after `done`.
4. `atelier-workspace.html` — agent bubble CSS; plan bubble on `plan` event; `narrate` listener
   appending agent bubbles; reset on new run; auto-scroll.
5. Unit tests (fakes, no network) → `make verify` → restart connector → live headless proof.

## Failure analysis

<!-- MANDATORY when the same check fails 3x (doom-loop protocol). -->

## Done

Proof commit: <sha>   Auditor verdict: <ON_TRACK/...>   Docs updated: yes/no/n-a
