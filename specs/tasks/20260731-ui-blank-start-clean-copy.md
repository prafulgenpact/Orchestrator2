# Task: ui-blank-start-clean-copy

Status: Done
Type: feature
Scope: web/atelier-workspace.html, STATE.md
Phase: Whole-app UI — polish

## Goal

Three UI fixes to the Atelier workspace so a fresh load is a clean slate and outputs are
copy-paste ready:

1. On load, every section is blank — no prepopulated conversation, no sample result cards, no
   canned trace summary. Nothing appears until the user runs a real task.
2. The "System Telemetry" block under the Agent Trace (Technical view) is removed entirely
   (HTML + its dead CSS).
3. Every intermediate result card and the final answer card carry a clean, well-formatted plain
   text payload so the Copy button yields something that pastes cleanly elsewhere (labelled
   heading, body, note, sources) rather than scraped innerText.

## Acceptance criteria

1. Fresh load shows an empty conversation thread (no user bubble), empty feed, empty canvas
   (no sample cards), and an empty trace summary — visually verified in the running connector.
2. No `System Telemetry` text or `.telemetry`/`.stat`/`.chart` CSS remains in the file
   (`grep -i telemetry` and `grep -nE '\.stat|\.chart'` return nothing).
3. Clicking Copy on a result card / answer card copies a structured text block (label, output,
   note, sources) — driven by a per-card `data-copy` payload, not `.body` innerText.
4. `make verify` PASS; decomposition eval unchanged (no planner/executor/py change).

## Plan

- Empty the canvas (remove the 5 sample article cards).
- Hide the user message + set task echo empty on load; reveal + timestamp it on run.
- Empty the trace summary block on load (JS fills it on run).
- Remove the telemetry HTML block and its CSS rules.
- Build a `data-copy` plain-text payload for result and answer cards; make the Copy button
  prefer it, falling back to innerText.

## Done

Proof commit: (this commit)   Proof fingerprint: 240b75950277   Auditor verdict: <pending>   Docs updated: STATE.md
