"""Load and validate the self-contained app registry.

The registry lists the pre-built apps the orchestrator can route to, plus exactly
one web-search fallback for subtasks no app covers. It ships in this repo so that
planning is deterministic and testable without touching the launcher or the app
folders. The planner shows this registry to the model; validation later checks that
every chosen app_id exists here.

Beyond the planner-facing description, each non-fallback app carries a machine-readable
**call-spec** the executor uses to actually invoke it over HTTP: an app-level ``port``
and ``health`` path, plus one or more ``operations`` (method, path, timeout, retry,
idempotency, destructive flag, notable request fields). The call-spec is deliberately
kept out of ``AppEntry.to_prompt_dict`` so the planner request — and the recorded e2e
fixture keyed on its hash — is unaffected by call-spec changes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REGISTRY_SCHEMA_VERSION = 1
DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "registry" / "apps.json"

_ALLOWED_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})
_ALLOWED_IDEMPOTENCY = frozenset({"supported", "none"})


class RegistryError(ValueError):
    """The registry file is missing, malformed, or fails validation."""


@dataclass(frozen=True)
class RetrySpec:
    """How many times a transient failure is retried, and the base backoff seconds."""

    transient_max: int = 2
    backoff_s: float = 3.0

    def to_dict(self) -> dict[str, Any]:
        return {"transient_max": self.transient_max, "backoff_s": self.backoff_s}


@dataclass(frozen=True)
class AppOperation:
    """One callable HTTP operation on an app, as the executor will invoke it.

    ``path`` is the full path a client calls (any router/mount prefix included).
    ``request_fields`` are the notable request-body field names (a hint for building
    the call), not an authoritative schema — the app's own OpenAPI remains the source
    of truth for exact payloads.
    """

    name: str
    description: str
    method: str
    path: str
    timeout_s: float
    destructive: bool
    idempotency: str
    retry: RetrySpec = field(default_factory=RetrySpec)
    request_fields: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "method": self.method,
            "path": self.path,
            "timeout_s": self.timeout_s,
            "destructive": self.destructive,
            "idempotency": self.idempotency,
            "retry": self.retry.to_dict(),
            "request_fields": list(self.request_fields),
        }


@dataclass(frozen=True)
class AppEntry:
    """One routable app (or the fallback), as described to the planner.

    ``port``/``health``/``operations`` are the executor-facing call-spec: required for
    non-fallback apps, absent for the web-search fallback. They are intentionally NOT
    part of ``to_prompt_dict`` so the planner sees only the descriptive view.
    """

    id: str
    name: str
    description: str
    capabilities: tuple[str, ...]
    example_tasks: tuple[str, ...]
    fallback: bool
    port: int | None = None
    health: str | None = None
    operations: tuple[AppOperation, ...] = ()

    def to_prompt_dict(self) -> dict[str, Any]:
        """Compact, deterministic view handed to the model (no display-only or call-spec fields)."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "capabilities": list(self.capabilities),
            "example_tasks": list(self.example_tasks),
            "fallback": self.fallback,
        }

    @property
    def base_url(self) -> str | None:
        """The app's local base URL, or None for the fallback (no port)."""
        return f"http://127.0.0.1:{self.port}" if self.port is not None else None

    def operation(self, name: str) -> AppOperation | None:
        for op in self.operations:
            if op.name == name:
                return op
        return None


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


def _require_int(value: Any, label: str) -> int:
    # bool is a subclass of int — reject it explicitly.
    if not isinstance(value, int) or isinstance(value, bool):
        raise RegistryError(f"{label} must be an integer")
    return value


def _require_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise RegistryError(f"{label} must be a number")
    return float(value)


def _parse_retry(raw: Any, where: str) -> RetrySpec:
    if raw is None:
        return RetrySpec()
    if not isinstance(raw, dict):
        raise RegistryError(f"{where} retry must be an object")
    transient_max = raw.get("transient_max", RetrySpec.transient_max)
    backoff_s = raw.get("backoff_s", RetrySpec.backoff_s)
    if not isinstance(transient_max, int) or isinstance(transient_max, bool) or transient_max < 0:
        raise RegistryError(f"{where} retry.transient_max must be a non-negative integer")
    if isinstance(backoff_s, bool) or not isinstance(backoff_s, int | float) or backoff_s < 0:
        raise RegistryError(f"{where} retry.backoff_s must be a non-negative number")
    return RetrySpec(transient_max=int(transient_max), backoff_s=float(backoff_s))


def _parse_operation(raw: Any, app_id: str, index: int) -> AppOperation:
    where = f"app '{app_id}' operation #{index}"
    if not isinstance(raw, dict):
        raise RegistryError(f"{where} must be a JSON object")
    name = _require_str(raw.get("name"), f"{where} name")
    method = _require_str(raw.get("method"), f"{where} ({name}) method").upper()
    if method not in _ALLOWED_METHODS:
        raise RegistryError(
            f"{where} ({name}) method must be one of {sorted(_ALLOWED_METHODS)}, got {method!r}"
        )
    path = _require_str(raw.get("path"), f"{where} ({name}) path")
    if not path.startswith("/"):
        raise RegistryError(f"{where} ({name}) path must start with '/', got {path!r}")
    timeout_s = _require_number(raw.get("timeout_s"), f"{where} ({name}) timeout_s")
    if timeout_s <= 0:
        raise RegistryError(f"{where} ({name}) timeout_s must be > 0")
    idempotency = _require_str(raw.get("idempotency"), f"{where} ({name}) idempotency")
    if idempotency not in _ALLOWED_IDEMPOTENCY:
        raise RegistryError(
            f"{where} ({name}) idempotency must be one of {sorted(_ALLOWED_IDEMPOTENCY)}"
        )
    return AppOperation(
        name=name,
        description=_require_str(raw.get("description"), f"{where} ({name}) description"),
        method=method,
        path=path,
        timeout_s=timeout_s,
        destructive=bool(raw.get("destructive", False)),
        idempotency=idempotency,
        retry=_parse_retry(raw.get("retry"), f"{where} ({name})"),
        request_fields=_str_list(raw.get("request_fields", []), f"{where} ({name}) request_fields"),
    )


def _parse_app(raw: Any) -> AppEntry:
    if not isinstance(raw, dict):
        raise RegistryError("each app must be a JSON object")
    if "id" not in raw or "name" not in raw or "description" not in raw:
        raise RegistryError("app is missing a required field (id, name, description)")
    app_id = _require_str(raw["id"], "app id")
    name = _require_str(raw["name"], f"app '{app_id}' name")
    description = _require_str(raw["description"], f"app '{app_id}' description")
    capabilities = _str_list(raw.get("capabilities", []), f"app '{app_id}' capabilities")
    example_tasks = _str_list(raw.get("example_tasks", []), f"app '{app_id}' example_tasks")
    fallback = bool(raw.get("fallback", False))

    port: int | None = None
    if raw.get("port") is not None:
        port = _require_int(raw["port"], f"app '{app_id}' port")
        if not 1 <= port <= 65535:
            raise RegistryError(f"app '{app_id}' port must be in 1..65535, got {port}")

    health: str | None = None
    if raw.get("health") is not None:
        health = _require_str(raw["health"], f"app '{app_id}' health")
        if not health.startswith("/"):
            raise RegistryError(f"app '{app_id}' health must start with '/', got {health!r}")

    ops_raw = raw.get("operations", [])
    if not isinstance(ops_raw, list):
        raise RegistryError(f"app '{app_id}' operations must be a list")
    operations = tuple(_parse_operation(op, app_id, i) for i, op in enumerate(ops_raw))
    op_names = [op.name for op in operations]
    if len(set(op_names)) != len(op_names):
        raise RegistryError(f"app '{app_id}' operation names must be unique")

    if fallback:
        if operations:
            raise RegistryError(f"fallback app '{app_id}' must not declare operations")
    else:
        if port is None:
            raise RegistryError(f"non-fallback app '{app_id}' must declare a 'port'")
        if health is None:
            raise RegistryError(f"non-fallback app '{app_id}' must declare a 'health' path")
        if not operations:
            raise RegistryError(f"non-fallback app '{app_id}' must declare at least one operation")

    return AppEntry(
        id=app_id,
        name=name,
        description=description,
        capabilities=capabilities,
        example_tasks=example_tasks,
        fallback=fallback,
        port=port,
        health=health,
        operations=operations,
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
