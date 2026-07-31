"""Unit tests for the web connector's event contract (backend calls monkeypatched — no network)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import pytest

from orchestrator import web
from orchestrator.llm.base import LLMClient
from orchestrator.registry import Registry


@dataclass
class _Sub:
    id: str
    depends_on: tuple[str, ...] = ()


@dataclass
class _Plan:
    subtasks: list[_Sub]

    def to_dict(self) -> dict[str, Any]:
        return {"subtasks": [s.id for s in self.subtasks]}


@dataclass
class _Res:
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return self.data


@dataclass
class _PlanResult:
    results: tuple[_Res, ...]


@dataclass
class _Synth:
    answer: str
    sources: tuple[str, ...]
    mode: str


def _install_fakes(monkeypatch: pytest.MonkeyPatch, *, fail: str | None = None) -> None:
    """Replace plan/execute/synthesize with deterministic in-memory doubles."""

    def fake_plan_task(client: Any, registry: Any, task: str, *, model: str) -> _Plan:
        _ = (client, registry, task, model)  # accepted to match the real signature
        if fail == "plan":
            raise RuntimeError("planner boom")
        return _Plan([_Sub("t1"), _Sub("t2", ("t1",))])

    def fake_execute(
        plan: Any, registry: Any, client: Any, model: str, progress: Any, on_result: Any
    ) -> _PlanResult:
        _ = (plan, registry, client, model)
        if fail == "execute":
            raise RuntimeError("executor boom")
        progress("-> t1")
        on_result(_Res({"subtask_id": "t1", "status": "ok"}))  # streamed mid-run, not after
        progress("[ok] t1 (0.5s)")
        return _PlanResult(())

    def fake_synthesize(
        client: Any, plan_result: Any, *, model: str, subtask_deps: Any = None, on_delta: Any = None
    ) -> _Synth:
        _ = (client, plan_result, model, subtask_deps)
        if on_delta is not None:
            on_delta("Hello")
            on_delta(" world")
        return _Synth("Hello world", ("http://example/x",), "synthesized")

    monkeypatch.setattr(web, "plan_task", fake_plan_task)
    monkeypatch.setattr(web, "_execute_plan_sync", fake_execute)
    monkeypatch.setattr(web, "synthesize", fake_synthesize)


def _run() -> list[web.Event]:
    return list(
        web.run_events(
            "do it", client=cast(LLMClient, object()), registry=cast(Registry, object()), model="m"
        )
    )


def test_run_events_order(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fakes(monkeypatch)
    events = _run()
    names = [name for name, _ in events]

    assert names[0] == "status"
    assert names[1] == "plan"
    assert names[-2] == "final"
    assert names[-1] == "done"
    for name in ("progress", "result", "answer"):
        assert name in names
    assert (
        names.index("plan")
        < names.index("progress")
        < names.index("result")
        < names.index("answer")
        < names.index("final")
    )

    final = dict(events)["final"]
    assert final["answer"] == "Hello world"
    assert final["sources"] == ["http://example/x"]


def test_run_events_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fakes(monkeypatch, fail="plan")
    events = _run()

    assert [name for name, _ in events] == ["status", "error", "done"]
    assert dict(events)["error"]["stage"] == "plan"


def test_run_events_execute_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fakes(monkeypatch, fail="execute")
    events = _run()
    names = [name for name, _ in events]

    assert names[:2] == ["status", "plan"]
    assert names[-1] == "done"
    assert "error" in names
    assert dict(events)["error"]["stage"] == "execute"


def test_sse_format() -> None:
    assert web.sse("plan", {"a": 1}) == b'event: plan\ndata: {"a": 1}\n\n'


def test_ui_path_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    page = tmp_path / "x.html"
    monkeypatch.setenv("ATELIER_UI", str(page))
    assert web.ui_path() == page

    monkeypatch.delenv("ATELIER_UI", raising=False)
    assert web.ui_path() == web.DEFAULT_UI
