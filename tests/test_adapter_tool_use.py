import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from flexloop.ai.base import ToolDef, ToolCall, ToolUseResponse
from flexloop.ai.anthropic_adapter import AnthropicAdapter
from flexloop.ai.openai_adapter import OpenAIAdapter
from flexloop.ai.ollama_adapter import OllamaAdapter


SWAP_TOOL = ToolDef(
    name="swap_exercise",
    description="Replace one exercise with another",
    input_schema={
        "type": "object",
        "properties": {
            "day_number": {"type": "integer"},
            "exercise_name": {"type": "string"},
            "replacement_name": {"type": "string"},
        },
        "required": ["day_number", "exercise_name", "replacement_name"],
    },
)


# --- Anthropic helpers ---

def _mock_anthropic_response(content_blocks, stop_reason="end_turn"):
    response = MagicMock()
    response.content = content_blocks
    response.stop_reason = stop_reason
    response.usage = MagicMock()
    response.usage.input_tokens = 100
    response.usage.output_tokens = 50
    response.usage.cache_read_input_tokens = 0
    response.usage.cache_creation_input_tokens = 0
    return response


def _text_block(text):
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _tool_use_block(id, name, input_dict):
    block = MagicMock()
    block.type = "tool_use"
    block.id = id
    block.name = name
    block.input = input_dict
    return block


# --- OpenAI helpers ---

def _mock_openai_response(content_text, tool_calls=None, finish_reason="stop"):
    response = MagicMock()
    choice = MagicMock()
    choice.finish_reason = finish_reason
    msg = MagicMock()
    msg.content = content_text
    msg.tool_calls = tool_calls or []
    choice.message = msg
    response.choices = [choice]
    response.usage = MagicMock()
    response.usage.prompt_tokens = 100
    response.usage.completion_tokens = 50
    return response


def _openai_tool_call(id, name, arguments_json):
    tc = MagicMock()
    tc.id = id
    tc.type = "function"
    tc.function = MagicMock()
    tc.function.name = name
    tc.function.arguments = arguments_json
    return tc


# === Anthropic Tests ===

@pytest.mark.asyncio
async def test_anthropic_tool_use_returns_tool_calls():
    adapter = AnthropicAdapter(model="claude-opus-4-6", api_key="test-key")

    tool_block = _tool_use_block(
        "toolu_123", "swap_exercise",
        {"day_number": 1, "exercise_name": "Bench Press", "replacement_name": "Incline DB Press"},
    )
    mock_response = _mock_anthropic_response(
        [_text_block("Here's an alternative:"), tool_block],
        stop_reason="tool_use",
    )

    adapter.client = MagicMock()
    adapter.client.messages = MagicMock()
    adapter.client.messages.create = AsyncMock(return_value=mock_response)

    result = await adapter.tool_use(
        system_prompt="You are a fitness coach.",
        messages=[{"role": "user", "content": "Swap bench press"}],
        tools=[SWAP_TOOL],
        tool_choice="any",
    )

    assert isinstance(result, ToolUseResponse)
    assert result.stop_reason == "tool_use"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "swap_exercise"
    assert result.tool_calls[0].id == "toolu_123"
    assert result.text == "Here's an alternative:"


@pytest.mark.asyncio
async def test_anthropic_tool_use_no_tools_called():
    adapter = AnthropicAdapter(model="claude-opus-4-6", api_key="test-key")

    mock_response = _mock_anthropic_response(
        [_text_block("I can't do that.")],
        stop_reason="end_turn",
    )

    adapter.client = MagicMock()
    adapter.client.messages = MagicMock()
    adapter.client.messages.create = AsyncMock(return_value=mock_response)

    result = await adapter.tool_use(
        system_prompt="You are a fitness coach.",
        messages=[{"role": "user", "content": "Tell me a joke"}],
        tools=[SWAP_TOOL],
    )

    assert result.stop_reason == "end_turn"
    assert len(result.tool_calls) == 0
    assert result.text == "I can't do that."


@pytest.mark.asyncio
async def test_anthropic_tool_use_translates_tool_results():
    """Verify tool_results role is translated to Anthropic format."""
    adapter = AnthropicAdapter(model="claude-opus-4-6", api_key="test-key")

    mock_response = _mock_anthropic_response([_text_block("Done.")], stop_reason="end_turn")

    adapter.client = MagicMock()
    adapter.client.messages = MagicMock()
    adapter.client.messages.create = AsyncMock(return_value=mock_response)

    await adapter.tool_use(
        system_prompt="Coach",
        messages=[
            {"role": "user", "content": "swap it"},
            {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "swap_exercise"}]},
            {"role": "tool_results", "results": [
                {"tool_use_id": "t1", "content": '{"status": "ok"}', "is_error": False},
            ]},
        ],
        tools=[SWAP_TOOL],
    )

    call_args = adapter.client.messages.create.call_args
    messages = call_args.kwargs["messages"]
    # The tool_results message should be translated to a user message with tool_result blocks
    tool_result_msg = messages[-1]
    assert tool_result_msg["role"] == "user"
    assert tool_result_msg["content"][0]["type"] == "tool_result"
    assert tool_result_msg["content"][0]["tool_use_id"] == "t1"


# === OpenAI Tests ===

@pytest.mark.asyncio
async def test_openai_tool_use_returns_tool_calls():
    adapter = OpenAIAdapter(model="gpt-4o", api_key="test-key")

    tc = _openai_tool_call(
        "call_123", "swap_exercise",
        json.dumps({"day_number": 1, "exercise_name": "Bench Press", "replacement_name": "Incline DB Press"}),
    )
    mock_response = _mock_openai_response("Here's an alternative:", [tc], "tool_calls")

    adapter.client = MagicMock()
    adapter.client.chat = MagicMock()
    adapter.client.chat.completions = MagicMock()
    adapter.client.chat.completions.create = AsyncMock(return_value=mock_response)

    result = await adapter.tool_use(
        system_prompt="You are a fitness coach.",
        messages=[{"role": "user", "content": "Swap bench press"}],
        tools=[SWAP_TOOL],
        tool_choice="any",
    )

    assert isinstance(result, ToolUseResponse)
    assert result.stop_reason == "tool_calls"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "swap_exercise"
    assert result.tool_calls[0].input["day_number"] == 1


@pytest.mark.asyncio
async def test_openai_tool_use_no_tools():
    adapter = OpenAIAdapter(model="gpt-4o", api_key="test-key")

    mock_response = _mock_openai_response("I can't do that.", [], "stop")

    adapter.client = MagicMock()
    adapter.client.chat = MagicMock()
    adapter.client.chat.completions = MagicMock()
    adapter.client.chat.completions.create = AsyncMock(return_value=mock_response)

    result = await adapter.tool_use(
        system_prompt="You are a fitness coach.",
        messages=[{"role": "user", "content": "Tell me a joke"}],
        tools=[SWAP_TOOL],
    )

    assert result.stop_reason == "stop"
    assert len(result.tool_calls) == 0


# === Ollama Tests ===

@pytest.mark.asyncio
async def test_ollama_tool_use_returns_tool_calls():
    adapter = OllamaAdapter(model="llama3", base_url="http://localhost:11434")

    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "choices": [{
            "finish_reason": "tool_calls",
            "message": {
                "content": "Here's an alternative:",
                "tool_calls": [{
                    "id": "call_456",
                    "type": "function",
                    "function": {
                        "name": "swap_exercise",
                        "arguments": json.dumps({"day_number": 1, "exercise_name": "Bench Press", "replacement_name": "DB Press"}),
                    },
                }],
            },
        }],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as MockClient:
        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(return_value=mock_resp)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client_instance

        result = await adapter.tool_use(
            system_prompt="You are a fitness coach.",
            messages=[{"role": "user", "content": "Swap bench press"}],
            tools=[SWAP_TOOL],
            tool_choice="any",
        )

    assert isinstance(result, ToolUseResponse)
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "swap_exercise"
