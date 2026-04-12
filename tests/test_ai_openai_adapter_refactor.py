"""Regression tests for the OpenAIAdapter hook refactor.

These tests pin the DEFAULT behavior of _get_client,
_chat_extra_kwargs, _responses_extra_kwargs, and _RERAISE_EXCEPTIONS
so that any subclass (like OpenAICodexAdapter) can rely on the hooks
being empty/no-op unless explicitly overridden, AND any change to
the base class that alters these defaults will flag.
"""
from __future__ import annotations

from flexloop.ai.openai_adapter import OpenAIAdapter


def test_openai_adapter_get_client_returns_persistent_instance():
    adapter = OpenAIAdapter(model="gpt-4o-mini", api_key="sk-test")
    client_a = adapter._get_client()
    client_b = adapter._get_client()
    assert client_a is client_b, (
        "default _get_client must return the same persistent AsyncOpenAI "
        "instance on repeated calls -- subclasses are the ones that rotate"
    )


def test_openai_adapter_chat_extra_kwargs_empty_by_default():
    adapter = OpenAIAdapter(model="gpt-4o-mini", api_key="sk-test")
    assert adapter._chat_extra_kwargs() == {}


def test_openai_adapter_responses_extra_kwargs_empty_by_default():
    adapter = OpenAIAdapter(model="gpt-4o-mini", api_key="sk-test")
    assert adapter._responses_extra_kwargs() == {}


def test_openai_adapter_reraise_exceptions_empty_tuple_by_default():
    assert OpenAIAdapter._RERAISE_EXCEPTIONS == ()


def test_openai_adapter_instance_honors_class_reraise_exceptions():
    """Instances read the class attribute.

    Overriding on a subclass class attribute is enough; per-instance
    mutation is NOT supported.
    """
    adapter = OpenAIAdapter(model="gpt-4o-mini", api_key="sk-test")
    assert adapter._RERAISE_EXCEPTIONS == ()
