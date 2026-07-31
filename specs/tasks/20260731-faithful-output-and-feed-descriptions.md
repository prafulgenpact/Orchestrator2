# Task: faithful-output-and-feed-descriptions

Status: Done
Type: feature
Scope: web/atelier-workspace.html, STATE.md
Phase: Whole-app UI — polish

## Goal

1. Every app's plain/console output renders faithfully (no mangling). Only true markdown (the
   blog, ArXiv summaries, Teach Me lessons) gets rich rendering; plain reports (e.g. Simulated
   Learning's `====`-boxed p-value demo) keep the app's own layout in a monospace block.
2. The left Progress feed is conversational — it shows each step's plain-English description —
   while the Agent Trace keeps the short technical title + app + method (so the two views differ).

## Acceptance criteria

1. A non-markdown string (console/box report) renders as `<pre class="report">` preserving its
   layout, with no stray `<hr>`; a markdown string still renders `<h1>/<strong>/<ul>` — verified
   live in-page.
2. The feed shows subtask descriptions; the trace shows subtask titles; feed text ≠ trace text —
   verified live in-page.
3. `make verify` PASS. No backend change; decomposition eval unchanged.

## Plan

- `looksLikeMarkdown(s)` + `renderText(s)`: markdown → `md()`, else → `<pre class="report">`.
  Route all string outputs (incl. text fields / chat messages) through `renderText`. Add `.report`
  CSS (monospace, pre-wrap, overflow-wrap:anywhere).
- `buildSteps` stores `description`; `renderFeed` shows `description || title`; `renderTrace`
  keeps `title`.

## Done

Proof commit: (this commit)   Proof fingerprint: 47729fcb4bb4   Auditor verdict: <pending>   Docs updated: STATE.md

Live-verified (headless Chrome, in-page): box-report → <pre class="report"> (no <hr>); blog →
markdown; feed shows descriptions, trace shows titles, feed ≠ trace; 0 JS errors.

Follow-up (separate backend task): user chose to split code apps into write→execute as two real
trace steps (issue 3). That's a planner/executor change affecting the decomposition eval — tracked
as its own task, plan-first.
