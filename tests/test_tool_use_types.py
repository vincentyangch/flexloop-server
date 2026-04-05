from flexloop.ai.base import ToolDef, ToolCall, ToolUseResponse, LLMResponse


def test_tool_def_creation():
    td = ToolDef(
        name="swap_exercise",
        description="Replace one exercise",
        input_schema={"type": "object", "properties": {"name": {"type": "string"}}},
    )
    assert td.name == "swap_exercise"
    assert td.input_schema["type"] == "object"


def test_tool_call_creation():
    tc = ToolCall(id="tc_123", name="swap_exercise", input={"name": "Bench Press"})
    assert tc.id == "tc_123"
    assert tc.input["name"] == "Bench Press"


def test_tool_use_response_creation():
    tur = ToolUseResponse(
        content=[],
        tool_calls=[],
        text="Here are alternatives",
        stop_reason="end_turn",
        input_tokens=100,
        output_tokens=50,
    )
    assert tur.stop_reason == "end_turn"
    assert tur.cache_read_tokens == 0


def test_tool_use_response_to_llm_response():
    tur = ToolUseResponse(
        content=[],
        tool_calls=[],
        text="response text",
        stop_reason="end_turn",
        input_tokens=100,
        output_tokens=50,
        cache_read_tokens=80,
        cache_creation_tokens=20,
    )
    lr = tur.to_llm_response()
    assert isinstance(lr, LLMResponse)
    assert lr.content == "response text"
    assert lr.input_tokens == 100
    assert lr.output_tokens == 50
    assert lr.cache_read_tokens == 80
    assert lr.cache_creation_tokens == 20
