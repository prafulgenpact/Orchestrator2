# Task: final-answer-charts

Status: Done
Type: feature
Scope: src/orchestrator/web.py, web/atelier-workspace.html, tests/unit/test_web.py, STATE.md
Phase: Whole-app UI — connector

## Goal (chart fix 2 of 3)

The final deliverable (the blog) should show the charts made during the run, not just the
intermediate step. Carry the run's chart images onto the final-answer card.

## Acceptance criteria

1. `_collect_images(plan_result)` gathers base64 PNGs from ok steps' `output['images']`, deduped and
   capped — unit-tested (dedupe, cap, empty, non-dict skipped).
2. The connector's `final` event includes `images`; the answer card renders them in a Charts section
   — verified live in-page (answer card shows the chart <img>s + the blog markdown).
3. `make verify` PASS.

## Plan

- web.py: pure `_collect_images`; add `images` to the `final` event.
- atelier-workspace.html: `.answer-charts` div in the answer card; `finalizeAnswer` renders
  `data.images` as inline PNGs.

## Done

Proof commit: (this commit)   Proof fingerprint: (sealed)   Auditor verdict: <pending>   Docs updated: STATE.md

Live-verified (headless Chrome): finalizeAnswer with images -> answer card renders the chart images
+ the blog markdown (h1), 0 JS errors.
