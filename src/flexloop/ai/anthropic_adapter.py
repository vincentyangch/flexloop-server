import logging

from anthropic import AsyncAnthropic

from flexloop.ai.base import LLMAdapter, LLMResponse, ToolCall, ToolUseResponse

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

    async def tool_use(
        self, system_prompt: str, messages: list[dict], tools: list,
        tool_choice: str = "auto", temperature: float = 0.7, max_tokens: int = 2000,
    ) -> ToolUseResponse:
        anthropic_tools = [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in tools
        ]

        if tool_choice == "any":
            tc = {"type": "any"}
        elif tool_choice == "auto":
            tc = {"type": "auto"}
        else:
            tc = {"type": "tool", "name": tool_choice}

        # Translate tool_results role to Anthropic format
        anthropic_messages = []
        for msg in messages:
            if msg["role"] == "tool_results":
                anthropic_messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": r["tool_use_id"],
                            "content": r["content"],
                            **({"is_error": True} if r.get("is_error") else {}),
                        }
                        for r in msg["results"]
                    ],
                })
            else:
                anthropic_messages.append(msg)

        response = await self.client.messages.create(
            model=self.model,
            system=self._build_system_with_cache(system_prompt),
            messages=anthropic_messages,
            tools=anthropic_tools,
            tool_choice=tc,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        cache_read, cache_creation = self._extract_cache_info(response.usage)

        tool_calls = []
        text_parts = []
        for block in response.content:
            if block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, input=block.input))
            elif block.type == "text":
                text_parts.append(block.text)

        return ToolUseResponse(
            content=response.content,
            tool_calls=tool_calls,
            text="".join(text_parts),
            stop_reason=response.stop_reason,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cache_read_tokens=cache_read,
            cache_creation_tokens=cache_creation,
        )
