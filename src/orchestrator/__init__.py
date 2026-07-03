"""Dry-run orchestrator: intent -> subtask DAG -> app selection (no invocation).

Given a natural-language task, the orchestrator recognizes the intent, decomposes
it into subtasks, and reports which of the pre-built apps would handle each one.
It is a DRY RUN: it never calls an app. See specs/00-objective.md (AC-1).
"""

from __future__ import annotations

__version__ = "0.1.0"
