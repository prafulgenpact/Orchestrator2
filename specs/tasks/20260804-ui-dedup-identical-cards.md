# Task: ui-dedup-identical-cards

Status: Done
Type: fix
Scope: web/atelier-workspace.html, STATE.md
Phase: Whole-app UI

## Goal (fix 3 of the RCA set)

Intermediate output cards must be unique. When a `result` event's (app + operation + output) is
identical to a card already on the canvas, don't render a second card. The step is still recorded
in the feed/trace (the technical view stays honest); only the duplicate canvas card is suppressed.

## Acceptance criteria

1. Two `result` events with identical app/operation/output produce ONE canvas card; a third event
   with different output produces a second card — verified live in-page.
2. The de-duplicated step is still enriched onto its trace step (feed/trace re-render) — verified
   in-page (the trace still reflects both subtasks).
3. `make verify` PASS (HTML only; no backend/test change).

## Plan

- Add a per-run `Set` of result signatures (reset in `runTask`). In `addResultCard`, after the
  step enrichment, compute `sig = app | operation | status | JSON(output/error)`; if already seen,
  `renderFeed()/renderTrace()` and return without creating a card; else record it and build the card.

## Done

Proof commit: (this commit)   Proof fingerprint: b8396d30d7a2   Auditor verdict: <pending>   Docs updated: STATE.md

Live-verified (headless Chrome): 2 identical + 1 different result -> 2 cards, 3 trace nodes, deduped step still enriched, 0 errors.
