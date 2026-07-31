# Task: trace-code-authoring-substep

Status: Done
Type: feature
Scope: web/atelier-workspace.html, STATE.md
Phase: Whole-app UI — polish

## Goal

When a step's input includes model-authored code, the Agent Trace shows it as TWO honest nodes:
an "authored code" node attributed to the Orchestrator's model (showing the code) and the app
execution node (showing output). No fabricated app call — Simulated Learning has no write API, so
the writing is truthfully attributed to the orchestrator, not the app.

## Acceptance criteria

1. A step whose `args.code` is a non-empty string renders two trace nodes: (a) tag "Orchestrator",
   name "Wrote the code", method "authored code", Output = the code; (b) the app node with the real
   method + output. A non-code step renders a single node — verified live in-page (3 nodes for a
   2-step plan where one step has code).
2. `make verify` PASS. No backend change; decomposition eval unchanged.

## Plan

- Extract a `traceNode(opts)` builder; in `renderTrace`, when `s.args.code` is present, prepend an
  Orchestrator-attributed "Wrote the code" node before the app-execution node.

## Done

Proof commit: (this commit)   Proof fingerprint: 7670350142da   Auditor verdict: <pending>   Docs updated: STATE.md

Live-verified (headless Chrome, in-page): code step -> 2 nodes ("Wrote the code" / Orchestrator +
"…" / Simulated Learning · execute_code); non-code step -> 1 node; 0 JS errors.
Decision: user chose honest UI sub-steps over a backend write→execute split (no write endpoint
exists for Simulated Learning).
