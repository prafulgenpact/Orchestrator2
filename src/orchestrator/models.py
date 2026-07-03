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
