"""Unit tests for LLMAdapter.stream_generate default fallback + StreamEvent."""
from __future__ import annotations

import pytest

from flexloop.ai.base import LLMAdapter, LLMResponse, StreamEvent


class _FakeAdapter(LLMAdapter):
    """Concrete test adapter that returns a canned LLMResponse from generate.

    Overrides only ``generate`` and ``chat`` — inherits the default
    ``stream_generate`` fallback from the base class.
    """

    def __init__(self) -> None:
        super().__init__(model="fake", api_key="", base_url="")
        self._canned = LLMResponse(
            content="Hello, world!",
            input_tokens=5,
            output_tokens=3,
            cache_read_tokens=0,
        )

    async def generate(
        self, system_prompt: str, user_prompt: str, temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> LLMResponse:
        return self._canned

    async def chat(
        self, messages: list[dict], temperature: float = 0.7, max_tokens: int = 2000,
    ) -> LLMResponse:
        return self._canned


class TestStreamEvent:
    def test_content_event_has_only_delta(self) -> None:
        evt = StreamEvent(type="content", delta="hello")
        assert evt.type == "content"
        assert evt.delta == "hello"
        assert evt.input_tokens is None
        assert evt.output_tokens is None
        assert evt.error is None

    def test_usage_event_has_token_counts(self) -> None:
        evt = StreamEvent(
            type="usage",
            input_tokens=5,
            output_tokens=3,
            cache_read_tokens=0,
            latency_ms=120,
        )
        assert evt.type == "usage"
        assert evt.input_tokens == 5
        assert evt.output_tokens == 3
        assert evt.latency_ms == 120
        assert evt.delta is None

    def test_done_event(self) -> None:
        evt = StreamEvent(type="done")
        assert evt.type == "done"
        assert evt.delta is None

    def test_error_event(self) -> None:
        evt = StreamEvent(type="error", error="boom")
        assert evt.type == "error"
        assert evt.error == "boom"


class TestDefaultStreamGenerate:
    async def test_yields_single_content_event(self) -> None:
        """The default fallback calls generate() and yields the content
        as exactly one ``content`` event.
        """
        adapter = _FakeAdapter()
        events: list[StreamEvent] = []
        async for evt in adapter.stream_generate(
            system_prompt="sys", user_prompt="usr", temperature=0.5, max_tokens=100
        ):
            events.append(evt)
        content_events = [e for e in events if e.type == "content"]
        assert len(content_events) == 1
        assert content_events[0].delta == "Hello, world!"

    async def test_yields_usage_event_with_token_counts(self) -> None:
        adapter = _FakeAdapter()
        events = [e async for e in adapter.stream_generate(
            system_prompt="sys", user_prompt="usr",
        )]
        usage_events = [e for e in events if e.type == "usage"]
        assert len(usage_events) == 1
        u = usage_events[0]
        assert u.input_tokens == 5
        assert u.output_tokens == 3
        assert u.cache_read_tokens == 0
        assert u.latency_ms is not None
        assert u.latency_ms >= 0

    async def test_yields_done_event_last(self) -> None:
        adapter = _FakeAdapter()
        events = [e async for e in adapter.stream_generate(
            system_prompt="sys", user_prompt="usr",
        )]
        assert events[-1].type == "done"

    async def test_event_order_is_content_usage_done(self) -> None:
        adapter = _FakeAdapter()
        events = [e async for e in adapter.stream_generate(
            system_prompt="sys", user_prompt="usr",
        )]
        assert [e.type for e in events] == ["content", "usage", "done"]

    async def test_error_emits_error_and_done(self) -> None:
        """If generate() raises, the stream emits an error event then done."""
        class _BrokenAdapter(_FakeAdapter):
            async def generate(self, *args, **kwargs) -> LLMResponse:
                raise RuntimeError("simulated failure")

        adapter = _BrokenAdapter()
        events = [e async for e in adapter.stream_generate(
            system_prompt="sys", user_prompt="usr",
        )]
        types = [e.type for e in events]
        assert "error" in types
        assert types[-1] == "done"
        error_evt = next(e for e in events if e.type == "error")
        assert "simulated failure" in (error_evt.error or "")
