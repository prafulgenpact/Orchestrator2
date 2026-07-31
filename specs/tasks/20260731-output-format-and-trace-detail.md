# Task: output-format-and-trace-detail

Status: Done
Type: feature
Scope: web/atelier-workspace.html, STATE.md
Phase: Whole-app UI — polish

## Goal

1. Every app's intermediate output is well formatted — including plain multi-line reports (e.g.
   Simulated Learning's p-value demo) which previously collapsed into one cluttered blob.
2. The agent trace shows, per step: app name, method/function invoked, input/arguments, and the
   (truncatable) output.

## Acceptance criteria

1. A plain multi-line report string preserves its line structure (rendered with `<br>`) and
   `=== Title ===` / `--- Title ---` lines become section headings — verified live: the p-value
   report renders `<h3>` sections with `<br>` line breaks, not one paragraph.
2. Each trace step's detail lists App, Method, Input, Output, Status; Output is truncated for
   long payloads — verified live: Method/Input/Output rows populated from the result event.
3. `make verify` PASS. No backend change; decomposition eval unchanged.

## Plan

- `mdToHtml`: join wrapped lines within a paragraph with `<br>` (not a space) so multi-line tool
  output keeps structure; treat `=== t ===` / `--- t ---` as `<h3>`, bare `===`/`---` as `<hr>`.
- Store `operation`/`args`/`output` on each step in `addResultCard`; render App/Method/Input/
  Output/Status in `renderTrace` with `trunc`/`argsText` helpers; add `.val.mono` CSS.

## Done

Proof commit: (this commit)   Proof fingerprint: 703855d07096   Auditor verdict: <pending>   Docs updated: STATE.md

Live-verified (headless Chrome, in-page): p-value report → `<h3>` sections + `<br>` lines;
trace detail keys = App/Method/Input/Output/Status with method+args+output populated; 0 JS errors.
