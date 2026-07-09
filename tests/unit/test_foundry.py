"""Unit tests for credential resolution and the client factory (no network).

Every test points ORCHESTRATOR_FALLBACK_ENV at a controlled path so the real
sibling .env is never read, and clears the Foundry env vars for a clean baseline.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.llm import get_client
from orchestrator.llm.base import LLMError
from orchestrator.llm.foundry import (
    DEFAULT_MODEL,
    FoundryClient,
    _parse_env_file,
    resolve_credentials,
    resolve_model,
)
from orchestrator.llm.replay import RecordingClient, ReplayClient

FOUNDRY_ENV = ("ANTHROPIC_FOUNDRY_API_KEY", "ANTHROPIC_FOUNDRY_BASE_URL")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for var in (*FOUNDRY_ENV, "ANTHROPIC_MODEL", "ORCHESTRATOR_MODEL"):
        monkeypatch.delenv(var, raising=False)
    # default: point the fallback at a non-existent file so nothing leaks in
    monkeypatch.setenv("ORCHESTRATOR_FALLBACK_ENV", str(tmp_path / "absent.env"))


def _set_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_FOUNDRY_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_FOUNDRY_BASE_URL", "https://foundry.example/api")


# --- _parse_env_file ---------------------------------------------------------


def test_parse_env_file_handles_comments_blanks_and_quotes(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "# a comment\n"
        "\n"
        'ANTHROPIC_FOUNDRY_API_KEY="quoted-key"\n'
        "ANTHROPIC_FOUNDRY_BASE_URL = https://x/api \n"
        "NOT_A_PAIR\n"
    )
    parsed = _parse_env_file(env)
    assert parsed["ANTHROPIC_FOUNDRY_API_KEY"] == "quoted-key"
    assert parsed["ANTHROPIC_FOUNDRY_BASE_URL"] == "https://x/api"
    assert "NOT_A_PAIR" not in parsed


def test_parse_env_file_missing_returns_empty(tmp_path: Path) -> None:
    assert _parse_env_file(tmp_path / "nope.env") == {}


# --- resolve_credentials -----------------------------------------------------


def test_resolve_from_process_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_creds(monkeypatch)
    creds = resolve_credentials()
    assert creds.api_key == "test-key"
    assert creds.base_url == "https://foundry.example/api"


def test_resolve_from_fallback_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    env = tmp_path / "fallback.env"
    env.write_text(
        "ANTHROPIC_FOUNDRY_API_KEY=file-key\n" "ANTHROPIC_FOUNDRY_BASE_URL=https://file/api\n"
    )
    monkeypatch.setenv("ORCHESTRATOR_FALLBACK_ENV", str(env))
    creds = resolve_credentials()
    assert creds.api_key == "file-key"
    assert creds.base_url == "https://file/api"


def test_resolve_from_project_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # With no explicit override, the project-local .env is consulted automatically.
    monkeypatch.delenv("ORCHESTRATOR_FALLBACK_ENV", raising=False)
    project = tmp_path / "project.env"
    project.write_text(
        "ANTHROPIC_FOUNDRY_API_KEY=proj-key\n" "ANTHROPIC_FOUNDRY_BASE_URL=https://proj/api\n"
    )
    monkeypatch.setattr("orchestrator.llm.foundry.PROJECT_ENV", project)
    monkeypatch.setattr("orchestrator.llm.foundry.DEFAULT_FALLBACK_ENV", tmp_path / "absent.env")
    creds = resolve_credentials()
    assert creds.api_key == "proj-key"
    assert creds.base_url == "https://proj/api"


def test_project_env_beats_sibling_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Project .env outranks the sibling fallback on a key both define.
    monkeypatch.delenv("ORCHESTRATOR_FALLBACK_ENV", raising=False)
    project = tmp_path / "project.env"
    project.write_text(
        "ANTHROPIC_FOUNDRY_API_KEY=proj\n" "ANTHROPIC_FOUNDRY_BASE_URL=https://proj/api\n"
    )
    sibling = tmp_path / "sibling.env"
    sibling.write_text(
        "ANTHROPIC_FOUNDRY_API_KEY=sib\n" "ANTHROPIC_FOUNDRY_BASE_URL=https://sib/api\n"
    )
    monkeypatch.setattr("orchestrator.llm.foundry.PROJECT_ENV", project)
    monkeypatch.setattr("orchestrator.llm.foundry.DEFAULT_FALLBACK_ENV", sibling)
    creds = resolve_credentials()
    assert creds.api_key == "proj"  # project wins over sibling
    assert creds.base_url == "https://proj/api"


def test_explicit_override_ignores_project_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # An explicit ORCHESTRATOR_FALLBACK_ENV is the SOLE fallback — the project .env is skipped.
    project = tmp_path / "project.env"
    project.write_text(
        "ANTHROPIC_FOUNDRY_API_KEY=proj\n" "ANTHROPIC_FOUNDRY_BASE_URL=https://proj/api\n"
    )
    monkeypatch.setattr("orchestrator.llm.foundry.PROJECT_ENV", project)
    monkeypatch.setenv("ORCHESTRATOR_FALLBACK_ENV", str(tmp_path / "absent.env"))
    with pytest.raises(LLMError, match="missing Foundry credentials"):
        resolve_credentials()


def test_resolve_model_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    assert resolve_model() == DEFAULT_MODEL
    assert resolve_model("explicit") == "explicit"
    monkeypatch.setenv("ORCHESTRATOR_MODEL", "from-orch-env")
    assert resolve_model() == "from-orch-env"
    assert resolve_model("explicit-wins") == "explicit-wins"


def test_missing_credentials_raises() -> None:
    # _clean_env (autouse) already cleared creds and pointed the fallback at nothing
    with pytest.raises(LLMError, match="missing Foundry credentials"):
        resolve_credentials()


# --- get_client factory ------------------------------------------------------


def test_get_client_replay(tmp_path: Path) -> None:
    assert isinstance(get_client("replay", fixture_dir=tmp_path), ReplayClient)


def test_get_client_live(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_creds(monkeypatch)
    assert isinstance(get_client("live"), FoundryClient)


def test_get_client_record(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_creds(monkeypatch)
    assert isinstance(get_client("record", fixture_dir=tmp_path), RecordingClient)


def test_get_client_unknown_mode() -> None:
    with pytest.raises(ValueError, match="unknown LLM mode"):
        get_client("banana")
