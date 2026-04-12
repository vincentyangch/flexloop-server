"""Unit tests for OpenAICodexAdapter."""
from __future__ import annotations

from types import SimpleNamespace

import httpx
import openai
import pytest

from flexloop.ai.codex_auth import (
    CodexAuthMalformed,
    CodexAuthMissing,
    CodexAuthWrongMode,
)
from flexloop.ai.openai_codex_adapter import OpenAICodexAdapter
from tests.fixtures.auth_json_factory import make_auth_json


def _usage():
    return SimpleNamespace(
        prompt_tokens=11,
        completion_tokens=7,
        prompt_tokens_details=SimpleNamespace(cached_tokens=3),
    )


def _stream_chunk(delta: str | None = None, usage=None):
    choices = []
    if delta is not None:
        choices = [SimpleNamespace(delta=SimpleNamespace(content=delta))]
    return SimpleNamespace(choices=choices, usage=usage)


def _responses_result():
    return SimpleNamespace(
        output="responses ok",
        usage=SimpleNamespace(
            input_tokens=13,
            output_tokens=5,
            input_tokens_details={"cached_tokens": 2},
        ),
    )


class FakeChatCompletions:
    def __init__(self, owner: "FakeAsyncOpenAI") -> None:
        self._owner = owner

    async def create(self, **kwargs):
        FakeAsyncOpenAI.chat_requests.append(
            {"api_key": self._owner.api_key, "kwargs": kwargs}
        )
        if FakeAsyncOpenAI.chat_error is not None:
            raise FakeAsyncOpenAI.chat_error

        async def _stream():
            yield _stream_chunk("codex ")
            yield _stream_chunk("ok")
            yield _stream_chunk(usage=_usage())

        return _stream()


class FakeResponses:
    def __init__(self, owner: "FakeAsyncOpenAI") -> None:
        self._owner = owner

    async def create(self, **kwargs):
        FakeAsyncOpenAI.responses_requests.append(
            {"api_key": self._owner.api_key, "kwargs": kwargs}
        )
        return _responses_result()


class FakeAsyncOpenAI:
    instances: list["FakeAsyncOpenAI"] = []
    chat_requests: list[dict] = []
    responses_requests: list[dict] = []
    chat_error: Exception | None = None

    def __init__(self, *, api_key: str, base_url: str | None = None) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.chat = SimpleNamespace(completions=FakeChatCompletions(self))
        self.responses = FakeResponses(self)
        FakeAsyncOpenAI.instances.append(self)

    @classmethod
    def reset(cls) -> None:
        cls.instances = []
        cls.chat_requests = []
        cls.responses_requests = []
        cls.chat_error = None


@pytest.fixture(autouse=True)
def fake_openai(monkeypatch):
    FakeAsyncOpenAI.reset()
    monkeypatch.setattr(
        "flexloop.ai.openai_codex_adapter.AsyncOpenAI", FakeAsyncOpenAI
    )
    yield
    FakeAsyncOpenAI.reset()


def _adapter(auth_file, reasoning_effort: str = "medium") -> OpenAICodexAdapter:
    return OpenAICodexAdapter(
        model="gpt-5.1-codex-max",
        auth_file=str(auth_file),
        reasoning_effort=reasoning_effort,
    )


@pytest.mark.asyncio
async def test_generate_reads_token_from_auth_file(tmp_path):
    auth_file = make_auth_json(tmp_path / "auth.json", access_token="token-A")
    adapter = _adapter(auth_file)

    response = await adapter.generate("system", "user")

    assert response.content == "codex ok"
    assert FakeAsyncOpenAI.chat_requests[-1]["api_key"] == "token-A"
    assert adapter.api_key == "codex-oauth-placeholder"
    assert adapter.base_url == ""


@pytest.mark.asyncio
async def test_generate_rereads_token_per_call(tmp_path):
    auth_file = make_auth_json(tmp_path / "auth.json", access_token="token-A")
    adapter = _adapter(auth_file)

    await adapter.generate("system", "user")
    make_auth_json(auth_file, access_token="token-B")
    await adapter.generate("system", "user")

    assert FakeAsyncOpenAI.chat_requests[0]["api_key"] == "token-A"
    assert FakeAsyncOpenAI.chat_requests[1]["api_key"] == "token-B"


@pytest.mark.asyncio
async def test_auth_missing_raises_through_generate(tmp_path):
    adapter = _adapter(tmp_path / "missing.json")

    with pytest.raises(CodexAuthMissing):
        await adapter.generate("system", "user")

    assert FakeAsyncOpenAI.responses_requests == []


@pytest.mark.asyncio
async def test_401_from_client_propagates(tmp_path):
    auth_file = make_auth_json(tmp_path / "auth.json")
    request = httpx.Request("POST", "https://api.openai.test/chat")
    response = httpx.Response(401, request=request)
    FakeAsyncOpenAI.chat_error = openai.AuthenticationError(
        "bad token", response=response, body=None
    )

    with pytest.raises(openai.AuthenticationError):
        await _adapter(auth_file).generate("system", "user")

    assert FakeAsyncOpenAI.responses_requests == []


@pytest.mark.asyncio
async def test_stream_generate_reads_token_and_streams(tmp_path):
    auth_file = make_auth_json(tmp_path / "auth.json", access_token="stream-token")
    adapter = _adapter(auth_file)

    events = [event async for event in adapter.stream_generate("system", "user")]

    assert [event.type for event in events] == ["content", "content", "usage", "done"]
    assert [event.delta for event in events[:2]] == ["codex ", "ok"]
    assert events[2].input_tokens == 11
    assert events[2].output_tokens == 7
    assert events[2].cache_read_tokens == 3
    assert FakeAsyncOpenAI.chat_requests[-1]["api_key"] == "stream-token"


@pytest.mark.asyncio
async def test_chat_completions_reasoning_effort_medium_top_level(tmp_path):
    auth_file = make_auth_json(tmp_path / "auth.json")

    await _adapter(auth_file, reasoning_effort="medium").generate("system", "user")

    kwargs = FakeAsyncOpenAI.chat_requests[-1]["kwargs"]
    assert kwargs["reasoning_effort"] == "medium"
    assert "reasoning" not in kwargs


@pytest.mark.asyncio
async def test_chat_completions_reasoning_effort_high_top_level(tmp_path):
    auth_file = make_auth_json(tmp_path / "auth.json")

    await _adapter(auth_file, reasoning_effort="high").generate("system", "user")

    kwargs = FakeAsyncOpenAI.chat_requests[-1]["kwargs"]
    assert kwargs["reasoning_effort"] == "high"


@pytest.mark.asyncio
async def test_chat_completions_reasoning_effort_none_not_injected(tmp_path):
    auth_file = make_auth_json(tmp_path / "auth.json")

    await _adapter(auth_file, reasoning_effort="none").generate("system", "user")

    kwargs = FakeAsyncOpenAI.chat_requests[-1]["kwargs"]
    assert "reasoning_effort" not in kwargs


@pytest.mark.asyncio
async def test_chat_completions_no_nested_reasoning_object(tmp_path):
    auth_file = make_auth_json(tmp_path / "auth.json")

    await _adapter(auth_file, reasoning_effort="medium").generate("system", "user")

    assert "reasoning" not in FakeAsyncOpenAI.chat_requests[-1]["kwargs"]


@pytest.mark.asyncio
async def test_responses_api_reasoning_effort_medium_nested(tmp_path):
    auth_file = make_auth_json(tmp_path / "auth.json")
    FakeAsyncOpenAI.chat_error = RuntimeError("chat completions unavailable")

    response = await _adapter(auth_file, reasoning_effort="medium").generate(
        "system", "user"
    )

    kwargs = FakeAsyncOpenAI.responses_requests[-1]["kwargs"]
    assert response.content == "responses ok"
    assert kwargs["reasoning"] == {"effort": "medium"}
    assert "reasoning_effort" not in kwargs


@pytest.mark.asyncio
async def test_responses_api_reasoning_effort_none_not_injected(tmp_path):
    auth_file = make_auth_json(tmp_path / "auth.json")
    FakeAsyncOpenAI.chat_error = RuntimeError("chat completions unavailable")

    await _adapter(auth_file, reasoning_effort="none").generate("system", "user")

    kwargs = FakeAsyncOpenAI.responses_requests[-1]["kwargs"]
    assert "reasoning" not in kwargs


@pytest.mark.asyncio
async def test_responses_api_no_top_level_reasoning_effort(tmp_path):
    auth_file = make_auth_json(tmp_path / "auth.json")
    FakeAsyncOpenAI.chat_error = RuntimeError("chat completions unavailable")

    await _adapter(auth_file, reasoning_effort="medium").generate("system", "user")

    assert "reasoning_effort" not in FakeAsyncOpenAI.responses_requests[-1]["kwargs"]


def test_reraise_exceptions_class_attribute():
    assert OpenAICodexAdapter._RERAISE_EXCEPTIONS == (
        CodexAuthMissing,
        CodexAuthMalformed,
        CodexAuthWrongMode,
        openai.AuthenticationError,
    )
