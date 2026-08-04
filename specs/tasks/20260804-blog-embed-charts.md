# Task: blog-embed-charts

Status: Done
Type: feature
Scope: src/orchestrator/registry.py, src/orchestrator/executor.py, registry/apps.json, tests/unit/test_registry.py, tests/unit/test_executor.py, STATE.md
Phase: Phase 2 — executor/contracts

## Goal (chart fix 3 of 3)

The PUBLISHED blog should contain the charts, not only the Atelier answer card. When the blog is
published via import (the orchestrator supplies `content`), embed the run's charts into that content
as markdown data-URI images.

## Acceptance criteria

1. `AppOperation.embed_images` parses (a request-field name; None default) and round-trips.
2. `_embed_upstream_images` appends upstream chart images to the named field as markdown data-URIs —
   deduped, capped by count and a size budget, a no-op without charts — unit-tested.
3. `post_blog_import` carries `embed_images: "content"`; make verify PASS.

## Caveat (documented, honest)

Best-effort: only the import path (not the app's own `generate_blog_async`, which has no content we
author) and only when the blog subtask depends on the chart step so its images are upstream. Whether
the images display depends on Blogs Playground rendering data-URI images in markdown. Large charts
are skipped to respect the content size cap. Regardless, the charts always show on the Atelier
answer card (chart fix 2).

## Done

Proof commit: (this commit)   Proof fingerprint: (sealed)   Auditor verdict: <pending>   Docs updated: STATE.md
