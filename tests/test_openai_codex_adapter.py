"""Unit tests for OpenAICodexAdapter."""
from __future__ import annotations

import base64
import json
from types import SimpleNamespace

import httpx
import openai
import pytest

from flexloop.ai.codex_auth import (
    CodexAuthMalformed,
    CodexAuthMissing,
    CodexAuthWrongMode,
)
from flexloop.ai.openai_codex_adapter import (
    OpenAICodexAdapter,
    _extract_chatgpt_account_id,
)
from tests.fixtures.auth_json_factory import make_auth_json, make_openclaw_auth_profiles


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


def _responses_stream_event(delta: str):
    return SimpleNamespace(type="response.output_text.delta", delta=delta)


def _responses_completed_event(input_tokens=13, output_tokens=5, output=None):
    return SimpleNamespace(
        type="response.completed",
        response=SimpleNamespace(
            usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
            output=output or [],
        ),
    )


def _error_event(message="something broke"):
    return SimpleNamespace(type="error", message=message, error=message)


def _failed_event(message="content filter triggered"):
    return SimpleNamespace(
        type="response.failed",
        response=SimpleNamespace(
            status="failed",
            error=SimpleNamespace(message=message),
        ),
    )


def _incomplete_event():
    return SimpleNamespace(
        type="response.incomplete",
        response=SimpleNamespace(status="incomplete", error=None),
    )


def _function_call_output_item(
    call_id="call_1", item_id="fc_001", name="my_tool", arguments='{"key":"val"}',
):
    return SimpleNamespace(
        type="function_call",
        call_id=call_id,
        id=item_id,
        name=name,
        arguments=arguments,
    )


def _message_output_item():
    return SimpleNamespace(type="message")


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
        if FakeAsyncOpenAI.responses_error is not None:
            raise FakeAsyncOpenAI.responses_error

        output = FakeAsyncOpenAI.responses_output
        custom = FakeAsyncOpenAI.responses_stream_events

        async def _stream():
            if custom is not None:
                for ev in custom:
                    yield ev
            else:
                yield _responses_stream_event("codex ")
                yield _responses_stream_event("ok")
                yield _responses_completed_event(output=output)

        return _stream()


class FakeAsyncOpenAI:
    instances: list["FakeAsyncOpenAI"] = []
    chat_requests: list[dict] = []
    responses_requests: list[dict] = []
    chat_error: Exception | None = None
    responses_error: Exception | None = None
    responses_output: list | None = None
    responses_stream_events: list | None = None

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.default_headers = default_headers
        self.chat = SimpleNamespace(completions=FakeChatCompletions(self))
        self.responses = FakeResponses(self)
        FakeAsyncOpenAI.instances.append(self)

    @classmethod
    def reset(cls) -> None:
        cls.instances = []
        cls.chat_requests = []
        cls.responses_requests = []
        cls.chat_error = None
        cls.responses_error = None
        cls.responses_output = None
        cls.responses_stream_events = None


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


def _make_chatgpt_jwt(account_id: str = "acct_test123") -> str:
    """Build a fake ChatGPT JWT containing chatgpt_account_id."""
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "none"}).encode()
    ).rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(
        json.dumps({
            "https://api.openai.com/auth": {
                "chatgpt_account_id": account_id,
            },
        }).encode()
    ).rstrip(b"=").decode()
    return f"{header}.{payload}.sig"


@pytest.mark.asyncio
async def test_generate_reads_token_from_auth_file(tmp_path):
    auth_file = make_auth_json(tmp_path / "auth.json", access_token="token-A")
    adapter = _adapter(auth_file)

    response = await adapter.generate("system", "user")

    assert response.content == "codex ok"
    assert FakeAsyncOpenAI.responses_requests[-1]["api_key"] == "token-A"
    assert adapter.api_key == "codex-oauth-placeholder"
    assert adapter.base_url == ""
    # Per-request client must route through the ChatGPT backend Codex endpoint
    assert FakeAsyncOpenAI.instances[-1].base_url == (
        "https://chatgpt.com/backend-api/codex"
    )


@pytest.mark.asyncio
async def test_generate_rereads_token_per_call(tmp_path):
    auth_file = make_auth_json(tmp_path / "auth.json", access_token="token-A")
    adapter = _adapter(auth_file)

    await adapter.generate("system", "user")
    make_auth_json(auth_file, access_token="token-B")
    await adapter.generate("system", "user")

    assert FakeAsyncOpenAI.responses_requests[0]["api_key"] == "token-A"
    assert FakeAsyncOpenAI.responses_requests[1]["api_key"] == "token-B"


@pytest.mark.asyncio
async def test_auth_missing_raises_through_generate(tmp_path):
    adapter = _adapter(tmp_path / "missing.json")

    with pytest.raises(CodexAuthMissing):
        await adapter.generate("system", "user")

    assert FakeAsyncOpenAI.responses_requests == []


@pytest.mark.asyncio
async def test_401_from_client_propagates(tmp_path):
    auth_file = make_auth_json(tmp_path / "auth.json")
    request = httpx.Request("POST", "https://api.openai.test/responses")
    response = httpx.Response(401, request=request)
    FakeAsyncOpenAI.responses_error = openai.AuthenticationError(
        "bad token", response=response, body=None
    )

    with pytest.raises(openai.AuthenticationError):
        await _adapter(auth_file).generate("system", "user")


@pytest.mark.asyncio
async def test_stream_generate_reads_token_and_streams(tmp_path):
    auth_file = make_auth_json(tmp_path / "auth.json", access_token="stream-token")
    adapter = _adapter(auth_file)

    events = [event async for event in adapter.stream_generate("system", "user")]

    assert [event.type for event in events] == ["content", "content", "usage", "done"]
    assert [event.delta for event in events[:2]] == ["codex ", "ok"]
    assert events[2].input_tokens == 13
    assert events[2].output_tokens == 5
    assert events[2].cache_read_tokens == 0
    assert FakeAsyncOpenAI.responses_requests[-1]["api_key"] == "stream-token"


@pytest.mark.asyncio
async def test_responses_api_reasoning_effort_medium_nested(tmp_path):
    auth_file = make_auth_json(tmp_path / "auth.json")

    response = await _adapter(auth_file, reasoning_effort="medium").generate(
        "system", "user"
    )

    kwargs = FakeAsyncOpenAI.responses_requests[-1]["kwargs"]
    assert response.content == "codex ok"
    assert kwargs["reasoning"] == {"effort": "medium"}
    assert "reasoning_effort" not in kwargs


@pytest.mark.asyncio
async def test_responses_api_reasoning_effort_high_nested(tmp_path):
    auth_file = make_auth_json(tmp_path / "auth.json")

    await _adapter(auth_file, reasoning_effort="high").generate("system", "user")

    kwargs = FakeAsyncOpenAI.responses_requests[-1]["kwargs"]
    assert kwargs["reasoning"] == {"effort": "high"}


@pytest.mark.asyncio
async def test_responses_api_reasoning_effort_none_not_injected(tmp_path):
    auth_file = make_auth_json(tmp_path / "auth.json")

    await _adapter(auth_file, reasoning_effort="none").generate("system", "user")

    kwargs = FakeAsyncOpenAI.responses_requests[-1]["kwargs"]
    assert "reasoning" not in kwargs


@pytest.mark.asyncio
async def test_responses_api_no_top_level_reasoning_effort(tmp_path):
    auth_file = make_auth_json(tmp_path / "auth.json")

    await _adapter(auth_file, reasoning_effort="medium").generate("system", "user")

    assert "reasoning_effort" not in FakeAsyncOpenAI.responses_requests[-1]["kwargs"]


@pytest.mark.asyncio
async def test_responses_api_requires_store_false(tmp_path):
    auth_file = make_auth_json(tmp_path / "auth.json")

    await _adapter(auth_file).generate("system", "user")

    kwargs = FakeAsyncOpenAI.responses_requests[-1]["kwargs"]
    assert kwargs["store"] is False


@pytest.mark.asyncio
async def test_responses_api_requires_stream_true(tmp_path):
    auth_file = make_auth_json(tmp_path / "auth.json")

    await _adapter(auth_file).generate("system", "user")

    kwargs = FakeAsyncOpenAI.responses_requests[-1]["kwargs"]
    assert kwargs["stream"] is True


@pytest.mark.asyncio
async def test_responses_api_input_is_list(tmp_path):
    auth_file = make_auth_json(tmp_path / "auth.json")

    await _adapter(auth_file).generate("sys", "hello")

    kwargs = FakeAsyncOpenAI.responses_requests[-1]["kwargs"]
    assert kwargs["input"] == [{"role": "user", "content": "hello"}]


@pytest.mark.asyncio
async def test_temperature_and_max_tokens_not_sent(tmp_path):
    """Codex backend rejects both temperature and max_output_tokens."""
    auth_file = make_auth_json(tmp_path / "auth.json")

    await _adapter(auth_file).generate("sys", "hi", temperature=0.3, max_tokens=50)

    kwargs = FakeAsyncOpenAI.responses_requests[-1]["kwargs"]
    assert "temperature" not in kwargs
    assert "max_output_tokens" not in kwargs
    assert "max_tokens" not in kwargs


def test_reraise_exceptions_class_attribute():
    assert OpenAICodexAdapter._RERAISE_EXCEPTIONS == (
        CodexAuthMissing,
        CodexAuthMalformed,
        CodexAuthWrongMode,
        openai.AuthenticationError,
    )


# ---- ChatGPT-Account-ID header tests ----


@pytest.mark.asyncio
async def test_chatgpt_account_id_header_sent_when_jwt_has_claim(tmp_path):
    jwt_token = _make_chatgpt_jwt("acct_abc")
    auth_file = make_auth_json(tmp_path / "auth.json", access_token=jwt_token)

    await _adapter(auth_file).generate("system", "user")

    client = FakeAsyncOpenAI.instances[-1]
    assert client.default_headers == {"ChatGPT-Account-ID": "acct_abc"}
    assert FakeAsyncOpenAI.responses_requests[-1]["api_key"] == jwt_token


@pytest.mark.asyncio
async def test_chatgpt_account_id_header_absent_for_non_jwt_token(tmp_path):
    auth_file = make_auth_json(tmp_path / "auth.json", access_token="plain-token")

    await _adapter(auth_file).generate("system", "user")

    client = FakeAsyncOpenAI.instances[-1]
    assert client.default_headers is None


@pytest.mark.asyncio
async def test_openclaw_account_id_from_profile_not_jwt(tmp_path):
    """OpenClaw profiles store accountId in the file, not the JWT.

    The adapter must read it from the auth file via read_credential(),
    not rely on JWT extraction alone.
    """
    auth_file = make_openclaw_auth_profiles(
        tmp_path / "auth-profiles.json",
        access_token="opaque-token-no-jwt",
        account_id="acct_openclaw_77",
    )

    await _adapter(auth_file).generate("system", "user")

    client = FakeAsyncOpenAI.instances[-1]
    assert client.default_headers == {"ChatGPT-Account-ID": "acct_openclaw_77"}


@pytest.mark.asyncio
async def test_codex_cli_account_id_from_tokens_object(tmp_path):
    """Codex CLI may store account_id in the tokens dict."""
    auth_file = tmp_path / "auth.json"
    make_auth_json(auth_file, access_token="plain-token")
    data = json.loads(auth_file.read_text())
    data["tokens"]["account_id"] = "acct_cli_55"
    auth_file.write_text(json.dumps(data))

    await _adapter(auth_file).generate("system", "user")

    client = FakeAsyncOpenAI.instances[-1]
    assert client.default_headers == {"ChatGPT-Account-ID": "acct_cli_55"}


# ---- _extract_chatgpt_account_id unit tests ----


def test_extract_account_id_from_valid_jwt():
    token = _make_chatgpt_jwt("acct_42")
    assert _extract_chatgpt_account_id(token) == "acct_42"


def test_extract_account_id_returns_none_for_plain_string():
    assert _extract_chatgpt_account_id("not-a-jwt") is None


def test_extract_account_id_returns_none_for_missing_claim():
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(b'{"sub":"user"}').rstrip(b"=").decode()
    assert _extract_chatgpt_account_id(f"{header}.{payload}.sig") is None


def test_extract_account_id_returns_none_for_non_string_value():
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(
        json.dumps({
            "https://api.openai.com/auth": {"chatgpt_account_id": 12345},
        }).encode()
    ).rstrip(b"=").decode()
    assert _extract_chatgpt_account_id(f"{header}.{payload}.sig") is None


# ---- tool_use tests ----


def _tool_def():
    from flexloop.ai.base import ToolDef
    return ToolDef(
        name="replace_exercise",
        description="Replace an exercise",
        input_schema={"type": "object", "properties": {"name": {"type": "string"}}},
    )


@pytest.mark.asyncio
async def test_tool_use_sends_responses_api_with_tools(tmp_path):
    auth_file = make_auth_json(tmp_path / "auth.json")
    FakeAsyncOpenAI.responses_output = [
        _function_call_output_item(call_id="call_1", name="replace_exercise", arguments='{"name":"squat"}'),
    ]

    response = await _adapter(auth_file).tool_use(
        system_prompt="sys",
        messages=[{"role": "user", "content": "swap it"}],
        tools=[_tool_def()],
        tool_choice="auto",
    )

    kwargs = FakeAsyncOpenAI.responses_requests[-1]["kwargs"]
    # Codex backend constraints
    assert kwargs["store"] is False
    assert kwargs["stream"] is True
    # Tools in Responses API format (flat, not nested)
    assert kwargs["tools"][0]["type"] == "function"
    assert kwargs["tools"][0]["name"] == "replace_exercise"
    assert "function" not in kwargs["tools"][0]  # not Chat Completions nested format
    # Input is a list
    assert kwargs["input"] == [{"role": "user", "content": "swap it"}]


@pytest.mark.asyncio
async def test_tool_use_extracts_tool_calls(tmp_path):
    auth_file = make_auth_json(tmp_path / "auth.json")
    FakeAsyncOpenAI.responses_output = [
        _function_call_output_item(call_id="call_A", name="replace_exercise", arguments='{"name":"deadlift"}'),
        _function_call_output_item(call_id="call_B", name="replace_exercise", arguments='{"name":"bench"}'),
    ]

    response = await _adapter(auth_file).tool_use(
        system_prompt="sys",
        messages=[{"role": "user", "content": "swap two"}],
        tools=[_tool_def()],
    )

    assert len(response.tool_calls) == 2
    assert response.tool_calls[0].id == "call_A"
    assert response.tool_calls[0].name == "replace_exercise"
    assert response.tool_calls[0].input == {"name": "deadlift"}
    assert response.tool_calls[1].id == "call_B"
    assert response.stop_reason == "tool_calls"


@pytest.mark.asyncio
async def test_tool_use_no_tool_calls_returns_stop(tmp_path):
    auth_file = make_auth_json(tmp_path / "auth.json")
    FakeAsyncOpenAI.responses_output = [_message_output_item()]

    response = await _adapter(auth_file).tool_use(
        system_prompt="sys",
        messages=[{"role": "user", "content": "just talk"}],
        tools=[_tool_def()],
    )

    assert response.tool_calls == []
    assert response.stop_reason == "stop"
    assert response.text == "codex ok"


@pytest.mark.asyncio
async def test_tool_use_round_trip_messages(tmp_path):
    """Content from tool_use() can be round-tripped back as assistant message."""
    auth_file = make_auth_json(tmp_path / "auth.json")
    FakeAsyncOpenAI.responses_output = [
        _function_call_output_item(
            "call_1", item_id="fc_99", name="replace_exercise",
            arguments='{"name":"squat"}',
        ),
    ]

    first = await _adapter(auth_file).tool_use(
        system_prompt="sys",
        messages=[{"role": "user", "content": "swap"}],
        tools=[_tool_def()],
    )

    # Verify round-trip content preserves both id and call_id
    fc_item = first.content[0]
    assert fc_item["id"] == "fc_99"
    assert fc_item["call_id"] == "call_1"

    # Simulate the refiner's round-trip
    round_trip_messages = [
        {"role": "user", "content": "swap"},
        {"role": "assistant", "content": first.content},
        {"role": "tool_results", "results": [
            {"tool_use_id": "call_1", "content": '{"status":"ok"}'},
        ]},
    ]

    FakeAsyncOpenAI.responses_output = [_message_output_item()]
    await _adapter(auth_file).tool_use(
        system_prompt="sys",
        messages=round_trip_messages,
        tools=[_tool_def()],
    )

    kwargs = FakeAsyncOpenAI.responses_requests[-1]["kwargs"]
    input_msgs = kwargs["input"]
    # User message
    assert input_msgs[0] == {"role": "user", "content": "swap"}
    # Round-tripped function call — must include both id and call_id
    assert input_msgs[1]["type"] == "function_call"
    assert input_msgs[1]["id"] == "fc_99"
    assert input_msgs[1]["call_id"] == "call_1"
    assert input_msgs[1]["name"] == "replace_exercise"
    # Tool result
    assert input_msgs[2]["type"] == "function_call_output"
    assert input_msgs[2]["call_id"] == "call_1"


@pytest.mark.asyncio
async def test_tool_use_round_trip_with_text_and_calls(tmp_path):
    """When model returns text + function calls, text uses role:assistant format."""
    auth_file = make_auth_json(tmp_path / "auth.json")
    FakeAsyncOpenAI.responses_output = [
        _message_output_item(),
        _function_call_output_item("call_X", item_id="fc_X", name="replace_exercise",
                                   arguments='{"name":"lunge"}'),
    ]

    resp = await _adapter(auth_file).tool_use(
        system_prompt="sys",
        messages=[{"role": "user", "content": "swap and explain"}],
        tools=[_tool_def()],
    )

    # Content has both assistant text and function_call items
    assert len(resp.content) == 2
    assert resp.content[0] == {"role": "assistant", "content": "codex ok"}
    assert resp.content[1]["type"] == "function_call"
    assert resp.content[1]["id"] == "fc_X"

    # Round-trip them back
    round_trip = [
        {"role": "user", "content": "swap and explain"},
        {"role": "assistant", "content": resp.content},
        {"role": "tool_results", "results": [
            {"tool_use_id": "call_X", "content": '{"ok":true}'},
        ]},
    ]

    FakeAsyncOpenAI.responses_output = [_message_output_item()]
    await _adapter(auth_file).tool_use(
        system_prompt="sys", messages=round_trip, tools=[_tool_def()],
    )

    input_msgs = FakeAsyncOpenAI.responses_requests[-1]["kwargs"]["input"]
    # user → assistant text → function_call → function_call_output
    assert input_msgs[0] == {"role": "user", "content": "swap and explain"}
    assert input_msgs[1] == {"role": "assistant", "content": "codex ok"}
    assert input_msgs[2]["type"] == "function_call"
    assert input_msgs[3]["type"] == "function_call_output"


@pytest.mark.asyncio
async def test_tool_use_multiple_message_items_no_duplicate(tmp_path):
    """Multiple message output items must not duplicate the assistant text."""
    auth_file = make_auth_json(tmp_path / "auth.json")
    FakeAsyncOpenAI.responses_output = [
        _message_output_item(),
        _message_output_item(),  # two message items in output
        _function_call_output_item(call_id="call_Z", name="replace_exercise",
                                   arguments='{"name":"squat"}'),
    ]

    resp = await _adapter(auth_file).tool_use(
        system_prompt="sys",
        messages=[{"role": "user", "content": "go"}],
        tools=[_tool_def()],
    )

    text_items = [i for i in resp.content if i.get("role") == "assistant"]
    assert len(text_items) == 1, f"Expected 1 text item, got {len(text_items)}"


@pytest.mark.asyncio
async def test_tool_use_choice_any_maps_to_required(tmp_path):
    auth_file = make_auth_json(tmp_path / "auth.json")
    FakeAsyncOpenAI.responses_output = [
        _function_call_output_item(),
    ]

    await _adapter(auth_file).tool_use(
        system_prompt="sys",
        messages=[{"role": "user", "content": "do it"}],
        tools=[_tool_def()],
        tool_choice="any",
    )

    kwargs = FakeAsyncOpenAI.responses_requests[-1]["kwargs"]
    assert kwargs["tool_choice"] == "required"


@pytest.mark.asyncio
async def test_tool_use_does_not_send_temperature(tmp_path):
    auth_file = make_auth_json(tmp_path / "auth.json")
    FakeAsyncOpenAI.responses_output = [_message_output_item()]

    await _adapter(auth_file).tool_use(
        system_prompt="sys",
        messages=[{"role": "user", "content": "go"}],
        tools=[_tool_def()],
        temperature=0.2,
    )

    kwargs = FakeAsyncOpenAI.responses_requests[-1]["kwargs"]
    assert "temperature" not in kwargs
    assert "max_output_tokens" not in kwargs


@pytest.mark.asyncio
async def test_stream_generate_does_not_send_temperature(tmp_path):
    auth_file = make_auth_json(tmp_path / "auth.json")

    events = [e async for e in _adapter(auth_file).stream_generate("sys", "hi", temperature=0.1)]

    kwargs = FakeAsyncOpenAI.responses_requests[-1]["kwargs"]
    assert "temperature" not in kwargs
    assert "max_output_tokens" not in kwargs
    assert events[0].type == "content"


# ---- stream error event tests ----


@pytest.mark.asyncio
async def test_generate_raises_on_stream_error_event(tmp_path):
    auth_file = make_auth_json(tmp_path / "auth.json")
    FakeAsyncOpenAI.responses_stream_events = [
        _responses_stream_event("partial"),
        _error_event("rate limit exceeded"),
    ]

    with pytest.raises(RuntimeError, match="rate limit exceeded"):
        await _adapter(auth_file).generate("sys", "hi")


@pytest.mark.asyncio
async def test_generate_raises_on_response_failed(tmp_path):
    auth_file = make_auth_json(tmp_path / "auth.json")
    FakeAsyncOpenAI.responses_stream_events = [
        _responses_stream_event("partial"),
        _failed_event("content filter triggered"),
    ]

    with pytest.raises(RuntimeError, match="content filter triggered"):
        await _adapter(auth_file).generate("sys", "hi")


@pytest.mark.asyncio
async def test_generate_raises_on_response_incomplete(tmp_path):
    auth_file = make_auth_json(tmp_path / "auth.json")
    FakeAsyncOpenAI.responses_stream_events = [
        _responses_stream_event("partial"),
        _incomplete_event(),
    ]

    with pytest.raises(RuntimeError, match="incomplete"):
        await _adapter(auth_file).generate("sys", "hi")


@pytest.mark.asyncio
async def test_stream_generate_yields_error_on_stream_error(tmp_path):
    auth_file = make_auth_json(tmp_path / "auth.json")
    FakeAsyncOpenAI.responses_stream_events = [
        _responses_stream_event("partial"),
        _error_event("server overloaded"),
    ]

    events = [e async for e in _adapter(auth_file).stream_generate("sys", "hi")]

    types = [e.type for e in events]
    assert "content" in types
    assert "error" in types
    assert types[-1] == "done"
    error_ev = next(e for e in events if e.type == "error")
    assert "server overloaded" in error_ev.error


@pytest.mark.asyncio
async def test_stream_generate_yields_error_on_response_failed(tmp_path):
    auth_file = make_auth_json(tmp_path / "auth.json")
    FakeAsyncOpenAI.responses_stream_events = [
        _failed_event("content filter"),
    ]

    events = [e async for e in _adapter(auth_file).stream_generate("sys", "hi")]

    types = [e.type for e in events]
    assert "error" in types
    assert types[-1] == "done"


@pytest.mark.asyncio
async def test_tool_use_raises_on_stream_error(tmp_path):
    auth_file = make_auth_json(tmp_path / "auth.json")
    FakeAsyncOpenAI.responses_stream_events = [
        _error_event("bad request"),
    ]

    with pytest.raises(RuntimeError, match="bad request"):
        await _adapter(auth_file).tool_use(
            system_prompt="sys",
            messages=[{"role": "user", "content": "go"}],
            tools=[_tool_def()],
        )
