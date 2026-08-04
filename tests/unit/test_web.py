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


def _install_fakes(
    monkeypatch: pytest.MonkeyPatch, *, fail: str | None = None
) -> list[dict[str, Any]]:
    """Replace plan/execute/synthesize/record_run with deterministic in-memory doubles.

    Returns the list of record_run calls (one kwargs dict each) so tests can assert every web run
    is recorded — the connector's always-log contract."""

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

    record_calls: list[dict[str, Any]] = []

    def fake_record_run(plan: Any, result: Any, synth: Any, **kwargs: Any) -> str:
        record_calls.append({"plan": plan, "result": result, "synth": synth, **kwargs})
        return "rid"

    monkeypatch.setattr(web, "plan_task", fake_plan_task)
    monkeypatch.setattr(web, "_execute_plan_sync", fake_execute)
    monkeypatch.setattr(web, "synthesize", fake_synthesize)
    monkeypatch.setattr(web, "record_run", fake_record_run)
    return record_calls


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


def test_is_benign_disconnect_true_for_client_hangups() -> None:
    assert web._is_benign_disconnect(ConnectionResetError()) is True
    assert web._is_benign_disconnect(BrokenPipeError()) is True
    assert web._is_benign_disconnect(ConnectionAbortedError()) is True


def test_is_benign_disconnect_false_for_real_errors() -> None:
    assert web._is_benign_disconnect(ValueError("boom")) is False
    assert web._is_benign_disconnect(RuntimeError()) is False
    assert web._is_benign_disconnect(None) is False


def _res(status: str, output: Any, artifacts: tuple[Any, ...] = ()) -> Any:
    from orchestrator.models import SubtaskResult

    return SubtaskResult(
        "t",
        "coding-playground",
        "Coding",
        status,
        "run_code",
        output,
        None,
        None,
        0.0,
        artifacts=artifacts,
    )


def _plan_result(*results: Any) -> Any:
    from orchestrator.models import PlanResult

    return PlanResult(task="t", intent="i", results=tuple(results))


def test_collect_images_gathers_dedupes_and_caps() -> None:
    pr = _plan_result(
        _res("ok", {"text": "done", "images": ["AAA", "BBB"]}),
        _res("error", {"images": ["ZZZ"]}),  # failed step -> ignored
        _res("ok", {"images": ["BBB", "CCC"]}),  # BBB duplicate -> deduped
        _res("ok", "just text"),  # non-dict output -> skipped
    )
    assert web._collect_images(pr) == ["AAA", "BBB", "CCC"]


def test_collect_images_caps_at_limit() -> None:
    pr = _plan_result(_res("ok", {"images": [str(i) for i in range(20)]}))
    assert len(web._collect_images(pr, limit=8)) == 8


def test_collect_images_empty_when_no_charts() -> None:
    assert web._collect_images(_plan_result(_res("ok", {"text": "no charts"}))) == []


def _chart_artifact(title: str = "Histogram", spec: dict[str, Any] | None = None) -> Any:
    from orchestrator.models import Artifact

    return Artifact(
        "chart", title, spec or {"type": "histogram", "bins": [0, 1, 2], "counts": [3, 4]}, "t"
    )


def test_result_payload_renders_chart_svg() -> None:
    r = _res("ok", {"bins": [0, 1, 2], "counts": [3, 4]}, artifacts=(_chart_artifact(),))
    payload = web._result_payload(r)

    assert payload["subtask_id"] == "t"  # the base to_dict fields are intact
    svg = payload["artifacts"][0]["svg"]
    assert svg.startswith("<svg") and "Histogram" in svg


def test_result_payload_skips_unknown_chart_shapes() -> None:
    unknown = _chart_artifact(spec={"mystery": 42})
    payload = web._result_payload(_res("ok", {"mystery": 42}, artifacts=(unknown,)))

    assert "svg" not in payload["artifacts"][0]  # spec table stays the honest view


def test_result_payload_no_artifacts_passthrough() -> None:
    r = _res("ok", {"text": "plain"})
    assert web._result_payload(r) == r.to_dict()


def test_collect_chart_svgs_gathers_dedupes_and_caps() -> None:
    hist = _chart_artifact()
    scatter = _chart_artifact("Scatter", {"type": "scatter", "x": [1], "y": [2]})
    pr = _plan_result(
        _res("ok", {}, artifacts=(hist, scatter)),
        _res("error", {}, artifacts=(_chart_artifact("Failed"),)),  # failed step -> ignored
        _res("ok", {}, artifacts=(hist,)),  # identical chart -> deduped
    )
    svgs = web._collect_chart_svgs(pr)

    assert len(svgs) == 2
    assert all(s.startswith("<svg") for s in svgs)


def test_collect_chart_svgs_caps_at_limit() -> None:
    arts = tuple(_chart_artifact(f"C{i}") for i in range(10))
    pr = _plan_result(_res("ok", {}, artifacts=arts))
    assert len(web._collect_chart_svgs(pr, limit=3)) == 3


def test_final_event_carries_charts_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fakes(monkeypatch)
    final = dict(_run())["final"]
    assert final["charts"] == []  # present (empty here — the fake run makes no charts)


def test_run_events_records_run(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _install_fakes(monkeypatch)
    events = _run()

    assert [name for name, _ in events][-1] == "done"
    assert len(calls) == 1
    call = calls[0]
    assert call["exit_code"] == 0
    assert call["mode"] == "live"
    assert call["result"] is not None and call["synth"] is not None
    assert call["started_at"] <= call["ended_at"]


def test_run_events_records_execute_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _install_fakes(monkeypatch, fail="execute")
    _run()

    assert len(calls) == 1
    assert calls[0]["exit_code"] == 1
    assert calls[0]["result"] is None


def test_run_events_no_record_without_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _install_fakes(monkeypatch, fail="plan")
    _run()

    assert calls == []  # planning failed -> there is no plan object to record


def test_record_failure_never_breaks_the_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fakes(monkeypatch)

    def boom(*args: Any, **kwargs: Any) -> str:
        _ = (args, kwargs)  # accepted to match the real signature
        raise OSError("disk full")

    monkeypatch.setattr(web, "record_run", boom)
    events = _run()
    assert [name for name, _ in events][-1] == "done"  # the browser still gets its answer
