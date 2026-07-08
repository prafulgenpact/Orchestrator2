# Task: depth-data-flow

<!-- Fill Goal/Type/Scope/Acceptance BEFORE any code. This file IS the plan for
     this task; drift_check.py enforces the Scope line mechanically. -->

Status: done
Type: feature
Scope: src/orchestrator/selector.py, src/orchestrator/executor.py, src/orchestrator/prompts/operation_select_system.md, tests/unit/test_selector.py, tests/unit/test_executor.py, plan-depth-orchestration.md, STATE.md
Phase: Phase 2 — depth (plan-depth-orchestration.md, Task 1: data flow between steps)

## Goal

A downstream subtask can use an upstream subtask's result: the operation+argument selector is
given the outputs of the subtasks it depends on, so (e.g.) step 2 can use the arXiv id that step 1
returned. Enables real multi-step orchestration (not independent single calls).

## Acceptance criteria

Each one names the test that proves it.

1. `select_operation` accepts upstream results and includes them in the prompt — proven by
   `tests/unit/test_selector.py` (new).
2. Executor passes each subtask's dependency outputs into selection — proven by
   `tests/unit/test_executor.py` (new).
3. `make verify` PASS (>=90% coverage; e2e replay unchanged).

## Plan (before coding)

The executor already runs subtasks in dependency waves (`compute_waves`) but throws away the
ordering's value: a subtask's result never reaches the subtasks that depend on it. This task adds
that one missing data path.

1. **selector.py** — `select_operation` and `build_select_message` gain an optional
   `upstream: Sequence[SubtaskResult] = ()`. When present, the prompt gets an "UPSTREAM RESULTS"
   block: for each dependency, its `[subtask_id] app_name: <compact output>` (a length-bounded
   JSON/text summary that PRESERVES ids, so a downstream step can pick an id out of it). Argument
   grounding is unchanged — returned args are still filtered to the operation's `request_fields`,
   so upstream can only supply values, never new fields.
2. **operation_select_system.md** — add a rule telling the model it may be given upstream results
   and should pull concrete values (e.g. an id) from them when the subtask refers to earlier work;
   never invent them. Bump prompt `version` to 2 (behavior changed).
3. **executor.py** — keep a `by_id: dict[str, SubtaskResult]`; before selecting a subtask's
   operation, gather its `depends_on` results (only `status == "ok"`) and pass them as `upstream`.
4. Tests (below) prove each AC. `make verify` must stay green (>=90% cov; e2e replay untouched —
   the selector isn't in the hermetic dry-run path).

## Failure analysis

## Done

All three acceptance criteria met:
1. `select_operation` accepts `upstream` and renders it into the prompt — proven by
   `test_message_includes_upstream_list_with_ids`, `test_upstream_output_is_truncated_when_long`,
   `test_select_can_use_upstream_id_as_argument` in tests/unit/test_selector.py.
2. Executor passes each subtask's dependency outputs into selection — proven by
   `test_execute_threads_upstream_output_into_downstream_selection` (and
   `test_execute_skips_failed_upstream`) in tests/unit/test_executor.py.
3. `make verify` PASS — fingerprint ead2014ab0b1, all 10 checks green, coverage >=90%, e2e replay
   unchanged, drift OK.

Proof commit: sealed via `make seal`   Auditor verdict: (pending @auditor)   Docs updated: yes (STATE.md)
