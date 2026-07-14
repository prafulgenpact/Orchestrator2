"""Decomposition eval: score the planner against labelled cases (offline, replay).

Each case in ``cases.json`` says which app(s) the planner MUST choose, which it MUST NOT,
and a sensible subtask-count range. This module does two things:

  * ``test_cases_wellformed`` — the dataset is valid (unique ids, real app ids, sane bounds).
  * ``test_decomposition_case`` — replay ``plan_task`` for one case and assert its expectations.

Routing is model-driven, so accuracy is proven by RECORDED fixtures, not by mocking our own
logic. A case with no recorded fixture SKIPS (never errors), so ``make verify`` stays green
before fixtures exist; record them with ``tests/eval/record.sh`` to turn skips into real checks.

The request built here is identical to the CLI's dry-run request (same registry, model, and
prompt), so a fixture recorded via ``python -m orchestrator "<task>"`` replays here by hash.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from orchestrator.llm.foundry import resolve_model
from orchestrator.llm.replay import MissingFixtureError, ReplayClient
from orchestrator.planner import plan_task
from orchestrator.registry import load_registry

HERE = Path(__file__).parent
FIXTURES = HERE / "fixtures"
_RAW: dict[str, Any] = json.loads((HERE / "cases.json").read_text())
CASES: list[dict[str, Any]] = _RAW["cases"]

REGISTRY = load_registry()
VALID_IDS = set(REGISTRY.ids())
MODEL = resolve_model(None)


def test_cases_wellformed() -> None:
    assert len(CASES) >= 15, "want at least 15 labelled cases"
    seen: set[str] = set()
    for case in CASES:
        cid = str(case["id"])
        assert cid not in seen, f"duplicate case id {cid!r}"
        seen.add(cid)
        assert str(case["task"]).strip(), f"{cid}: empty task"
        for key in ("must_include", "must_not_include"):
            for app_id in case[key]:
                assert app_id in VALID_IDS, f"{cid}: unknown app id {app_id!r} in {key}"
        lo, hi = int(case["min_subtasks"]), int(case["max_subtasks"])
        assert 1 <= lo <= hi, f"{cid}: bad subtask bounds {lo}..{hi}"


@pytest.mark.parametrize("case", CASES, ids=[str(c["id"]) for c in CASES])
def test_decomposition_case(case: dict[str, Any]) -> None:
    client = ReplayClient(fixture_dir=FIXTURES)
    try:
        plan = plan_task(client, REGISTRY, str(case["task"]), model=MODEL)
    except MissingFixtureError:
        pytest.skip(f"no fixture for {case['id']!r} — record with tests/eval/record.sh")

    used = {s.app.app_id for s in plan.subtasks}

    missing = set(case["must_include"]) - used
    assert (
        not missing
    ), f"{case['id']}: expected apps not chosen {sorted(missing)}; got {sorted(used)}"

    forbidden = set(case["must_not_include"]) & used
    assert not forbidden, f"{case['id']}: forbidden apps chosen {sorted(forbidden)}"

    n = len(plan.subtasks)
    lo, hi = int(case["min_subtasks"]), int(case["max_subtasks"])
    assert lo <= n <= hi, f"{case['id']}: {n} subtasks, expected {lo}..{hi}"
