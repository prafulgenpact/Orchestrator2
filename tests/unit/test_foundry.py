"""Unit tests for credential resolution and the client factory (no network).

Every test points ORCHESTRATOR_FALLBACK_ENV at a controlled path so the real
sibling .env is never read, and clears the Foundry env vars for a clean baseline.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from orchestrator.llm import get_client
from orchestrator.llm.base import LLMError, LLMRequest
from orchestrator.llm.foundry import (
    DEFAULT_LLM_TIMEOUT_S,
    DEFAULT_MODEL,
    FoundryClient,
    FoundryCredentials,
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


def test_default_temperature_is_zero() -> None:
    req = LLMRequest(model="m", system="s", messages=({"role": "user", "content": "hi"},))
    assert req.temperature == 0.0  # deterministic by default


def test_request_temperature_is_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    # The temperature on the request must actually reach the Anthropic streaming call.
    captured: dict[str, Any] = {}

    class _Stream:
        text_stream: tuple[str, ...] = ()

        def __enter__(self) -> _Stream:
            return self

        def __exit__(self, *_a: object) -> bool:
            return False

        def get_final_message(self) -> _Msg:
            return _Msg([_Block("text", text="ok")])

    class _Messages:
        def stream(self, **kwargs: Any) -> _Stream:
            captured.update(kwargs)
            return _Stream()

    class _Client:
        messages = _Messages()

        def __init__(self, **_kw: Any) -> None:
            pass

    fake = types.SimpleNamespace(AnthropicFoundry=lambda **kw: _Client(**kw))
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    client = FoundryClient(FoundryCredentials(api_key="k", base_url="http://x"))
    out = client.complete(
        LLMRequest(model="m", system="s", messages=({"role": "u", "content": "h"},))
    )
    assert out == "ok"
    assert captured["temperature"] == 0.0


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


# --- complete(): streaming (progress-based, no total stopwatch) + no self-retry ----------------


class _FakeStream:
    """Mimics the SDK streaming context manager: ``text_stream`` yields the text deltas (each a
    read that resets the inactivity clock); ``get_final_message()`` returns the final Message."""

    def __init__(self, message: _Msg, text_pieces: tuple[str, ...]) -> None:
        self._message = message
        self.text_stream = list(text_pieces)

    def __enter__(self) -> _FakeStream:
        return self

    def __exit__(self, *_a: object) -> bool:
        return False

    def get_final_message(self) -> _Msg:
        return self._message


class _FakeMessages:
    def __init__(
        self, message: _Msg, captured: dict[str, Any], text_pieces: tuple[str, ...]
    ) -> None:
        self._message = message
        self._captured = captured
        self._text = text_pieces

    def stream(self, **kwargs: Any) -> _FakeStream:
        self._captured["stream_kwargs"] = kwargs
        return _FakeStream(self._message, self._text)


def _install_fake_anthropic(
    monkeypatch: pytest.MonkeyPatch, message: _Msg, text_pieces: tuple[str, ...] = ("hel", "lo")
) -> dict[str, Any]:
    """Inject a fake ``anthropic`` module so complete()'s network path runs with no real SDK/key.

    Returns a dict capturing the AnthropicFoundry construction kwargs and the stream() kwargs."""
    captured: dict[str, Any] = {}

    class _FakeFoundry:
        def __init__(self, **kwargs: Any) -> None:
            captured["init_kwargs"] = kwargs
            self.messages = _FakeMessages(message, captured, text_pieces)

    module = types.ModuleType("anthropic")
    module.AnthropicFoundry = _FakeFoundry  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "anthropic", module)
    return captured


def test_complete_stream_emits_deltas(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_creds(monkeypatch)
    # deltas come from the token stream; the returned string is the assembled final message —
    # different sources on purpose, so the test proves both wires are connected.
    msg = _Msg([_Block("text", text="FULL ANSWER")])
    _install_fake_anthropic(monkeypatch, msg, text_pieces=("de", "lta", "s"))
    deltas: list[str] = []
    out = FoundryClient(resolve_credentials()).complete_stream(_req(), deltas.append)
    assert deltas == ["de", "lta", "s"]  # streamed to the callback, in order
    assert out == "FULL ANSWER"  # assembled from the final message


def _req(**extra: Any) -> LLMRequest:
    return LLMRequest(model="m", system="s", messages=({"role": "user", "content": "hi"},), **extra)


def test_complete_streams_text_response(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_creds(monkeypatch)
    msg = _Msg([_Block("text", text="hello "), _Block("text", text="world")])
    _install_fake_anthropic(monkeypatch, msg)
    out = FoundryClient(resolve_credentials()).complete(_req())
    assert out == "hello world"  # assembled from the final streamed message


def test_complete_streams_tool_use_json(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_creds(monkeypatch)
    payload = {"operation": "execute_code", "arguments": {"code": "print(1)\nx = 2"}}
    msg = _Msg([_Block("tool_use", value=payload)], stop_reason="tool_use")
    captured = _install_fake_anthropic(monkeypatch, msg)
    tool = {"name": "pick", "input_schema": {"type": "object"}}
    req = _req(tools=(tool,), tool_choice={"type": "tool", "name": "pick"})
    assert json.loads(FoundryClient(resolve_credentials()).complete(req)) == payload
    assert captured["stream_kwargs"]["tools"] == [tool]  # tools forwarded to the stream call


def test_complete_disables_self_retry_and_sets_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_creds(monkeypatch)
    monkeypatch.setenv("ORCHESTRATOR_LLM_TIMEOUT_S", "42")  # now an inactivity (silence) bound
    captured = _install_fake_anthropic(monkeypatch, _Msg([_Block("text", text="ok")]))
    FoundryClient(resolve_credentials()).complete(_req())
    assert captured["init_kwargs"]["max_retries"] == 0  # no silent self-retry compounding a stall
    assert captured["init_kwargs"]["timeout"] == 42.0
    assert "tools" not in captured["stream_kwargs"]  # omitted when the request has none
