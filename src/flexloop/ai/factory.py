from flexloop.ai.anthropic_adapter import AnthropicAdapter
from flexloop.ai.base import LLMAdapter
from flexloop.ai.ollama_adapter import OllamaAdapter
from flexloop.ai.openai_adapter import OpenAIAdapter
from flexloop.ai.openai_codex_adapter import OpenAICodexAdapter


def create_adapter(
    provider: str, model: str, api_key: str = "", base_url: str = "", **kwargs
) -> LLMAdapter:
    if provider == "openai":
        return OpenAIAdapter(model=model, api_key=api_key, base_url=base_url, **kwargs)
    elif provider == "openai-compatible":
        return OpenAIAdapter(model=model, api_key=api_key, base_url=base_url, **kwargs)
    elif provider == "openai-codex":
        return OpenAICodexAdapter(
            model=model,
            auth_file=kwargs.pop("codex_auth_file", "~/.codex/auth.json"),
            reasoning_effort=kwargs.pop("reasoning_effort", "medium"),
        )
    elif provider == "anthropic":
        return AnthropicAdapter(model=model, api_key=api_key, **kwargs)
    elif provider == "ollama":
        base = base_url or "http://localhost:11434"
        return OllamaAdapter(model=model, base_url=base, **kwargs)
    raise ValueError(f"Unknown provider: {provider}")
