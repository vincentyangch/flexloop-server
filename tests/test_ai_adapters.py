from flexloop.ai.base import LLMAdapter
from flexloop.ai.factory import create_adapter


def test_create_openai_adapter():
    adapter = create_adapter(provider="openai", model="gpt-4o-mini", api_key="test-key")
    assert isinstance(adapter, LLMAdapter)


def test_create_openai_compatible_adapter():
    adapter = create_adapter(
        provider="openai-compatible", model="test", api_key="test", base_url="http://localhost:1234"
    )
    assert isinstance(adapter, LLMAdapter)


def test_create_anthropic_adapter():
    adapter = create_adapter(
        provider="anthropic", model="claude-sonnet-4-20250514", api_key="test-key"
    )
    assert isinstance(adapter, LLMAdapter)


def test_create_ollama_adapter():
    adapter = create_adapter(provider="ollama", model="llama3", api_key="")
    assert isinstance(adapter, LLMAdapter)


def test_create_unknown_adapter_raises():
    try:
        create_adapter(provider="unknown", model="test", api_key="test")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Unknown provider" in str(e)
