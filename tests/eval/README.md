# Decomposition eval

Measures how well the planner decomposes a task and routes each subtask to the right app.
It's the number we use to judge planner-prompt / app-card changes, instead of eyeballing one task.

## Files

- `cases.json` — labelled cases. Per case: `task`, `must_include` (apps that MUST be chosen),
  `must_not_include` (apps that MUST NOT be), `min_subtasks`/`max_subtasks`, and a `note`.
- `test_decomposition.py` — replays each case through `plan_task` and asserts those expectations.
  A case with no recorded fixture **skips** (so `make verify` is green before recording).
- `record.sh` — records a fixture per case via the real model (needs credentials + network).
- `fixtures/` — recorded planner responses (committed; safe — request + response text only).

## Workflow

```bash
# 1. record fixtures once (live model)
bash tests/eval/record.sh

# 2. score offline (no network, no key) — also runs inside `make verify`
PYTHONPATH=src python -m pytest tests/eval -v
```

A failing case is a **misroute or a bad subtask count** — read the assertion message: it names
the case, the apps expected/forbidden, and the count. Fix the app card or the planner prompt,
re-record that case, and re-run.

## Adding a case

Append to `cases.json` (keep `id` unique, use real app ids from `registry/apps.json`), then
`bash tests/eval/record.sh` to record its fixture.
