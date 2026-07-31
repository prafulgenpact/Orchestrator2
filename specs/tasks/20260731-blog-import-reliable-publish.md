# Task: blog-import-reliable-publish

Status: Done
Type: fix
Scope: registry/apps.json, tests/unit/test_registry_coverage.py, STATE.md
Phase: Phase 2 — app contracts

## Goal

Blogs Playground must reliably PUBLISH the blog instead of erroring at the 60s deadline.

## Root cause (evidence)

`POST /api/blog/import` (op `post_blog_import`) runs an inline StyleCritic + Verifier (two Opus
LLM calls) when `run_critique=true`. The app model defaults `run_critique=True`
(`Blogs Playground/backend/main.py:88`), and the orchestrator did not send it, so every import ran
the slow critique path (~30–60s+) and blew the op's hard 60s deadline → the run recorded
`retry: operation exceeded 60.0s deadline` (classified transient, but `transient_max=0` so no
retry). The blog text itself was model-authored (the `content` arg); only the publish failed.

## Fix (orchestrator contract, not the external app)

In `registry/apps.json`, op `post_blog_import`:
- add `"defaults": {"run_critique": false}` — the selector fills it (setdefault) and it is sent in
  the POST body (`_build_request` sends all non-path args), so import takes the fast path and
  publishes immediately. Quality critique is the app's optional add-on and is not needed for the
  orchestrator's own grounded synthesis.
- remove `"run_critique"` from `request_fields` so the model never sets it back to true (contract
  test only rejects fields NOT in the OpenAPI, so dropping one is subset-safe).
- raise `timeout_s` 60 → 120 as a generous anti-hang backstop (import is now instant; this only
  guards a pathologically slow save).

## Acceptance criteria

1. The `post_blog_import` contract sends `run_critique=false` by default and no longer lists it as
   a model-filled request field — asserted by a new unit test in tests/unit/test_registry_coverage
   (or test_registry) reading the contract.
2. `make verify` PASS (incl. api-contract + decomposition eval unchanged).
3. Live: a "draft and publish a blog" task ends with the Blogs Playground step DONE (not error)
   and the app holds the published blog — recorded here.

## Done

Proof commit: (this commit)   Proof fingerprint: 17ca65a9fafb   Auditor verdict: <pending>   Docs updated: STATE.md

Live evidence: POST /api/blog/import with run_critique=false returned HTTP 200 in 0.06s and created
a blog (vs 60s+ timeout with critique). A full 'draft and publish a blog' run ended with the Blogs
Playground step status=ok (no deadline error).
