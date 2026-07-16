"""Unit tests for credential resolution and the client factory (no network).

Every test points ORCHESTRATOR_FALLBACK_ENV at a controlled path so the real
sibling .env is never read, and clears the Foundry env vars for a clean baseline.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.llm import get_client
from orchestrator.llm.base import LLMError, LLMRequest
from orchestrator.llm.foundry import (
    DEFAULT_LLM_TIMEOUT_S,
    DEFAULT_MODEL,
    FoundryClient,
    _extract_text,
    _parse_env_file,
    resolve_credentials,
    resolve_llm_timeout,
    resolve_model,
)
from orchestrator.llm.replay import RecordingClient, ReplayClient

FOUNDRY_ENV = ("ANTHROPIC_FOUNDRY_API_KEY", "ANTHROPIC_FOUNDRY_BASE_URL")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    extra = ("ANTHROPIC_MODEL", "ORCHESTRATOR_MODEL", "ORCHESTRATOR_LLM_TIMEOUT_S")
    for var in (*FOUNDRY_ENV, *extra):
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


def test_resolve_llm_timeout_default() -> None:
    # _clean_env (autouse) cleared ORCHESTRATOR_LLM_TIMEOUT_S
    assert resolve_llm_timeout() == DEFAULT_LLM_TIMEOUT_S


def test_resolve_llm_timeout_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORCHESTRATOR_LLM_TIMEOUT_S", "42")
    assert resolve_llm_timeout() == 42.0


def test_resolve_llm_timeout_rejects_bad_values(monkeypatch: pytest.MonkeyPatch) -> None:
    for bad in ("", "not-a-number", "0", "-5"):
        monkeypatch.setenv("ORCHESTRATOR_LLM_TIMEOUT_S", bad)
        assert resolve_llm_timeout() == DEFAULT_LLM_TIMEOUT_S, bad


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


# --- LLMRequest tool fields: opt-in, hash-preserving -------------------------


def test_to_dict_omits_tool_fields_when_unset() -> None:
    # A tools-free request must serialize EXACTLY as before (same keys) so its request_hash
    # is byte-identical — this is what guarantees the planner/grounding/synthesis fixtures
    # do not need re-recording when the selector adopts tool-use.
    req = LLMRequest(model="m", system="s", messages=({"role": "user", "content": "hi"},))
    assert req.to_dict() == {
        "model": "m",
        "system": "s",
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": req.max_tokens,
    }


def test_to_dict_includes_tool_fields_when_set() -> None:
    tool = {"name": "pick", "input_schema": {"type": "object"}}
    choice = {"type": "tool", "name": "pick"}
    req = LLMRequest(
        model="m",
        system="s",
        messages=({"role": "user", "content": "hi"},),
        tools=(tool,),
        tool_choice=choice,
    )
    data = req.to_dict()
    assert data["tools"] == [tool]
    assert data["tool_choice"] == choice


# --- _extract_text: tool-use -> canonical JSON; truncation -> clear error -----


class _Block:
    # Mimics an Anthropic content block: attributes are .type / .text / .input (params renamed
    # to avoid shadowing the `type`/`input` builtins — ruff A002).
    def __init__(self, kind: str, text: str | None = None, value: object | None = None) -> None:
        self.type = kind
        self.text = text
        self.input = value


class _Msg:
    def __init__(self, content: list[_Block], stop_reason: str = "end_turn") -> None:
        self.content = content
        self.stop_reason = stop_reason


def test_extract_tool_use_returns_json() -> None:
    payload = {"operation": "execute_code", "arguments": {"code": "print('hi')\nx = 1"}}
    msg = _Msg([_Block("tool_use", value=payload)], stop_reason="tool_use")
    raw = _extract_text(msg, expect_tool=True)
    # The returned string is guaranteed-valid JSON (it came from the structured tool input,
    # not free text) — even though the code argument contains a raw newline.
    import json as _json

    assert _json.loads(raw) == payload


def test_extract_raises_on_truncation() -> None:
    msg = _Msg([_Block("tool_use", value={"partial": True})], stop_reason="max_tokens")
    with pytest.raises(LLMError, match="truncated"):
        _extract_text(msg, expect_tool=True)


def test_extract_raises_when_no_tool_use() -> None:
    msg = _Msg([_Block("text", text="I refuse to use the tool")], stop_reason="end_turn")
    with pytest.raises(LLMError, match="tool_use"):
        _extract_text(msg, expect_tool=True)


def test_extract_text_joins_text_blocks() -> None:
    msg = _Msg([_Block("text", text="foo"), _Block("text", text="bar")])
    assert _extract_text(msg, expect_tool=False) == "foobar"


def test_extract_text_no_text_raises() -> None:
    msg = _Msg([_Block("tool_use", value={})])
    with pytest.raises(LLMError, match="no text content"):
        _extract_text(msg, expect_tool=False)
