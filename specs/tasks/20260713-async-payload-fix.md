# Task: async-payload-fix

Status: in progress
Type: fix
Scope: registry/apps.json, tests/unit/test_registry.py, STATE.md
Phase: Phase 2 — depth (follow-on to async-poll; makes Blogs/Research start calls actually succeed)

## Goal

The async start calls (Blogs `generate_blog_async`/`iterate_blog_async`, Research `start_research`)
were 422'ing because the selector filled type-risky OPTIONAL fields with guessed values (live proof:
"short blog" → `word_count_target: "short"` → 422 int_parsing). Confirmed: a minimal `{topic}` body
is accepted (200 → run_id). Fix: trim these ops' `request_fields` to the safe minimal set the
selector can always fill correctly (the app defaults everything else), so the start succeeds and the
async poller (T4) runs the app to completion instead of falling back to the web.

## Acceptance criteria

Each one names the test that proves it.

1. The three async start ops expose only safe minimal request fields (generate→[topic];
   iterate→[blog_id,instruction]; start_research→[topic]) — proven by
   `tests/unit/test_registry.py::test_async_start_ops_have_minimal_request_fields`.
2. `make verify` PASS (>=90% cov; dry-run e2e unchanged — request_fields are not in to_prompt_dict).
3. Live: "write a short blog about X" is produced BY Blogs Playground (a real run, no web fallback
   banner).

## Plan (before coding)

1. apps.json: `generate_blog_async` request_fields → ["topic"]; `iterate_blog_async` →
   ["blog_id", "instruction"]; `start_research` → ["topic"]. (Richer, type-validated optional
   passing is a later hardening; minimal-and-correct first.)
2. test_registry.py: assert the trimmed request_fields.
3. `make verify`, commit, seal, push. Re-run the live blog to confirm it comes from Blogs Playground.

## Failure analysis

## Done

Proof commit: <sha>   Auditor verdict: <pending>   Docs updated: yes/no
