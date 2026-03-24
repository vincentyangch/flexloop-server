import logging

from openai import AsyncOpenAI

from flexloop.ai.base import LLMAdapter, LLMResponse

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
            return LLMResponse(
                content=response.choices[0].message.content or "",
                input_tokens=response.usage.prompt_tokens if response.usage else 0,
                output_tokens=response.usage.completion_tokens if response.usage else 0,
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
            if usage:
                input_tokens = getattr(usage, "input_tokens", 0) or getattr(usage, "prompt_tokens", 0) or 0
                output_tokens = getattr(usage, "output_tokens", 0) or getattr(usage, "completion_tokens", 0) or 0

            return LLMResponse(content=content, input_tokens=input_tokens, output_tokens=output_tokens)

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
