"""Tests for the AI adapter factory."""
from __future__ import annotations

import pytest

from flexloop.ai.factory import create_adapter
from flexloop.ai.openai_codex_adapter import OpenAICodexAdapter


def test_create_adapter_returns_codex_adapter_for_openai_codex():
    adapter = create_adapter(
        provider="openai-codex",
        model="gpt-5.1-codex-max",
        codex_auth_file="/tmp/fake-auth.json",
        reasoning_effort="medium",
    )

    assert isinstance(adapter, OpenAICodexAdapter)
    assert adapter.model == "gpt-5.1-codex-max"
    assert adapter._auth_file == "/tmp/fake-auth.json"
    assert adapter._reasoning_effort == "medium"


def test_create_adapter_unknown_provider_raises():
    with pytest.raises(ValueError, match="Unknown provider: unknown"):
        create_adapter(provider="unknown", model="gpt-4o-mini")
