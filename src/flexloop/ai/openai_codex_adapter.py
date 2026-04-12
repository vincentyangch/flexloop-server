"""OpenAI Codex OAuth adapter.

Reads the Codex CLI / OpenClaw ChatGPT OAuth token fresh from auth.json for
each request and reuses the base OpenAI adapter's request/response handling.
"""
from __future__ import annotations

import openai
from openai import AsyncOpenAI

from flexloop.ai.codex_auth import (
    CodexAuthMalformed,
    CodexAuthMissing,
    CodexAuthReader,
    CodexAuthWrongMode,
)
from flexloop.ai.openai_adapter import OpenAIAdapter


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
        token = CodexAuthReader(self._auth_file).read_access_token()
        return AsyncOpenAI(api_key=token)

    def _chat_extra_kwargs(self) -> dict:
        if self._reasoning_effort == "none":
            return {}
        return {"reasoning_effort": self._reasoning_effort}

    def _responses_extra_kwargs(self) -> dict:
        if self._reasoning_effort == "none":
            return {}
        return {"reasoning": {"effort": self._reasoning_effort}}
