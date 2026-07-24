# Task: selector-schema-safety

Status: in progress
Type: bugfix
Scope: src/orchestrator/contract.py, src/orchestrator/selector.py, tools/refresh_openapi.py, registry/apps.json, tests/unit/**, tests/contract/openapi/**, STATE.md
Phase: Phase 2 — Fix 1 of the web-fallback deep-dive (plan: ~/.claude/plans/before-going-to-solutions-modular-lampson.md)

## Goal

A task like "write a short blog" is served BY Blogs Playground instead of 422-ing into web
fallback. The selector stops sending wrongly-typed arguments to apps: it sees each field's real
type, wrongly-typed values are coerced when safe and dropped otherwise, and the two unsafe
duplicate blog-generate ops are removed so the safe async op is the only generate path.
(Completes what 20260713-async-payload-fix started; root cause: selector is schema-blind —
live proof was `word_count_target: "short"` → 422 int_parsing → web fallback.)

## Acceptance criteria

Each one names the test that proves it.

1. Snapshots carry field types: `slim_from_openapi` extracts a `types` map per endpoint
   (path/query params + body properties, anyOf/Optional resolved) — proven by
   `tests/unit/test_contract.py::test_slim_extracts_field_types`.
2. The selector's operation view includes those types so the model fills fields correctly —
   proven by `tests/unit/test_selector.py::test_operations_view_includes_field_types`.
3. Wrongly-typed arguments never reach an app: safe coercions applied ("5"→5, "true"→True);
   an uncoercible OPTIONAL field is dropped; an uncoercible REQUIRED field is dropped so the
   existing missing-required skip fires (honest skip, no garbage call) — proven by
   `tests/unit/test_selector.py::test_wrong_type_optional_dropped`,
   `::test_numeric_string_coerced`, `::test_wrong_type_required_dropped_causes_skip`.
4. Blogs Playground exposes exactly ONE generate op (`generate_blog_async`);
   `post_blog_generate` and `post_blog_generate_streaming` are gone — proven by
   `tests/unit/test_registry.py::test_blogs_single_generate_op`.
5. `make verify` PASS; decomposition eval unchanged (16/16 — op-level change, planner untouched).
6. Live (user acceptance): "write a short blog about X" produced BY Blogs Playground, no
   fallback banner, across repeated runs.

## Plan (before coding)

1. contract.py `slim_from_openapi`: also emit `"types": {field: jsonschema-type}` per endpoint
   (param `schema.type`; body property `type`, resolving `$ref` and `anyOf` Optional[...]).
   `check_op` unchanged (types are additive; old snapshots without `types` stay valid).
2. tools/refresh_openapi.py: no code change needed (it serializes whatever slim returns);
   re-run against live apps to regenerate all snapshots with types.
3. selector.py: `_operations_view` merges each op's field types from its app snapshot
   (reuse contract.load_snapshot/snapshot_path; missing snapshot → no types, unchanged view);
   after `_parse_selection`, a new `_enforce_field_types(op, args, types)` coerces safe cases
   and drops uncoercible values (optional AND required — required-dropped then hits the
   existing executor skip with its honest "missing required input" reason).
4. registry/apps.json: delete `post_blog_generate` + `post_blog_generate_streaming` from
   blogs-playground. Sweep the other 10 apps for the same unsafe-duplicate pattern (an async
   op with trimmed fields + sync duplicates exposing type-risky fields) and list findings here.
5. Tests per acceptance criteria; failing test first for the 422 scenario (criterion 3).
6. `make verify`; user live-tests (criterion 6); then STATE.md + close 20260713 as superseded.

## Sweep findings (step 4)

Swept all apps with async ops for unsafe sync duplicates (POST/PUT ops with >=4 request fields):
- blogs-playground: `post_blog_generate` + `post_blog_generate_streaming` — TRUE duplicates of
  `generate_blog_async` (same pipeline, 7 type-risky fields). REMOVED; endpoints recorded as
  deliberately-unwired in test_registry_coverage.py with rationale.
- blogs-playground `post_blog_iterate_paragraph` / `post_blog_publish_wordpress` / `put_style`,
  research-assistant `post_disagreements` / `post_notes`: distinct functions, NOT duplicates —
  kept; now protected by the new value-level type gate anyway.
- Registry op count: blogs-playground 37 -> 35. No other app had a duplicate pattern.

Supersedes: 20260713-async-payload-fix (was "in progress"; its trimmed async request_fields are
confirmed in place and its remaining gap — the sync duplicates — is closed by this task).

## Failure analysis

(none — clean run)

## Done

All acceptance criteria met. `make verify` PASS (proofs/latest.json, fingerprint fc03445a2178).
Unit 809 passing (5 new). Live-verified: "write a short blog about the future of agentic AI in
enterprises" produced BY Blogs Playground via `generate_blog_async` (source port 8010, 81 healthy
polls, no fallback banner) — the exact task class that previously 422'd to web. Decomposition eval
unchanged. Supersedes 20260713-async-payload-fix.

Proof commit: <this commit>   Auditor verdict: <pending>   Docs updated: STATE.md
