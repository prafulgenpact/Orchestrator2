# Task: rich-output-rendering

Status: Done
Type: feature
Scope: web/atelier-workspace.html, STATE.md
Phase: Whole-app UI — polish

## Goal

Intermediate result cards and the final answer card must render app outputs as readable,
well-formatted content (not raw JSON / raw markdown source), and copy as clean plain text:

1. Prose outputs (the blog / synthesis, ArXiv summaries, Teach Me lessons) render as real
   markdown — headings, bold, lists, blockquotes, code blocks, links — so a blog looks like a
   blog, with no stray `#`/`**` characters.
2. Structured outputs render for humans: an ArXiv paper list shows title / authors / meta /
   abstract / link per paper, not a JSON dump.
3. Code renders in a monospace code block, preserving formatting.
4. The Copy button yields clean, paste-ready text (markdown source for prose; a readable
   title/authors/abstract/link list for papers).

## Acceptance criteria

1. A markdown answer renders to real HTML headings/bold/lists (verified live in the browser: the
   answer card contains `<h1>/<h2>/<strong>/<ul>` and no literal leading `#`).
2. An ArXiv result renders one readable block per paper (title + abstract + link), not raw JSON
   (verified live: card contains paper titles as text, no `{`/`"arxiv_id"` noise).
3. Copy on a paper card yields title/authors/abstract/link text; Copy on the answer yields the
   markdown source + sources (verified live via the card `data-copy`).
4. `make verify` PASS. No backend/planner change; decomposition eval unchanged.

Live end-to-end: run a multi-app task on a freshly-restarted connector; confirm paper cards,
a rendered blog, and clean copy.

## Plan

- Add a small, self-contained markdown renderer (`mdToHtml`/`mdInline`) — escape first, then
  format (headings, bold/italic, inline+fenced code, ul/ol, blockquote, hr, links, paragraphs).
- Add a value dispatcher (`renderValue`) + `renderPaper`/`renderKV` that picks the right view by
  shape (string→md; paper list→paper items; dict with a text field / chat messages→md; images→
  <img>; else clean key/value). Rewrite `renderOutput` to use it.
- Render the streamed answer as markdown (accumulate raw, re-render on each delta).
- Clean-text copy: `valueToText`/`paperToText`; update `resultCopyText`/`answerCopyText`.
- CSS for `.md*`, `.paper`, `.kvrow`, `.out-*`.
- make verify; live-verify in a headless browser; update STATE.md.

## Done

Proof commit: (this commit)   Proof fingerprint: de51e2ff032c   Auditor verdict: <pending>   Docs updated: STATE.md

Live verification (headless Chrome against the connector): answer card renders <h1>/<h2>/
<strong>/<ul>, rawHashCount=0 (no stray `#`); ArXiv card shows 3 readable paper titles + links,
hasRawJson=false; paper Copy = title/authors/arXiv-id/abstract/link; 0 JS errors.
