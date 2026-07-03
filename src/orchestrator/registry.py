"""Load and validate the self-contained app registry.

The registry lists the pre-built apps the orchestrator can route to, plus exactly
one web-search fallback for subtasks no app covers. It ships in this repo so that
planning is deterministic and testable without touching the launcher or the app
folders. The planner shows this registry to the model; validation later checks that
every chosen app_id exists here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REGISTRY_SCHEMA_VERSION = 1
DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "registry" / "apps.json"


class RegistryError(ValueError):
    """The registry file is missing, malformed, or fails validation."""


@dataclass(frozen=True)
class AppEntry:
    """One routable app (or the fallback), as described to the planner."""

    id: str
    name: str
    description: str
    capabilities: tuple[str, ...]
    example_tasks: tuple[str, ...]
    fallback: bool

    def to_prompt_dict(self) -> dict[str, Any]:
        """Compact, deterministic view handed to the model (no display-only fields)."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "capabilities": list(self.capabilities),
            "example_tasks": list(self.example_tasks),
            "fallback": self.fallback,
        }


@dataclass(frozen=True)
class Registry:
    """The validated set of apps: unique ids, exactly one fallback."""

    apps: tuple[AppEntry, ...]

    def get(self, app_id: str) -> AppEntry | None:
        for app in self.apps:
            if app.id == app_id:
                return app
        return None

    def ids(self) -> tuple[str, ...]:
        return tuple(app.id for app in self.apps)

    @property
    def fallback_id(self) -> str:
        for app in self.apps:
            if app.fallback:
                return app.id
        raise RegistryError("registry has no fallback app")


def _require_str(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RegistryError(f"{label} must be a non-empty string")
    return value


def _str_list(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise RegistryError(f"{label} must be a list of strings")
    return tuple(value)


def _parse_app(raw: Any) -> AppEntry:
    if not isinstance(raw, dict):
        raise RegistryError("each app must be a JSON object")
    if "id" not in raw or "name" not in raw or "description" not in raw:
        raise RegistryError("app is missing a required field (id, name, description)")
    app_id = _require_str(raw["id"], "app id")
    return AppEntry(
        id=app_id,
        name=_require_str(raw["name"], f"app '{app_id}' name"),
        description=_require_str(raw["description"], f"app '{app_id}' description"),
        capabilities=_str_list(raw.get("capabilities", []), f"app '{app_id}' capabilities"),
        example_tasks=_str_list(raw.get("example_tasks", []), f"app '{app_id}' example_tasks"),
        fallback=bool(raw.get("fallback", False)),
    )


def load_registry(path: Path | None = None) -> Registry:
    """Read and validate the registry. Raises RegistryError on any problem."""
    registry_path = path or DEFAULT_REGISTRY_PATH
    try:
        raw_text = registry_path.read_text()
    except OSError as exc:
        raise RegistryError(f"cannot read registry at {registry_path}: {exc}") from exc
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise RegistryError(f"registry is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise RegistryError("registry root must be a JSON object")
    if data.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        raise RegistryError(
            f"unsupported registry schema_version: {data.get('schema_version')!r} "
            f"(expected {REGISTRY_SCHEMA_VERSION})"
        )
    apps_raw = data.get("apps")
    if not isinstance(apps_raw, list) or not apps_raw:
        raise RegistryError("registry 'apps' must be a non-empty list")

    apps = tuple(_parse_app(item) for item in apps_raw)
    app_ids = [app.id for app in apps]
    if len(set(app_ids)) != len(app_ids):
        raise RegistryError("registry app ids must be unique")
    fallback_count = sum(1 for app in apps if app.fallback)
    if fallback_count != 1:
        raise RegistryError(f"registry must have exactly one fallback app, found {fallback_count}")
    return Registry(apps=apps)
