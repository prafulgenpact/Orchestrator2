"""Immutable data model for a dry-run orchestration plan.

A Plan is the orchestrator's output for a task: the recognized intent, the subtask
DAG (dependencies encode sequential vs parallel execution), and — per subtask — the
app that would handle it, with rationale and confidence. Nothing here invokes an
app; this is the dry-run contract.

Tuples (not lists) are used for the collection fields so instances are deeply
immutable and hashable, matching the frozen dataclasses.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class AppSelection:
    """The app chosen to handle one subtask (dry run — never invoked).

    app_name and fallback are denormalized from the registry at validation time,
    never trusted from the model. fallback is True for the web-search catch-all.
    """

    app_id: str
    app_name: str
    rationale: str
    confidence: float
    fallback: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "app_id": self.app_id,
            "app_name": self.app_name,
            "rationale": self.rationale,
            "confidence": self.confidence,
            "fallback": self.fallback,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppSelection:
        return cls(
            app_id=data["app_id"],
            app_name=data["app_name"],
            rationale=data["rationale"],
            confidence=float(data["confidence"]),
            fallback=bool(data["fallback"]),
        )


@dataclass(frozen=True)
class Subtask:
    """One decomposed unit of work, its chosen app, and its dependencies.

    depends_on lists the ids of subtasks that must complete first. An empty
    depends_on means the subtask can start immediately; subtasks with the same
    satisfied dependencies form a parallel wave (computed by the renderer).
    """

    id: str
    title: str
    description: str
    depends_on: tuple[str, ...]
    app: AppSelection

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "depends_on": list(self.depends_on),
            "app": self.app.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Subtask:
        return cls(
            id=data["id"],
            title=data["title"],
            description=data["description"],
            depends_on=tuple(data.get("depends_on", [])),
            app=AppSelection.from_dict(data["app"]),
        )


@dataclass(frozen=True)
class Plan:
    """The full dry-run plan for a single task."""

    task: str
    intent: str
    subtasks: tuple[Subtask, ...]
    model: str
    prompt_version: str
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task": self.task,
            "intent": self.intent,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "subtasks": [s.to_dict() for s in self.subtasks],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Plan:
        return cls(
            task=data["task"],
            intent=data["intent"],
            subtasks=tuple(Subtask.from_dict(s) for s in data["subtasks"]),
            model=data["model"],
            prompt_version=data["prompt_version"],
            schema_version=int(data.get("schema_version", SCHEMA_VERSION)),
        )


@dataclass(frozen=True)
class Artifact:
    """A non-text output an app produced — today a chart. Carried alongside the text answer so it
    survives the pipeline's text length caps (which would otherwise truncate a chart to nothing).

    ``kind`` is "chart" for now. ``spec`` is the app's chart-ready data (e.g. a box-plot's
    quartiles), rendered to a picture later. ``title`` labels it; ``subtask_id`` ties it to the
    step that produced it.
    """

    kind: str
    title: str
    spec: dict[str, Any]
    subtask_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "title": self.title,
            "spec": self.spec,
            "subtask_id": self.subtask_id,
        }


@dataclass(frozen=True)
class SubtaskResult:
    """The outcome of executing one subtask against its chosen app.

    ``status`` is "ok" (app returned a result), "error" (call/selection failed), or
    "skipped" (not executed — e.g. the web-search fallback, deferred). ``output`` is the
    app's real response; ``source`` is the URL it came from (provenance for grounding).
    ``artifacts`` carries any charts the app produced (kept out of the text answer so they are
    never truncated) — trailing + defaulted because SubtaskResult is built positionally everywhere.
    """

    subtask_id: str
    app_id: str
    app_name: str
    status: str
    operation: str | None
    output: Any
    source: str | None
    error: str | None
    duration_s: float
    note: str | None = None  # disclosure, e.g. "<app> couldn't answer; used web fallback"
    artifacts: tuple[Artifact, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "subtask_id": self.subtask_id,
            "app_id": self.app_id,
            "app_name": self.app_name,
            "status": self.status,
            "operation": self.operation,
            "output": self.output,
            "source": self.source,
            "error": self.error,
            "duration_s": round(self.duration_s, 3),
            "note": self.note,
            "artifacts": [a.to_dict() for a in self.artifacts],
        }


@dataclass(frozen=True)
class PlanResult:
    """The result of executing a Plan: the app output for each subtask, with provenance."""

    task: str
    intent: str
    results: tuple[SubtaskResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "intent": self.intent,
            "results": [r.to_dict() for r in self.results],
        }
