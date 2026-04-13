"""OpenAI Codex OAuth adapter.

Reads the Codex CLI / OpenClaw ChatGPT OAuth token fresh from auth.json for
each request and routes through the ChatGPT backend Codex endpoint (the same
quota lane that OpenClaw / Codex CLI use) instead of the public
api.openai.com endpoint.
"""
from __future__ import annotations

import base64
import json
import json as json_mod
import logging

import openai
from openai import AsyncOpenAI

from flexloop.ai.codex_auth import (
    CodexAuthMalformed,
    CodexAuthMissing,
    CodexAuthReader,
    CodexAuthWrongMode,
)
from flexloop.ai.openai_adapter import OpenAIAdapter

logger = logging.getLogger(__name__)

# ChatGPT OAuth tokens are issued for the ChatGPT backend, not the public
# OpenAI API.  Using api.openai.com lands on a separate billing/quota lane
# and produces 429 insufficient_quota even though the token itself is valid.
# The Codex sub-path mirrors the OpenAI Responses API wire format so the
# standard SDK client works as-is (confirmed by ChessNotation reference impl).
_CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"


def _extract_chatgpt_account_id(token: str) -> str | None:
    """Decode ``chatgpt_account_id`` from the access-token JWT payload.

    The ChatGPT backend expects this value in the ``ChatGPT-Account-ID``
    request header.  Returns *None* (silently) on any decode failure so
    callers can proceed without the header when the token format changes.
    """
    parts = token.split(".")
    if len(parts) < 2:
        return None
    payload_b64 = parts[1]
    padding = "=" * (-len(payload_b64) % 4)
    try:
        payload = json.loads(
            base64.urlsafe_b64decode(payload_b64 + padding),
        )
    except (ValueError, json.JSONDecodeError):
        return None
    auth = payload.get("https://api.openai.com/auth")
    if not isinstance(auth, dict):
        return None
    account_id = auth.get("chatgpt_account_id")
    return account_id if isinstance(account_id, str) else None


class OpenAICodexAdapter(OpenAIAdapter):
    _RERAISE_EXCEPTIONS: tuple[type[BaseException], ...] = (
        CodexAuthMissing,
        CodexAuthMalformed,
        CodexAuthWrongMode,
        openai.AuthenticationError,
    )

    def __init__(
        self,
        model: str,
        auth_file: str,
        reasoning_effort: str = "medium",
        **kwargs,
    ) -> None:
        self._auth_file = auth_file
        self._reasoning_effort = reasoning_effort
        # AsyncOpenAI rejects empty strings, but this client is never used:
        # _get_client() below replaces it with a fresh OAuth-token client.
        super().__init__(
            model,
            api_key="codex-oauth-placeholder",
            base_url="",
        )

    def _get_client(self) -> AsyncOpenAI:
        token, account_id = CodexAuthReader(self._auth_file).read_credential()
        # Auth-file account_id first, JWT decode as fallback (matches
        # ChessNotation: record.accountId ?? extractChatGPTAccountId(token)).
        if not account_id:
            account_id = _extract_chatgpt_account_id(token)
        headers: dict[str, str] = {}
        if account_id:
            headers["ChatGPT-Account-ID"] = account_id
        return AsyncOpenAI(
            api_key=token,
            base_url=_CODEX_BASE_URL,
            default_headers=headers or None,
        )

    def _chat_extra_kwargs(self) -> dict:
        if self._reasoning_effort == "none":
            return {}
        return {"reasoning_effort": self._reasoning_effort}

    def _responses_extra_kwargs(self) -> dict:
        if self._reasoning_effort == "none":
            return {}
        return {"reasoning": {"effort": self._reasoning_effort}}

    # ------------------------------------------------------------------
    # The ChatGPT Codex backend only speaks Responses API and requires:
    #   - ``input`` as a list of message objects (not a plain string)
    #   - ``store=False``
    #   - ``stream=True``
    # Override generate/chat/stream_generate to go straight to the
    # streaming Responses API, skipping the Chat Completions path.
    # ------------------------------------------------------------------

    @staticmethod
    def _check_stream_error(event) -> None:
        """Raise on ``error``, ``response.failed``, or ``response.incomplete``."""
        etype = getattr(event, "type", "")
        if etype == "error":
            msg = getattr(event, "message", None) or str(
                getattr(event, "error", "stream error")
            )
            raise RuntimeError(f"Codex stream error: {msg}")
        if etype in ("response.failed", "response.incomplete"):
            resp = getattr(event, "response", None)
            err = getattr(resp, "error", None) if resp else None
            msg = getattr(err, "message", None) if err else None
            status = getattr(resp, "status", etype)
            raise RuntimeError(
                f"Codex response {status}: {msg or 'no details'}"
            )

    async def _responses_stream(
        self, instructions: str, input_msgs: list[dict],
        temperature: float, max_tokens: int,
    ) -> "LLMResponse":
        """Stream a Responses API call and aggregate into an LLMResponse.

        ``temperature`` and ``max_tokens`` are accepted for interface
        compatibility but NOT sent — the Codex backend rejects both
        ``temperature`` and ``max_output_tokens`` with HTTP 400.
        """
        from flexloop.ai.base import LLMResponse

        client = self._get_client()
        stream = await client.responses.create(
            model=self.model,
            instructions=instructions,
            input=input_msgs,
            store=False,
            stream=True,
            **self._responses_extra_kwargs(),
        )

        content = ""
        input_tokens = 0
        output_tokens = 0
        async for event in stream:
            self._check_stream_error(event)
            if event.type == "response.output_text.delta":
                content += event.delta
            elif event.type == "response.completed":
                usage = getattr(event.response, "usage", None)
                if usage:
                    input_tokens = getattr(usage, "input_tokens", 0) or 0
                    output_tokens = getattr(usage, "output_tokens", 0) or 0

        return LLMResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    async def generate(
        self, system_prompt: str, user_prompt: str, temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> "LLMResponse":
        return await self._responses_stream(
            system_prompt,
            [{"role": "user", "content": user_prompt}],
            temperature, max_tokens,
        )

    async def chat(
        self, messages: list[dict], temperature: float = 0.7, max_tokens: int = 2000,
    ) -> "LLMResponse":
        system_msg = ""
        input_msgs: list[dict] = []
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            else:
                input_msgs.append(msg)
        return await self._responses_stream(
            system_msg, input_msgs, temperature, max_tokens,
        )

    async def stream_generate(
        self, system_prompt: str, user_prompt: str, temperature: float = 0.7,
        max_tokens: int = 2000,
    ):
        """Yield per-delta StreamEvents from the Codex Responses API."""
        import time as _time

        from flexloop.ai.base import StreamEvent

        start = _time.perf_counter()
        try:
            client = self._get_client()
            stream = await client.responses.create(
                model=self.model,
                instructions=system_prompt,
                input=[{"role": "user", "content": user_prompt}],
                store=False,
                stream=True,
                **self._responses_extra_kwargs(),
            )

            input_tokens = 0
            output_tokens = 0
            async for event in stream:
                self._check_stream_error(event)
                if event.type == "response.output_text.delta":
                    yield StreamEvent(type="content", delta=event.delta)
                elif event.type == "response.completed":
                    usage = getattr(event.response, "usage", None)
                    if usage:
                        input_tokens = getattr(usage, "input_tokens", 0) or 0
                        output_tokens = getattr(usage, "output_tokens", 0) or 0
        except Exception as exc:  # noqa: BLE001
            yield StreamEvent(type="error", error=str(exc))
            yield StreamEvent(type="done")
            return

        latency_ms = int((_time.perf_counter() - start) * 1000)
        yield StreamEvent(
            type="usage",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=0,
            latency_ms=latency_ms,
        )
        yield StreamEvent(type="done")

    async def tool_use(
        self, system_prompt: str, messages: list[dict], tools: list,
        tool_choice: str = "auto", temperature: float = 0.7, max_tokens: int = 2000,
    ) -> "ToolUseResponse":
        from flexloop.ai.base import ToolCall, ToolUseResponse

        # Responses API tool format (flat, not nested under "function")
        api_tools = [
            {"type": "function", "name": t.name,
             "description": t.description, "parameters": t.input_schema}
            for t in tools
        ]

        if tool_choice == "any":
            tc = "required"
        elif tool_choice == "auto":
            tc = "auto"
        else:
            tc = {"type": "function", "name": tool_choice}

        # Convert messages to Responses API input format
        input_msgs: list[dict] = []
        for msg in messages:
            if msg["role"] == "tool_results":
                for r in msg["results"]:
                    input_msgs.append({
                        "type": "function_call_output",
                        "call_id": r["tool_use_id"],
                        "output": r["content"],
                    })
            elif msg["role"] == "assistant" and isinstance(msg.get("content"), list):
                # Round-trip: content is a list of Responses API output dicts
                # from a previous tool_use() call on this adapter.
                for item in msg["content"]:
                    if isinstance(item, dict):
                        input_msgs.append(item)
            else:
                input_msgs.append({"role": msg["role"], "content": msg["content"]})

        client = self._get_client()
        stream = await client.responses.create(
            model=self.model,
            instructions=system_prompt,
            input=input_msgs,
            tools=api_tools,
            tool_choice=tc,
            store=False,
            stream=True,
            **self._responses_extra_kwargs(),
        )

        text = ""
        input_tokens = 0
        output_tokens = 0
        completed_output = None

        async for event in stream:
            self._check_stream_error(event)
            if event.type == "response.output_text.delta":
                text += event.delta
            elif event.type == "response.completed":
                usage = getattr(event.response, "usage", None)
                if usage:
                    input_tokens = getattr(usage, "input_tokens", 0) or 0
                    output_tokens = getattr(usage, "output_tokens", 0) or 0
                completed_output = event.response.output

        # Extract tool calls and build round-trip content from completed output.
        # The round-trip items are fed back into ``input`` on subsequent
        # iterations, so they must use valid Responses API input types:
        #   - function_call: needs both ``id`` (output-item ID) and ``call_id``
        #   - assistant text: ``{"role": "assistant", "content": "..."}``
        tool_calls: list[ToolCall] = []
        round_trip_items: list[dict] = []
        text_emitted = False

        for item in (completed_output or []):
            item_type = getattr(item, "type", None)
            if item_type == "function_call":
                item_id = getattr(item, "id", "")
                call_id = getattr(item, "call_id", "") or item_id
                name = getattr(item, "name", "")
                arguments = getattr(item, "arguments", "{}")
                try:
                    parsed = json_mod.loads(arguments)
                except (json_mod.JSONDecodeError, TypeError):
                    parsed = {}
                tool_calls.append(ToolCall(id=call_id, name=name, input=parsed))
                round_trip_items.append({
                    "type": "function_call",
                    "id": item_id,
                    "call_id": call_id,
                    "name": name,
                    "arguments": arguments,
                })
            elif item_type == "message" and text and not text_emitted:
                # Include assistant text once so multi-turn context stays
                # coherent without duplicating across multiple message items.
                round_trip_items.append({
                    "role": "assistant",
                    "content": text,
                })
                text_emitted = True

        stop_reason = "tool_calls" if tool_calls else "stop"

        return ToolUseResponse(
            content=round_trip_items,
            tool_calls=tool_calls,
            text=text,
            stop_reason=stop_reason,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
