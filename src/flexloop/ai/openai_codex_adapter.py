"""OpenAI Codex OAuth adapter.

Reads the Codex CLI / OpenClaw ChatGPT OAuth token fresh from auth.json for
each request and routes through the ChatGPT backend Codex endpoint (the same
quota lane that OpenClaw / Codex CLI use) instead of the public
api.openai.com endpoint.
"""
from __future__ import annotations

import base64
import json
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
