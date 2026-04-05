import logging

from openai import AsyncOpenAI

import json as json_mod

from flexloop.ai.base import LLMAdapter, LLMResponse, ToolCall, ToolUseResponse

logger = logging.getLogger(__name__)


class OpenAIAdapter(LLMAdapter):
    def __init__(self, model: str, api_key: str, base_url: str = "", **kwargs):
        super().__init__(model, api_key, base_url)
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        self.client = AsyncOpenAI(**client_kwargs)

    def _parse_response(self, response) -> LLMResponse:
        """Parse response handling both Chat Completions and Responses API formats."""
        # Standard Chat Completions format
        if hasattr(response, "choices") and response.choices:
            cache_read = 0
            if response.usage:
                # OpenAI reports cached tokens in prompt_tokens_details
                details = getattr(response.usage, "prompt_tokens_details", None)
                if details:
                    cache_read = getattr(details, "cached_tokens", 0) or 0
            return LLMResponse(
                content=response.choices[0].message.content or "",
                input_tokens=response.usage.prompt_tokens if response.usage else 0,
                output_tokens=response.usage.completion_tokens if response.usage else 0,
                cache_read_tokens=cache_read,
            )

        # Responses API format (response.output)
        if hasattr(response, "output"):
            content = ""
            if isinstance(response.output, list):
                for item in response.output:
                    if hasattr(item, "content"):
                        for block in item.content:
                            if hasattr(block, "text"):
                                content += block.text
                    elif hasattr(item, "text"):
                        content += item.text
            elif isinstance(response.output, str):
                content = response.output

            usage = getattr(response, "usage", None)
            input_tokens = 0
            output_tokens = 0
            cache_read = 0
            if usage:
                input_tokens = getattr(usage, "input_tokens", 0) or getattr(usage, "prompt_tokens", 0) or 0
                output_tokens = getattr(usage, "output_tokens", 0) or getattr(usage, "completion_tokens", 0) or 0
                # Check for cached tokens in various formats
                cache_read = getattr(usage, "input_tokens_details", {})
                if isinstance(cache_read, dict):
                    cache_read = cache_read.get("cached_tokens", 0) or 0
                elif hasattr(cache_read, "cached_tokens"):
                    cache_read = getattr(cache_read, "cached_tokens", 0) or 0
                else:
                    cache_read = 0

            return LLMResponse(content=content, input_tokens=input_tokens,
                               output_tokens=output_tokens, cache_read_tokens=cache_read)

        # Raw string response (some providers return plain text)
        if isinstance(response, str):
            return LLMResponse(content=response, input_tokens=0, output_tokens=0)

        # Fallback: try to extract content from any response structure
        logger.warning(f"Unknown response format: {type(response)}")
        content = str(response)
        return LLMResponse(content=content, input_tokens=0, output_tokens=0)

    async def generate(
        self, system_prompt: str, user_prompt: str, temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> LLMResponse:
        try:
            # Try Chat Completions API first
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return self._parse_response(response)
        except Exception as e:
            logger.warning(f"Chat Completions API failed: {e}. Trying Responses API.")
            # Fallback to Responses API
            try:
                response = await self.client.responses.create(
                    model=self.model,
                    instructions=system_prompt,
                    input=user_prompt,
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                )
                return self._parse_response(response)
            except Exception as e2:
                logger.error(f"Both API formats failed. Chat: {e}, Responses: {e2}")
                raise e2

    async def chat(
        self, messages: list[dict], temperature: float = 0.7, max_tokens: int = 2000,
    ) -> LLMResponse:
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return self._parse_response(response)
        except Exception as e:
            logger.warning(f"Chat Completions API failed: {e}. Trying Responses API.")
            # Extract system and user messages for Responses API
            system_msg = ""
            user_input = ""
            for msg in messages:
                if msg["role"] == "system":
                    system_msg = msg["content"]
                elif msg["role"] == "user":
                    user_input = msg["content"]

            try:
                response = await self.client.responses.create(
                    model=self.model,
                    instructions=system_msg,
                    input=user_input,
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                )
                return self._parse_response(response)
            except Exception as e2:
                logger.error(f"Both API formats failed. Chat: {e}, Responses: {e2}")
                raise e2

    async def tool_use(
        self, system_prompt: str, messages: list[dict], tools: list,
        tool_choice: str = "auto", temperature: float = 0.7, max_tokens: int = 2000,
    ) -> ToolUseResponse:
        openai_tools = [
            {
                "type": "function",
                "function": {"name": t.name, "description": t.description, "parameters": t.input_schema},
            }
            for t in tools
        ]

        if tool_choice == "any":
            tc = "required"
        elif tool_choice == "auto":
            tc = "auto"
        else:
            tc = {"type": "function", "function": {"name": tool_choice}}

        openai_messages = [{"role": "system", "content": system_prompt}]
        for msg in messages:
            if msg["role"] == "tool_results":
                for r in msg["results"]:
                    openai_messages.append({
                        "role": "tool",
                        "tool_call_id": r["tool_use_id"],
                        "content": r["content"],
                    })
            else:
                openai_messages.append(msg)

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=openai_messages,
            tools=openai_tools,
            tool_choice=tc,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        choice = response.choices[0]
        msg = choice.message

        tool_calls = []
        if msg.tool_calls:
            for tc_obj in msg.tool_calls:
                try:
                    parsed_input = json_mod.loads(tc_obj.function.arguments)
                except json_mod.JSONDecodeError:
                    parsed_input = {}
                tool_calls.append(ToolCall(id=tc_obj.id, name=tc_obj.function.name, input=parsed_input))

        return ToolUseResponse(
            content=msg,
            tool_calls=tool_calls,
            text=msg.content or "",
            stop_reason=choice.finish_reason,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
        )
