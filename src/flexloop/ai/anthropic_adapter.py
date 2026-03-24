import logging

from anthropic import AsyncAnthropic

from flexloop.ai.base import LLMAdapter, LLMResponse

logger = logging.getLogger(__name__)


class AnthropicAdapter(LLMAdapter):
    def __init__(self, model: str, api_key: str, enable_cache: bool = True, **kwargs):
        super().__init__(model, api_key)
        self.client = AsyncAnthropic(api_key=api_key)
        self.enable_cache = enable_cache

    def _build_system_with_cache(self, system_prompt: str) -> list[dict]:
        """Build system prompt with cache control for Anthropic.

        The system prompt is marked as cacheable so repeated calls
        with the same system instructions don't reprocess those tokens.
        """
        if self.enable_cache:
            return [
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        return [{"type": "text", "text": system_prompt}]

    def _extract_cache_info(self, usage) -> tuple[int, int]:
        """Extract cache read and creation tokens from Anthropic usage."""
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0

        if cache_read > 0:
            logger.info(f"Cache hit: {cache_read} tokens read from cache")
        if cache_creation > 0:
            logger.info(f"Cache miss: {cache_creation} tokens cached for future use")

        return cache_read, cache_creation

    async def generate(
        self, system_prompt: str, user_prompt: str, temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> LLMResponse:
        response = await self.client.messages.create(
            model=self.model,
            system=self._build_system_with_cache(system_prompt),
            messages=[{"role": "user", "content": user_prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )

        cache_read, cache_creation = self._extract_cache_info(response.usage)

        return LLMResponse(
            content=response.content[0].text if response.content else "",
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cache_read_tokens=cache_read,
            cache_creation_tokens=cache_creation,
        )

    async def chat(
        self, messages: list[dict], temperature: float = 0.7, max_tokens: int = 2000,
    ) -> LLMResponse:
        system_msg = ""
        chat_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            else:
                chat_messages.append(msg)

        kwargs = {
            "model": self.model,
            "messages": chat_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system_msg:
            kwargs["system"] = self._build_system_with_cache(system_msg)

        response = await self.client.messages.create(**kwargs)

        cache_read, cache_creation = self._extract_cache_info(response.usage)

        return LLMResponse(
            content=response.content[0].text if response.content else "",
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cache_read_tokens=cache_read,
            cache_creation_tokens=cache_creation,
        )
