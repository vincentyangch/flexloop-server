import json as json_mod

import httpx

from flexloop.ai.base import LLMAdapter, LLMResponse, ToolCall, ToolUseResponse


class OllamaAdapter(LLMAdapter):
    def __init__(self, model: str, base_url: str = "http://localhost:11434", **kwargs):
        super().__init__(model, api_key="", base_url=base_url)

    async def generate(
        self, system_prompt: str, user_prompt: str, temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> LLMResponse:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "stream": False,
                    "options": {"temperature": temperature, "num_predict": max_tokens},
                },
                timeout=120.0,
            )
            response.raise_for_status()
            data = response.json()

        return LLMResponse(
            content=data.get("message", {}).get("content", ""),
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
        )

    async def chat(
        self, messages: list[dict], temperature: float = 0.7, max_tokens: int = 2000,
    ) -> LLMResponse:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": temperature, "num_predict": max_tokens},
                },
                timeout=120.0,
            )
            response.raise_for_status()
            data = response.json()

        return LLMResponse(
            content=data.get("message", {}).get("content", ""),
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
        )

    async def tool_use(
        self, system_prompt: str, messages: list[dict], tools: list,
        tool_choice: str = "auto", temperature: float = 0.7, max_tokens: int = 2000,
    ) -> ToolUseResponse:
        """Tool use via Ollama's OpenAI-compatible /v1/chat/completions endpoint."""
        url = f"{self.base_url}/v1/chat/completions"

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

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                json={
                    "model": self.model,
                    "messages": openai_messages,
                    "tools": openai_tools,
                    "tool_choice": tc,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                timeout=120.0,
            )
            resp.raise_for_status()
            data = resp.json()

        choice = data["choices"][0]
        msg = choice["message"]
        usage = data.get("usage", {})

        tool_calls = []
        for tc_obj in msg.get("tool_calls", []):
            try:
                parsed_input = json_mod.loads(tc_obj["function"]["arguments"])
            except (json_mod.JSONDecodeError, KeyError):
                parsed_input = {}
            tool_calls.append(ToolCall(
                id=tc_obj.get("id", ""),
                name=tc_obj["function"]["name"],
                input=parsed_input,
            ))

        return ToolUseResponse(
            content=msg,
            tool_calls=tool_calls,
            text=msg.get("content", "") or "",
            stop_reason=choice.get("finish_reason", "stop"),
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
        )
