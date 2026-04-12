# Admin Dashboard — Phase 4c (AI Playground) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the admin AI Playground — a two-panel UI where the operator can fire prompts at the configured AI provider and watch responses stream in real time. Supports free-form prompts (raw system + user text) and template mode (pick a registered prompt, fill its `{{variables}}`, render a preview, send). Streaming is implemented via fetch+ReadableStream over HTTP POST (not EventSource, which only supports GET). The "Try parse as JSON" toggle catches empty-response bugs instantly — this is the feature that makes the spec's §1 opening story ("the 'AI returned invalid plan format' bug took 30 minutes to diagnose") reproducible in 30 seconds.

**Architecture:**
1. **Adapter streaming infrastructure** — `LLMAdapter` gains a new `stream_generate()` async generator method with a concrete default fallback in the base class (calls `generate()`, yields the full content as a single chunk + usage event). `OpenAIAdapter` overrides it with true per-delta streaming (the existing `_stream_chat_completion` already iterates deltas but currently aggregates — this chunk exposes the deltas as events). Other adapters (Anthropic, Ollama) inherit the fallback for now; true streaming can be added later without breaking anything.
2. **SSE wire format** — the `/run` endpoint emits `text/event-stream` via FastAPI's `StreamingResponse`. Each content chunk is `data: {"type": "content", "delta": "..."}\n\n`, terminated by `data: {"type": "usage", ...}\n\n` and `data: {"type": "done"}\n\n`. No `sse-starlette` dependency — the format is simple and we stay minimal.
3. **Templates endpoint** — reads from the filesystem via `prompt_service.list_prompts` (reused from 4b), then for each active version calls `read_version` + `extract_variables` to produce `{name, active_version, variables}`. No caching.
4. **Render endpoint** — reuses the existing `PromptManager.render()` which does simple `.replace("{{key}}", value)`. The server returns the rendered string without sending it to the AI.
5. **Frontend SSE client** — a small `lib/sseReader.ts` utility parses a `Response.body` ReadableStream into events. Uses `fetch` with `method: POST` so cookies are carried same-origin and the CSRF `Origin` header is sent automatically by the browser.
6. **Two-panel UI** — left panel has mode toggle (free-form vs template), system/user textareas (or template dropdown + variable form + rendered preview), advanced options (temperature, max_tokens, provider_override, model_override), Send button. Right panel has streaming response text area, token counts + latency, "Try parse as JSON" toggle that attempts `JSON.parse` and shows either a formatted tree or the parse error.
7. **"Open in playground →" button** (deferred from phase 4b) added to `PromptToolbar` in the Prompts page — navigates to `/ai/playground?template=<name>` which auto-selects template mode with the pre-picked template.

**Tech Stack (new to phase 4c):**
- **Backend:** no new dependencies. Uses FastAPI's built-in `StreamingResponse`, stdlib `time.perf_counter` for latency, existing `PromptManager` for template rendering.
- **Frontend:** no new dependencies. Manual SSE parsing via `Response.body.getReader()` + TextDecoder (native browser APIs).

**Spec reference:** `docs/superpowers/specs/2026-04-06-admin-dashboard-design.md`. Read §10.3 (AI Playground — authoritative), §10.2 (Prompt editor — the "Open in playground →" cross-reference), §1 (the motivating story), §14 phase 4 bullet.

**Phases 1-3 + 4a + 4b already delivered** (do not rework): admin auth + CSRF middleware, 7 CRUD pages, Plans editor, Config editor + audit log + runtime DB-backed Settings, Prompt editor with versioned `.md` files + CodeMirror + diff + variable inspector. The following are reusable and should be reused, not re-created:
- `flexloop.admin.prompt_service.list_prompts` / `read_version` / `extract_variables`
- `flexloop.admin.prompt_service.get_prompts_dir` dependency (test override via `app.dependency_overrides`)
- `flexloop.ai.factory.create_adapter(provider, model, api_key, base_url)`
- `flexloop.ai.prompts.PromptManager` (render via `.replace("{{key}}", value)`)
- `flexloop.config.settings` for the saved defaults

**Phase 4d (AI Usage dashboard) and Phase 5 are out of scope.**

---

## Decisions locked in for this phase

These choices are fixed before implementation starts. Do not re-litigate them mid-execution — if a decision turns out to be wrong, stop and ask the user.

1. **`LLMAdapter.stream_generate()` is a CONCRETE method, not abstract.** The base class provides a default fallback that calls `self.generate(...)` and yields a single content chunk + usage event. Concrete adapters (OpenAIAdapter) can override with true per-delta streaming. This means Anthropic and Ollama adapters work out of the box without any code changes — they just appear "bursty" (one big chunk then done) instead of character-by-character. Acceptable for v1.

2. **New dataclass `StreamEvent`** in `flexloop.ai.base`:
   ```python
   @dataclass
   class StreamEvent:
       type: str  # "content" | "usage" | "done"
       delta: str | None = None         # populated for type=="content"
       input_tokens: int | None = None  # populated for type=="usage"
       output_tokens: int | None = None
       cache_read_tokens: int | None = None
       latency_ms: int | None = None
   ```
   Adapters yield `StreamEvent` objects; the router serializes them to SSE wire format.

3. **SSE wire format:** `data: <json>\n\n` per event. No `event:` line (single channel). Example payloads:
   ```
   data: {"type": "content", "delta": "Hello"}

   data: {"type": "content", "delta": " world"}

   data: {"type": "usage", "input_tokens": 5, "output_tokens": 2, "cache_read_tokens": 0, "latency_ms": 450}

   data: {"type": "done"}

   ```
   The final `{"type": "done"}` event is an explicit terminator so the frontend knows to stop reading. FastAPI closes the connection naturally after the generator returns, but the explicit `done` event lets the frontend render the "complete" state before the close lands.

4. **`POST /api/admin/playground/run` always uses SSE response.** The spec says "If `stream: true`, `/run` returns an SSE stream" but in practice, the playground UI always wants streaming (that's the whole point). Removing the non-streaming path simplifies the code and matches the UX. If a future caller wants non-streaming, they can collect the SSE events and flatten them.

5. **Request body for `/run`:**
   ```
   {
     "system_prompt": str,
     "user_prompt": str,
     "temperature": float | null,
     "max_tokens": int | null,
     "provider_override": str | null,
     "model_override": str | null,
     "api_key_override": str | null,
     "base_url_override": str | null
   }
   ```
   `temperature`, `max_tokens`, and all override fields are optional. Omitted fields fall back to `settings.ai_*`. This is the same pattern as 4a's test-connection, with the same server-side fallback logic.

6. **Error handling on the SSE stream.** If the adapter raises during streaming, the generator catches the exception and emits a final `data: {"type": "error", "error": "<message>"}\n\n` event, followed by `data: {"type": "done"}\n\n`. The HTTP status is still 200 — errors are data on the stream, not HTTP errors. This matches 4a's test-connection convention.

7. **`GET /api/admin/playground/templates`:**
   ```json
   {
     "templates": [
       {
         "name": "plan_generation",
         "active_version": "v2",
         "variables": ["goal", "user_name"]
       },
       {
         "name": "chat",
         "active_version": "v1",
         "variables": ["message"]
       }
     ]
   }
   ```
   Only the active-default version is exposed. Variables are extracted from the active version's content via the 4b regex helper.

8. **`POST /api/admin/playground/render`:**
   ```
   Request: {"template_name": "plan_generation", "variables": {"user_name": "Alice", "goal": "strength"}}
   Response: {"template_name": "plan_generation", "version": "v2", "rendered": "Generate a plan for Alice targeting strength."}
   ```
   The server uses `PromptManager.render()`. Missing variables are left as `{{var}}` literals in the output (consistent with existing PromptManager behavior). No validation.

9. **No streaming for template-mode "render"** — the render endpoint always returns JSON (not SSE). It's a cheap server-side transformation; no AI call involved.

10. **"Open in playground →" button** on `PromptToolbar` (phase 4b deferred) navigates to `/ai/playground?template=<prompt_name>`. The playground reads the query param on mount, switches to template mode, selects the pre-named template, and fetches `/render` with empty variables to populate the preview textarea. The user can then edit the variables and Send.

11. **Frontend SSE parsing: manual, not a library.** `lib/sseReader.ts` implements the loop: `await reader.read()`, decode with `TextDecoder`, split on `\n\n`, parse each `data:` line as JSON. Standard ~30 LOC. No `@microsoft/fetch-event-source` dependency.

12. **"Try parse as JSON" toggle** lives on the right panel. Default off. When on, it takes the accumulated response text, tries `JSON.parse`, and either renders the parsed value as a formatted `<pre>` (using `JSON.stringify(value, null, 2)`) OR shows the parse error in a red box. No third-party JSON tree viewer.

13. **No audit log for playground runs.** Matches spec §10.1 "v1 only audits config changes". The playground is a throwaway experimentation surface.

14. **No request/response history persistence.** Each Send is standalone. If the admin wants to save a useful prompt, they edit it in the Prompt editor instead.

15. **Cookie-based auth works end-to-end for the fetch-POST streaming path.** The admin UI is served same-origin with the API, so `fetch('/api/admin/playground/run', {method: 'POST', body: ..., credentials: 'same-origin'})` carries the session cookie. The CSRF middleware checks the `Origin` header which browsers set automatically. No special handling needed.

16. **Worktree + feature branch:**
    - Worktree: `/Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase4c`
    - Branch: `feat/admin-dashboard-phase4c-playground`
    - Merge: fast-forward into `main`, delete branch + worktree, bump parent submodule, update memory.

---

## File Structure

All paths relative to `flexloop-server/` unless stated otherwise.

**Backend — new:**
```
src/flexloop/admin/
└── routers/
    └── playground.py              NEW — 3 endpoints (run/templates/render)
```

**Backend — modified:**
```
src/flexloop/
├── ai/base.py                     add StreamEvent dataclass + stream_generate default
├── ai/openai_adapter.py           override stream_generate with true per-delta streaming
└── main.py                        import + include_router for admin_playground_router
```

**Backend — tests:**
```
tests/
├── test_adapter_streaming.py      NEW — unit tests for stream_generate fallback + types
└── test_admin_playground.py       NEW — integration tests for 3 router endpoints
```

**Frontend — new:**
```
admin-ui/src/
├── lib/sseReader.ts               NEW — parse SSE events from a Response body stream
├── pages/PlaygroundPage.tsx       NEW — main two-panel page
└── components/playground/         NEW
    ├── PlaygroundInput.tsx        NEW — left panel (mode toggle, form, Send)
    ├── PlaygroundOutput.tsx       NEW — right panel (stream text, usage, JSON parse)
    └── TemplateForm.tsx           NEW — variable form for template mode
```

**Frontend — modified:**
```
admin-ui/src/
├── App.tsx                        add /ai/playground route
├── components/AppSidebar.tsx      remove `disabled: true` from Playground item
├── components/prompts/PromptToolbar.tsx   add "Open in playground →" button
├── pages/PromptsPage.tsx          wire the button to navigate
└── lib/api.types.ts               regenerated from updated OpenAPI schema
```

**Docs:**
```
docs/admin-dashboard-phase4c-smoke-test.md    NEW — manual + automated checklist
```

---

## Execution setup

```bash
cd /Users/flyingchickens/Projects/FlexLoop/flexloop-server
git worktree add /Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase4c -b feat/admin-dashboard-phase4c-playground
cd /Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase4c
uv sync --extra dev
uv pip install -e .
cd admin-ui && npm install --legacy-peer-deps && cd ..
```

Verify baseline:

```bash
uv run pytest -q
```

Expected: 383 tests green (phase 4b baseline).

```bash
cd admin-ui && npx tsc --noEmit && npm run build && cd ..
```

Expected: both green.

---

## Chunk 1: Backend — adapter streaming infrastructure

This chunk adds `stream_generate()` to the adapter base class with a default fallback, overrides it in `OpenAIAdapter` for true per-delta streaming, and adds a new `StreamEvent` dataclass. Fully unit-tested with a `FakeAdapter`.

### Task 1: Add `StreamEvent` dataclass + failing tests for the default fallback

**Files:**
- Modify: `src/flexloop/ai/base.py`
- Create: `tests/test_adapter_streaming.py`

- [ ] **Step 1: Add `StreamEvent` to `src/flexloop/ai/base.py`**

Append to the dataclass section (after `LLMResponse`, before `LLMAdapter`):

```python
@dataclass
class StreamEvent:
    """A single event emitted by ``LLMAdapter.stream_generate``.

    ``type`` is one of:
    - ``"content"``: incremental text chunk; ``delta`` holds the bytes.
    - ``"usage"``: terminal token/latency info; populated fields are
      ``input_tokens``, ``output_tokens``, ``cache_read_tokens``, ``latency_ms``.
    - ``"done"``: explicit end-of-stream marker — frontends use this to
      render a "complete" state before the HTTP connection closes.
    - ``"error"``: adapter failure during streaming; ``error`` holds the
      human-readable message. Streams with an error event also emit a
      final ``"done"`` event.
    """
    type: str
    delta: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    latency_ms: int | None = None
    error: str | None = None
```

- [ ] **Step 2: Create the failing test file**

```python
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
```

- [ ] **Step 3: Run to confirm failures**

```bash
uv run pytest tests/test_adapter_streaming.py -v
```

Expected: `TestStreamEvent` tests PASS (StreamEvent is defined), but `TestDefaultStreamGenerate` tests FAIL with `AttributeError: 'LLMAdapter' object has no attribute 'stream_generate'`.

- [ ] **Step 4: Commit the failing tests**

```bash
git add src/flexloop/ai/base.py tests/test_adapter_streaming.py
git commit -m "test(ai): failing tests for LLMAdapter.stream_generate + StreamEvent"
```

---

### Task 2: Implement the default `stream_generate` fallback in `LLMAdapter`

**Files:**
- Modify: `src/flexloop/ai/base.py`

- [ ] **Step 1: Add `stream_generate` method to the `LLMAdapter` class**

Append to the `LLMAdapter` class (after `tool_use`):

```python
    async def stream_generate(
        self, system_prompt: str, user_prompt: str, temperature: float = 0.7,
        max_tokens: int = 2000,
    ):
        """Stream ``generate`` output as a sequence of ``StreamEvent``.

        Default implementation for adapters that don't support true
        streaming: runs ``generate`` to completion, then yields the full
        content as a single ``content`` event, followed by a ``usage``
        event with latency, followed by a terminal ``done`` event.

        Adapters that DO support streaming (e.g. OpenAIAdapter) override
        this to yield per-delta content events as bytes arrive. The event
        shape and event ordering (``content*, usage, done``) are the same
        in both cases so frontends only need one code path.

        Errors raised by ``generate`` are caught and surfaced as an
        ``error`` event followed by a terminal ``done`` event — callers
        never see a raised exception from this generator.
        """
        import time as _time

        start = _time.perf_counter()
        try:
            response = await self.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:  # noqa: BLE001
            yield StreamEvent(type="error", error=str(exc))
            yield StreamEvent(type="done")
            return

        latency_ms = int((_time.perf_counter() - start) * 1000)
        yield StreamEvent(type="content", delta=response.content)
        yield StreamEvent(
            type="usage",
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cache_read_tokens=response.cache_read_tokens,
            latency_ms=latency_ms,
        )
        yield StreamEvent(type="done")
```

- [ ] **Step 2: Run the tests**

```bash
uv run pytest tests/test_adapter_streaming.py -v
```

Expected: all 9 tests pass (4 `TestStreamEvent` + 5 `TestDefaultStreamGenerate`).

- [ ] **Step 3: Full suite**

```bash
uv run pytest -q
```

Expected: 392 tests green (383 + 9 new).

- [ ] **Step 4: Commit**

```bash
git add src/flexloop/ai/base.py
git commit -m "feat(ai): LLMAdapter.stream_generate default fallback"
```

---

### Task 3: Override `stream_generate` in `OpenAIAdapter` with true per-delta streaming

**Files:**
- Modify: `src/flexloop/ai/openai_adapter.py`

The existing `_stream_chat_completion` already iterates deltas from OpenAI's streaming endpoint but aggregates into an `LLMResponse`. The new `stream_generate` override follows the same pattern but yields `StreamEvent` objects instead.

- [ ] **Step 1: Add the override**

Insert into `OpenAIAdapter` (between `generate` and `chat`):

```python
    async def stream_generate(
        self, system_prompt: str, user_prompt: str, temperature: float = 0.7,
        max_tokens: int = 2000,
    ):
        """True per-delta streaming for OpenAI / OpenAI-compatible providers.

        Yields ``StreamEvent(type="content", delta=...)`` for each delta as
        it arrives, followed by a terminal ``usage`` event and ``done``.
        """
        import time as _time

        from flexloop.ai.base import StreamEvent

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        start = _time.perf_counter()
        try:
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
                stream_options={"include_usage": True},
            )
            input_tokens = 0
            output_tokens = 0
            cache_read = 0
            async for chunk in stream:
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        yield StreamEvent(type="content", delta=delta.content)
                if chunk.usage:
                    input_tokens = chunk.usage.prompt_tokens or 0
                    output_tokens = chunk.usage.completion_tokens or 0
                    details = getattr(chunk.usage, "prompt_tokens_details", None)
                    if details:
                        cache_read = getattr(details, "cached_tokens", 0) or 0
        except Exception as exc:  # noqa: BLE001
            yield StreamEvent(type="error", error=str(exc))
            yield StreamEvent(type="done")
            return

        latency_ms = int((_time.perf_counter() - start) * 1000)
        yield StreamEvent(
            type="usage",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read,
            latency_ms=latency_ms,
        )
        yield StreamEvent(type="done")
```

- [ ] **Step 2: Verify the existing OpenAI tests still pass**

```bash
uv run pytest tests/test_ai_adapters.py -v
```

Expected: all pre-existing tests pass (the override doesn't touch `generate` / `chat`).

- [ ] **Step 3: Full suite**

```bash
uv run pytest -q
```

Expected: 392 tests green (no new tests in this task — the streaming override is covered by Chunk 2's integration tests which mock the adapter).

- [ ] **Step 4: Commit**

```bash
git add src/flexloop/ai/openai_adapter.py
git commit -m "feat(ai): OpenAIAdapter.stream_generate with true per-delta events"
```

---

**End of Chunk 1.** Adapter streaming infrastructure is in place. Default fallback works for all providers; OpenAI has a true-streaming override. Next chunk wraps this in HTTP endpoints.

---

## Chunk 2: Backend — playground router

### Task 4: Router skeleton + `POST /api/admin/playground/run` with SSE response

**Files:**
- Create: `src/flexloop/admin/routers/playground.py`
- Modify: `src/flexloop/main.py`
- Create: `tests/test_admin_playground.py`

- [ ] **Step 1: Write failing tests for `/run`**

```python
"""Integration tests for /api/admin/playground."""
from __future__ import annotations

import json

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import SESSION_COOKIE_NAME, create_session, hash_password
from flexloop.models.admin_user import AdminUser


ORIGIN = "http://localhost:5173"


async def _make_admin_and_cookie(db: AsyncSession) -> dict[str, str]:
    admin = AdminUser(username="tester", password_hash=hash_password("password123"))
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    token, _ = await create_session(db, admin_user_id=admin.id)
    return {SESSION_COOKIE_NAME: token}


class TestPlaygroundRun:
    async def test_requires_auth(self, client: AsyncClient) -> None:
        res = await client.post(
            "/api/admin/playground/run",
            json={"system_prompt": "sys", "user_prompt": "hi"},
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 401

    async def test_streams_content_and_usage_with_fake_adapter(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """With a stubbed create_adapter returning a fake adapter whose
        stream_generate yields controlled events, /run should emit an SSE
        stream that round-trips every event.
        """
        from flexloop.admin.routers import playground as playground_router
        from flexloop.ai.base import LLMAdapter, LLMResponse, StreamEvent

        class _FakeAdapter(LLMAdapter):
            def __init__(self, *a, **kw) -> None:
                super().__init__(model="fake", api_key="", base_url="")

            async def generate(self, *a, **kw) -> LLMResponse:
                return LLMResponse(content="hi", input_tokens=1, output_tokens=1)

            async def chat(self, *a, **kw) -> LLMResponse:
                return LLMResponse(content="hi", input_tokens=1, output_tokens=1)

            async def stream_generate(self, *a, **kw):
                yield StreamEvent(type="content", delta="Hello")
                yield StreamEvent(type="content", delta=", world!")
                yield StreamEvent(
                    type="usage",
                    input_tokens=5,
                    output_tokens=3,
                    cache_read_tokens=0,
                    latency_ms=42,
                )
                yield StreamEvent(type="done")

        monkeypatch.setattr(
            playground_router, "create_adapter", lambda *a, **kw: _FakeAdapter()
        )

        cookies = await _make_admin_and_cookie(db_session)
        res = await client.post(
            "/api/admin/playground/run",
            json={"system_prompt": "sys", "user_prompt": "hi"},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/event-stream")

        # Parse the SSE body into events
        body = res.text
        events = []
        for line in body.split("\n\n"):
            line = line.strip()
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: "):]))

        # Expected: 2 content + 1 usage + 1 done = 4 events
        assert len(events) == 4
        assert events[0] == {"type": "content", "delta": "Hello"}
        assert events[1] == {"type": "content", "delta": ", world!"}
        assert events[2]["type"] == "usage"
        assert events[2]["input_tokens"] == 5
        assert events[2]["output_tokens"] == 3
        assert events[2]["latency_ms"] == 42
        assert events[3] == {"type": "done"}

    async def test_error_event_on_adapter_failure(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from flexloop.admin.routers import playground as playground_router
        from flexloop.ai.base import LLMAdapter, LLMResponse, StreamEvent

        class _BrokenAdapter(LLMAdapter):
            def __init__(self, *a, **kw) -> None:
                super().__init__(model="fake", api_key="", base_url="")

            async def generate(self, *a, **kw) -> LLMResponse:
                raise RuntimeError("boom")

            async def chat(self, *a, **kw) -> LLMResponse:
                raise RuntimeError("boom")

            async def stream_generate(self, *a, **kw):
                yield StreamEvent(type="error", error="simulated boom")
                yield StreamEvent(type="done")

        monkeypatch.setattr(
            playground_router, "create_adapter", lambda *a, **kw: _BrokenAdapter()
        )

        cookies = await _make_admin_and_cookie(db_session)
        res = await client.post(
            "/api/admin/playground/run",
            json={"system_prompt": "sys", "user_prompt": "hi"},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 200
        body = res.text
        events = [
            json.loads(line[len("data: "):])
            for line in body.split("\n\n")
            if line.strip().startswith("data: ")
        ]
        assert any(e["type"] == "error" and "simulated boom" in e["error"] for e in events)
        assert events[-1] == {"type": "done"}

    async def test_overrides_passed_to_create_adapter(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from flexloop.admin.routers import playground as playground_router
        from flexloop.ai.base import LLMAdapter, LLMResponse, StreamEvent

        captured: dict = {}

        class _FakeAdapter(LLMAdapter):
            def __init__(self, *a, **kw) -> None:
                super().__init__(model="fake", api_key="", base_url="")

            async def generate(self, *a, **kw) -> LLMResponse:
                return LLMResponse(content="", input_tokens=0, output_tokens=0)

            async def chat(self, *a, **kw) -> LLMResponse:
                return LLMResponse(content="", input_tokens=0, output_tokens=0)

            async def stream_generate(self, *a, **kw):
                yield StreamEvent(type="done")

        def _fake_create_adapter(provider, model, api_key, base_url, **kwargs):
            captured["provider"] = provider
            captured["model"] = model
            captured["api_key"] = api_key
            captured["base_url"] = base_url
            return _FakeAdapter()

        monkeypatch.setattr(
            playground_router, "create_adapter", _fake_create_adapter
        )

        cookies = await _make_admin_and_cookie(db_session)
        res = await client.post(
            "/api/admin/playground/run",
            json={
                "system_prompt": "sys",
                "user_prompt": "hi",
                "provider_override": "anthropic",
                "model_override": "claude-test",
                "api_key_override": "sk-override",
                "base_url_override": "https://override.example.com",
            },
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 200
        assert captured["provider"] == "anthropic"
        assert captured["model"] == "claude-test"
        assert captured["api_key"] == "sk-override"
        assert captured["base_url"] == "https://override.example.com"
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/test_admin_playground.py::TestPlaygroundRun -v
```

Expected: all 4 fail (router doesn't exist — 404).

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_admin_playground.py
git commit -m "test(admin): failing tests for POST /api/admin/playground/run"
```

- [ ] **Step 4: Create the router + `/run` handler**

```python
"""Admin endpoints for the AI playground.

Three endpoints:
- POST /api/admin/playground/run         SSE streaming run
- GET  /api/admin/playground/templates   list registered prompts + variables
- POST /api/admin/playground/render      render a template with variables

The ``/run`` endpoint always returns ``text/event-stream``. Each event is
a single ``data: <json>\\n\\n`` line. Event types: ``content``, ``usage``,
``error``, ``done``. The stream is terminated by an explicit ``done``
event so frontends can render the complete state before the connection
closes.

Spec: §10.3
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

from flexloop.admin.auth import require_admin
from flexloop.admin.prompt_service import (
    extract_variables,
    read_version,
)
from flexloop.admin.routers.prompts import get_prompts_dir
from flexloop.ai.factory import create_adapter
from flexloop.ai.prompts import PromptManager
from flexloop.config import settings
from flexloop.models.admin_user import AdminUser

router = APIRouter(prefix="/api/admin/playground", tags=["admin:playground"])


# --- Schemas --------------------------------------------------------------


class PlaygroundRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system_prompt: str
    user_prompt: str
    temperature: float | None = None
    max_tokens: int | None = None
    provider_override: str | None = None
    model_override: str | None = None
    api_key_override: str | None = None
    base_url_override: str | None = None


# --- Helpers --------------------------------------------------------------


def _event_to_data_line(event_dict: dict) -> str:
    """Format an event dict as a single ``data: <json>\\n\\n`` SSE line."""
    payload = {k: v for k, v in event_dict.items() if v is not None}
    return f"data: {json.dumps(payload)}\n\n"


# --- POST /run ------------------------------------------------------------


@router.post("/run")
async def run_playground(
    payload: PlaygroundRunRequest,
    _admin: AdminUser = Depends(require_admin),
) -> StreamingResponse:
    # Resolve provider/model/key/base_url: override values take precedence,
    # omitted fields fall back to saved settings.
    provider = payload.provider_override or settings.ai_provider
    model = payload.model_override or settings.ai_model
    api_key = (
        payload.api_key_override
        if payload.api_key_override is not None
        else settings.ai_api_key
    )
    base_url = (
        payload.base_url_override
        if payload.base_url_override is not None
        else settings.ai_base_url
    )
    temperature = (
        payload.temperature if payload.temperature is not None else settings.ai_temperature
    )
    max_tokens = (
        payload.max_tokens if payload.max_tokens is not None else settings.ai_max_tokens
    )

    adapter = create_adapter(
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
    )

    async def event_generator():
        try:
            async for event in adapter.stream_generate(
                system_prompt=payload.system_prompt,
                user_prompt=payload.user_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            ):
                yield _event_to_data_line(asdict(event))
        except Exception as exc:  # noqa: BLE001
            # Catch any exception raised OUTSIDE the adapter's own
            # error-handling path (e.g. create_adapter failure reaching
            # here would normally surface as an HTTPException, but an
            # error inside the async-for loop would propagate).
            yield _event_to_data_line({"type": "error", "error": str(exc)})
            yield _event_to_data_line({"type": "done"})

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

- [ ] **Step 5: Mount the router in `main.py`**

Add the import:
```python
from flexloop.admin.routers.playground import router as admin_playground_router
```

And `app.include_router(admin_playground_router)` next to the other admin include_routers.

- [ ] **Step 6: Run the tests**

```bash
uv run pytest tests/test_admin_playground.py::TestPlaygroundRun -v
```

Expected: all 4 pass.

- [ ] **Step 7: Full suite**

```bash
uv run pytest -q
```

Expected: 396 green (392 + 4 new).

- [ ] **Step 8: Commit**

```bash
git add src/flexloop/admin/routers/playground.py src/flexloop/main.py
git commit -m "feat(admin): POST /api/admin/playground/run with SSE streaming"
```

---

### Task 5: `GET /api/admin/playground/templates`

**Files:**
- Modify: `src/flexloop/admin/routers/playground.py`
- Modify: `tests/test_admin_playground.py`

- [ ] **Step 1: Write failing tests**

```python
class TestPlaygroundTemplates:
    async def test_requires_auth(self, client: AsyncClient) -> None:
        res = await client.get("/api/admin/playground/templates")
        assert res.status_code == 401

    async def test_returns_templates_with_variables(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        tmp_path,
    ) -> None:
        from flexloop.admin.routers.prompts import get_prompts_dir
        from flexloop.main import app

        # Seed a scratch prompts dir
        (tmp_path / "plan_generation").mkdir()
        (tmp_path / "plan_generation" / "v1.md").write_text("v1 {{a}}")
        (tmp_path / "plan_generation" / "v2.md").write_text(
            "v2 {{user_name}} {{goal}}"
        )
        (tmp_path / "chat").mkdir()
        (tmp_path / "chat" / "v1.md").write_text("chat {{message}}")
        (tmp_path / "manifest.json").write_text(
            json.dumps({
                "plan_generation": {"default": "v2"},
                "chat": {"default": "v1"},
            })
        )

        app.dependency_overrides[get_prompts_dir] = lambda: tmp_path
        try:
            cookies = await _make_admin_and_cookie(db_session)
            res = await client.get(
                "/api/admin/playground/templates",
                cookies=cookies,
            )
            assert res.status_code == 200
            body = res.json()
            assert "templates" in body
            by_name = {t["name"]: t for t in body["templates"]}
            assert by_name["plan_generation"]["active_version"] == "v2"
            assert set(by_name["plan_generation"]["variables"]) == {
                "user_name", "goal",
            }
            assert by_name["chat"]["active_version"] == "v1"
            assert by_name["chat"]["variables"] == ["message"]
        finally:
            app.dependency_overrides.pop(get_prompts_dir, None)

    async def test_empty_prompts_dir_returns_empty_list(
        self, client: AsyncClient, db_session: AsyncSession, tmp_path,
    ) -> None:
        from flexloop.admin.routers.prompts import get_prompts_dir
        from flexloop.main import app

        (tmp_path / "manifest.json").write_text("{}")
        app.dependency_overrides[get_prompts_dir] = lambda: tmp_path
        try:
            cookies = await _make_admin_and_cookie(db_session)
            res = await client.get(
                "/api/admin/playground/templates", cookies=cookies
            )
            assert res.status_code == 200
            assert res.json()["templates"] == []
        finally:
            app.dependency_overrides.pop(get_prompts_dir, None)
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/test_admin_playground.py::TestPlaygroundTemplates -v
```

Expected: 3 fail.

- [ ] **Step 3: Add schema + handler**

Append to `src/flexloop/admin/routers/playground.py`:

```python
class PlaygroundTemplate(BaseModel):
    name: str
    active_version: str
    variables: list[str]


class PlaygroundTemplatesResponse(BaseModel):
    templates: list[PlaygroundTemplate]


@router.get("/templates", response_model=PlaygroundTemplatesResponse)
async def list_templates(
    prompts_dir: Path = Depends(get_prompts_dir),
    _admin: AdminUser = Depends(require_admin),
) -> PlaygroundTemplatesResponse:
    from flexloop.admin import prompt_service

    infos = prompt_service.list_prompts(prompts_dir)
    templates: list[PlaygroundTemplate] = []
    for info in infos:
        active = info.active_by_provider.get("default")
        if not active:
            # Skip prompts with no default provider; the playground's
            # template picker only exposes default-active versions.
            continue
        try:
            content = read_version(prompts_dir, info.name, active)
        except Exception:  # noqa: BLE001
            # If the active version file is missing, skip rather than 500
            continue
        templates.append(
            PlaygroundTemplate(
                name=info.name,
                active_version=active,
                variables=extract_variables(content),
            )
        )
    return PlaygroundTemplatesResponse(templates=templates)
```

- [ ] **Step 4: Run the tests**

```bash
uv run pytest tests/test_admin_playground.py::TestPlaygroundTemplates -v
```

Expected: all 3 pass.

- [ ] **Step 5: Full suite**

```bash
uv run pytest -q
```

Expected: 399 green.

- [ ] **Step 6: Commit**

```bash
git add src/flexloop/admin/routers/playground.py tests/test_admin_playground.py
git commit -m "feat(admin): GET /api/admin/playground/templates"
```

---

### Task 6: `POST /api/admin/playground/render`

**Files:**
- Modify: `src/flexloop/admin/routers/playground.py`
- Modify: `tests/test_admin_playground.py`

- [ ] **Step 1: Write failing tests**

```python
class TestPlaygroundRender:
    async def test_requires_auth(self, client: AsyncClient) -> None:
        res = await client.post(
            "/api/admin/playground/render",
            json={"template_name": "plan_generation", "variables": {}},
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 401

    async def test_renders_template_with_variables(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        tmp_path,
    ) -> None:
        from flexloop.admin.routers.prompts import get_prompts_dir
        from flexloop.main import app

        (tmp_path / "plan_generation").mkdir()
        (tmp_path / "plan_generation" / "v1.md").write_text(
            "Generate a plan for {{user_name}} targeting {{goal}}."
        )
        (tmp_path / "manifest.json").write_text(
            json.dumps({"plan_generation": {"default": "v1"}})
        )

        app.dependency_overrides[get_prompts_dir] = lambda: tmp_path
        try:
            cookies = await _make_admin_and_cookie(db_session)
            res = await client.post(
                "/api/admin/playground/render",
                json={
                    "template_name": "plan_generation",
                    "variables": {
                        "user_name": "Alice",
                        "goal": "strength",
                    },
                },
                cookies=cookies,
                headers={"Origin": ORIGIN},
            )
            assert res.status_code == 200
            body = res.json()
            assert body["template_name"] == "plan_generation"
            assert body["version"] == "v1"
            assert body["rendered"] == (
                "Generate a plan for Alice targeting strength."
            )
        finally:
            app.dependency_overrides.pop(get_prompts_dir, None)

    async def test_missing_template_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        tmp_path,
    ) -> None:
        from flexloop.admin.routers.prompts import get_prompts_dir
        from flexloop.main import app

        (tmp_path / "manifest.json").write_text("{}")
        app.dependency_overrides[get_prompts_dir] = lambda: tmp_path
        try:
            cookies = await _make_admin_and_cookie(db_session)
            res = await client.post(
                "/api/admin/playground/render",
                json={"template_name": "nonexistent", "variables": {}},
                cookies=cookies,
                headers={"Origin": ORIGIN},
            )
            assert res.status_code == 404
        finally:
            app.dependency_overrides.pop(get_prompts_dir, None)

    async def test_missing_variables_leaves_placeholders(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        tmp_path,
    ) -> None:
        """Consistent with PromptManager.render: unfilled {{vars}} stay as literals."""
        from flexloop.admin.routers.prompts import get_prompts_dir
        from flexloop.main import app

        (tmp_path / "plan_generation").mkdir()
        (tmp_path / "plan_generation" / "v1.md").write_text(
            "Plan for {{user_name}} with {{goal}}"
        )
        (tmp_path / "manifest.json").write_text(
            json.dumps({"plan_generation": {"default": "v1"}})
        )

        app.dependency_overrides[get_prompts_dir] = lambda: tmp_path
        try:
            cookies = await _make_admin_and_cookie(db_session)
            res = await client.post(
                "/api/admin/playground/render",
                json={
                    "template_name": "plan_generation",
                    "variables": {"user_name": "Bob"},
                },
                cookies=cookies,
                headers={"Origin": ORIGIN},
            )
            assert res.status_code == 200
            body = res.json()
            assert body["rendered"] == "Plan for Bob with {{goal}}"
        finally:
            app.dependency_overrides.pop(get_prompts_dir, None)

    async def test_rejects_invalid_template_name(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        tmp_path,
    ) -> None:
        from flexloop.admin.routers.prompts import get_prompts_dir
        from flexloop.main import app

        (tmp_path / "manifest.json").write_text("{}")
        app.dependency_overrides[get_prompts_dir] = lambda: tmp_path
        try:
            cookies = await _make_admin_and_cookie(db_session)
            res = await client.post(
                "/api/admin/playground/render",
                json={
                    "template_name": "../etc/passwd",
                    "variables": {},
                },
                cookies=cookies,
                headers={"Origin": ORIGIN},
            )
            assert res.status_code == 400
        finally:
            app.dependency_overrides.pop(get_prompts_dir, None)
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/test_admin_playground.py::TestPlaygroundRender -v
```

Expected: 5 fail.

- [ ] **Step 3: Add schema + handler**

Append to `src/flexloop/admin/routers/playground.py`:

```python
class PlaygroundRenderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_name: str
    variables: dict[str, str]


class PlaygroundRenderResponse(BaseModel):
    template_name: str
    version: str
    rendered: str


@router.post("/render", response_model=PlaygroundRenderResponse)
async def render_template(
    payload: PlaygroundRenderRequest,
    prompts_dir: Path = Depends(get_prompts_dir),
    _admin: AdminUser = Depends(require_admin),
) -> PlaygroundRenderResponse:
    from flexloop.admin.prompt_service import (
        InvalidNameError,
        NotFoundError,
        _read_manifest,
    )

    # Validate the template name early — reuses the service layer's validator
    # by calling read_version on the active version. But first we need to
    # find the active version.
    try:
        manifest = _read_manifest(prompts_dir)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    if payload.template_name not in manifest:
        # Pass through the service's validation for invalid names (400) vs
        # genuinely missing templates (404). read_version validates the name
        # before it checks the file, so call it with a dummy version to get
        # the right error — except for valid-but-missing names which should
        # 404 cleanly.
        try:
            read_version(prompts_dir, payload.template_name, "v1")
        except InvalidNameError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc
        except NotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
            ) from exc
        # Fallback: if somehow the template name validates and the file
        # reads without error, return 404.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"template {payload.template_name!r} not found",
        )

    active_version = manifest[payload.template_name].get("default")
    if not active_version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"template {payload.template_name!r} has no default active version",
        )

    # Use PromptManager.render for consistency with the existing codebase.
    manager = PromptManager(prompts_dir)
    try:
        rendered = manager.render(payload.template_name, **payload.variables)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    return PlaygroundRenderResponse(
        template_name=payload.template_name,
        version=active_version,
        rendered=rendered,
    )
```

- [ ] **Step 4: Run the tests**

```bash
uv run pytest tests/test_admin_playground.py::TestPlaygroundRender -v
```

Expected: all 5 pass.

- [ ] **Step 5: Full suite**

```bash
uv run pytest -q
```

Expected: 404 green.

- [ ] **Step 6: Commit**

```bash
git add src/flexloop/admin/routers/playground.py tests/test_admin_playground.py
git commit -m "feat(admin): POST /api/admin/playground/render"
```

---

**End of Chunk 2.** All 3 playground endpoints are wired up with 12 integration tests. Next chunk starts the frontend.

---

## Chunk 3: Frontend — Playground page scaffold + SSE client

### Task 7: Regenerate `api.types.ts`

**Files:**
- Modify: `admin-ui/src/lib/api.types.ts`

Same pattern as previous chunks.

- [ ] **Step 1: Start the backend in the background + regenerate types**

```bash
cd /Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase4c
# Start backend (run_in_background: true):
uv run uvicorn flexloop.main:app --port 8000
# Then in a foreground call:
cd admin-ui && sleep 2 && npm run codegen
```

Expected: diff shows new entries for `PlaygroundRunRequest`, `PlaygroundTemplate`, `PlaygroundTemplatesResponse`, `PlaygroundRenderRequest`, `PlaygroundRenderResponse`.

- [ ] **Step 2: Stop the backend + commit**

```bash
cd ..
git add admin-ui/src/lib/api.types.ts
git commit -m "chore(admin-ui): regenerate api.types.ts for playground schemas"
```

---

### Task 8: `lib/sseReader.ts` — minimal SSE parser

**Files:**
- Create: `admin-ui/src/lib/sseReader.ts`

A small utility for parsing `data: <json>\n\n` events from a `Response.body` ReadableStream.

- [ ] **Step 1: Create the utility**

```tsx
/**
 * Minimal SSE (server-sent events) parser for fetch-based POST streams.
 *
 * EventSource only supports GET, so we use fetch() + ReadableStream to
 * carry a POST body AND read SSE responses. This parser accumulates
 * bytes from the reader and emits parsed JSON payloads from each
 * ``data: <json>\n\n`` line.
 *
 * Usage:
 *
 *   const res = await fetch("/api/admin/playground/run", {
 *     method: "POST",
 *     headers: {"Content-Type": "application/json"},
 *     body: JSON.stringify(payload),
 *     credentials: "same-origin",
 *   });
 *   for await (const event of parseSSE(res)) {
 *     if (event.type === "content") ...
 *   }
 */
export type SSEEvent = {
  type: string;
  [key: string]: unknown;
};

export async function* parseSSE(
  response: Response,
): AsyncGenerator<SSEEvent, void, unknown> {
  if (!response.body) {
    throw new Error("response has no body");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // SSE events are separated by a blank line (\n\n)
    const lines = buffer.split("\n\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("data:")) continue;
      const json = trimmed.slice("data:".length).trim();
      if (!json) continue;
      try {
        yield JSON.parse(json) as SSEEvent;
      } catch {
        // Malformed event — skip
      }
    }
  }
  // Flush any remaining buffer
  const trimmed = buffer.trim();
  if (trimmed.startsWith("data:")) {
    const json = trimmed.slice("data:".length).trim();
    if (json) {
      try {
        yield JSON.parse(json) as SSEEvent;
      } catch {
        // Malformed event — skip
      }
    }
  }
}
```

- [ ] **Step 2: Type-check**

```bash
cd admin-ui && npx tsc --noEmit
```

Expected: green.

- [ ] **Step 3: Commit**

```bash
cd ..
git add admin-ui/src/lib/sseReader.ts
git commit -m "feat(admin-ui): minimal SSE parser for fetch+ReadableStream"
```

---

### Task 9: Create `PlaygroundOutput` right-panel component

**Files:**
- Create: `admin-ui/src/components/playground/PlaygroundOutput.tsx`

Displays the streaming response text, token counts + latency, "Try parse as JSON" toggle.

- [ ] **Step 1: Write the component**

```tsx
/**
 * Right-panel output display for the playground.
 *
 * Shows:
 * - Accumulated streaming response text in a <pre>
 * - Token counts (input, output, cache_read) and latency
 * - "Try parse as JSON" toggle — attempts JSON.parse and shows either the
 *   formatted tree or the parse error
 * - Error banner if the stream emitted an ``error`` event
 */
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export type PlaygroundUsage = {
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  latency_ms: number;
};

type Props = {
  content: string;
  usage: PlaygroundUsage | null;
  error: string | null;
  isStreaming: boolean;
};

export function PlaygroundOutput({ content, usage, error, isStreaming }: Props) {
  const [tryJson, setTryJson] = useState(false);

  const jsonResult = useMemo(() => {
    if (!tryJson || !content) return null;
    try {
      const parsed = JSON.parse(content);
      return { ok: true, value: JSON.stringify(parsed, null, 2) };
    } catch (e) {
      return { ok: false, error: e instanceof Error ? e.message : String(e) };
    }
  }, [tryJson, content]);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-base">Response</CardTitle>
          <div className="flex items-center gap-2">
            {isStreaming && <Badge>streaming…</Badge>}
            {usage && (
              <Badge variant="secondary" className="tabular-nums">
                {usage.latency_ms} ms
              </Badge>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {error && (
            <pre className="text-xs bg-red-500/10 text-red-700 dark:text-red-400 p-2 rounded mb-3 whitespace-pre-wrap">
              {error}
            </pre>
          )}
          <pre className="font-mono text-xs whitespace-pre-wrap min-h-[200px] max-h-[50vh] overflow-auto bg-muted/30 p-3 rounded">
            {content || (
              <span className="text-muted-foreground">
                (No response yet — click Send)
              </span>
            )}
          </pre>
        </CardContent>
      </Card>

      {usage && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Usage</CardTitle>
          </CardHeader>
          <CardContent className="text-sm space-y-1 tabular-nums">
            <div>Input tokens: {usage.input_tokens}</div>
            <div>Output tokens: {usage.output_tokens}</div>
            <div>Cache read: {usage.cache_read_tokens}</div>
            <div>Latency: {usage.latency_ms} ms</div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-base">Try parse as JSON</CardTitle>
          <Button
            size="sm"
            variant={tryJson ? "default" : "outline"}
            onClick={() => setTryJson((v) => !v)}
          >
            {tryJson ? "On" : "Off"}
          </Button>
        </CardHeader>
        {tryJson && jsonResult && (
          <CardContent>
            {jsonResult.ok ? (
              <pre className="font-mono text-xs whitespace-pre-wrap max-h-[40vh] overflow-auto bg-muted/30 p-3 rounded">
                {jsonResult.value}
              </pre>
            ) : (
              <pre className="font-mono text-xs bg-red-500/10 text-red-700 dark:text-red-400 p-3 rounded whitespace-pre-wrap">
                Parse error: {jsonResult.error}
              </pre>
            )}
          </CardContent>
        )}
      </Card>
    </div>
  );
}
```

- [ ] **Step 2: Type-check + commit**

```bash
cd admin-ui && npx tsc --noEmit && cd ..
git add admin-ui/src/components/playground/PlaygroundOutput.tsx
git commit -m "feat(admin-ui): PlaygroundOutput with streaming text + JSON parse toggle"
```

---

### Task 10: Create `PlaygroundInput` left-panel component (free-form mode only)

**Files:**
- Create: `admin-ui/src/components/playground/PlaygroundInput.tsx`

Free-form mode with system/user textareas and advanced options. Template mode is added in Chunk 4.

- [ ] **Step 1: Write the component**

```tsx
/**
 * Left-panel input for the playground.
 *
 * Phase 4c Chunk 3: free-form mode ONLY (system + user textareas).
 * Chunk 4 will add template mode with a dropdown + variable form +
 * rendered preview.
 */
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

export type PlaygroundRunPayload = {
  system_prompt: string;
  user_prompt: string;
  temperature: number | null;
  max_tokens: number | null;
  provider_override: string | null;
  model_override: string | null;
  api_key_override: string | null;
  base_url_override: string | null;
};

type Props = {
  onSend: (payload: PlaygroundRunPayload) => void;
  isStreaming: boolean;
};

export function PlaygroundInput({ onSend, isStreaming }: Props) {
  const [systemPrompt, setSystemPrompt] = useState("You are a helpful assistant.");
  const [userPrompt, setUserPrompt] = useState("");
  const [temperature, setTemperature] = useState<string>("");
  const [maxTokens, setMaxTokens] = useState<string>("");
  const [providerOverride, setProviderOverride] = useState("");
  const [modelOverride, setModelOverride] = useState("");

  const canSend = userPrompt.trim().length > 0 && !isStreaming;

  const handleSend = () => {
    onSend({
      system_prompt: systemPrompt,
      user_prompt: userPrompt,
      temperature: temperature === "" ? null : Number(temperature),
      max_tokens: maxTokens === "" ? null : Number(maxTokens),
      provider_override: providerOverride || null,
      model_override: modelOverride || null,
      api_key_override: null,
      base_url_override: null,
    });
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Prompt</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="system_prompt">System prompt</Label>
            <Textarea
              id="system_prompt"
              rows={3}
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="user_prompt">User prompt</Label>
            <Textarea
              id="user_prompt"
              rows={8}
              value={userPrompt}
              onChange={(e) => setUserPrompt(e.target.value)}
              placeholder="Type your test prompt here…"
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Advanced</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="temperature">Temperature (blank = saved default)</Label>
            <Input
              id="temperature"
              type="number"
              step="0.05"
              value={temperature}
              onChange={(e) => setTemperature(e.target.value)}
              placeholder="0.7"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="max_tokens">Max tokens</Label>
            <Input
              id="max_tokens"
              type="number"
              value={maxTokens}
              onChange={(e) => setMaxTokens(e.target.value)}
              placeholder="2000"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="provider_override">Provider override</Label>
            <Input
              id="provider_override"
              value={providerOverride}
              onChange={(e) => setProviderOverride(e.target.value)}
              placeholder="(use saved)"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="model_override">Model override</Label>
            <Input
              id="model_override"
              value={modelOverride}
              onChange={(e) => setModelOverride(e.target.value)}
              placeholder="(use saved)"
            />
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button onClick={handleSend} disabled={!canSend}>
          {isStreaming ? "Streaming…" : "Send"}
        </Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Type-check + commit**

```bash
cd admin-ui && npx tsc --noEmit && cd ..
git add admin-ui/src/components/playground/PlaygroundInput.tsx
git commit -m "feat(admin-ui): PlaygroundInput with free-form mode + advanced options"
```

---

### Task 11: Create `PlaygroundPage` with two-panel layout + SSE wiring

**Files:**
- Create: `admin-ui/src/pages/PlaygroundPage.tsx`

- [ ] **Step 1: Write the page**

```tsx
/**
 * Admin AI Playground page.
 *
 * Two-panel layout: PlaygroundInput on the left, PlaygroundOutput on the
 * right. Send button fires a POST to /api/admin/playground/run and reads
 * the SSE response via parseSSE from lib/sseReader.
 *
 * Phase 4c Chunk 3: free-form mode only. Chunk 4 adds template mode and
 * the "Open in playground →" query param handler.
 */
import { useState } from "react";

import { PlaygroundInput } from "@/components/playground/PlaygroundInput";
import type { PlaygroundRunPayload } from "@/components/playground/PlaygroundInput";
import { PlaygroundOutput } from "@/components/playground/PlaygroundOutput";
import type { PlaygroundUsage } from "@/components/playground/PlaygroundOutput";
import { parseSSE } from "@/lib/sseReader";

export function PlaygroundPage() {
  const [content, setContent] = useState("");
  const [usage, setUsage] = useState<PlaygroundUsage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);

  const send = async (payload: PlaygroundRunPayload) => {
    setContent("");
    setUsage(null);
    setError(null);
    setIsStreaming(true);
    try {
      const res = await fetch("/api/admin/playground/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        credentials: "same-origin",
      });
      if (!res.ok) {
        const text = await res.text();
        setError(`HTTP ${res.status}: ${text}`);
        setIsStreaming(false);
        return;
      }
      for await (const event of parseSSE(res)) {
        if (event.type === "content") {
          setContent((prev) => prev + (event.delta as string));
        } else if (event.type === "usage") {
          setUsage({
            input_tokens: (event.input_tokens as number) ?? 0,
            output_tokens: (event.output_tokens as number) ?? 0,
            cache_read_tokens: (event.cache_read_tokens as number) ?? 0,
            latency_ms: (event.latency_ms as number) ?? 0,
          });
        } else if (event.type === "error") {
          setError((event.error as string) ?? "unknown error");
        } else if (event.type === "done") {
          // Done — nothing to do, the stream will end on its own
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setIsStreaming(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Playground</h1>
        <p className="text-sm text-muted-foreground">
          Test prompts against the configured AI provider. The "Try parse as
          JSON" toggle is your friend for catching malformed responses.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <PlaygroundInput onSend={send} isStreaming={isStreaming} />
        <PlaygroundOutput
          content={content}
          usage={usage}
          error={error}
          isStreaming={isStreaming}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

```bash
cd admin-ui && npx tsc --noEmit
```

Expected: green.

- [ ] **Step 3: Commit**

```bash
cd ..
git add admin-ui/src/pages/PlaygroundPage.tsx
git commit -m "feat(admin-ui): PlaygroundPage with two-panel layout + SSE streaming"
```

---

### Task 12: Wire `/ai/playground` route + enable sidebar item

**Files:**
- Modify: `admin-ui/src/App.tsx`
- Modify: `admin-ui/src/components/AppSidebar.tsx`

- [ ] **Step 1: Add the route in App.tsx**

```tsx
import { PlaygroundPage } from "@/pages/PlaygroundPage";
// ... inside the authenticated layout Routes:
<Route path="ai/playground" element={<PlaygroundPage />} />
```

- [ ] **Step 2: Enable sidebar**

In `admin-ui/src/components/AppSidebar.tsx` find:

```tsx
{ label: "Playground", to: "/ai/playground", icon: FlaskConical, disabled: true },
```

Remove `disabled: true`:

```tsx
{ label: "Playground", to: "/ai/playground", icon: FlaskConical },
```

- [ ] **Step 3: Build**

```bash
cd admin-ui && npx tsc --noEmit && npm run build
```

Expected: both green.

- [ ] **Step 4: Commit**

```bash
cd ..
git add admin-ui/src/App.tsx admin-ui/src/components/AppSidebar.tsx
git commit -m "feat(admin-ui): wire /ai/playground route + enable sidebar item"
```

---

**End of Chunk 3.** Free-form playground is fully functional — user can type prompts and see streaming responses. Next chunk adds template mode and the cross-link from the Prompts page.

---

## Chunk 4: Frontend — template mode + "Open in playground" cross-link

### Task 13: Create `TemplateForm` variable form component

**Files:**
- Create: `admin-ui/src/components/playground/TemplateForm.tsx`

- [ ] **Step 1: Write the component**

```tsx
/**
 * Variable form for template mode in the playground.
 *
 * Given a list of variable names (from the template's {{...}} extraction),
 * renders one text input per variable. Returns the current values via
 * a controlled callback.
 */
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type Props = {
  variables: string[];
  values: Record<string, string>;
  onChange: (values: Record<string, string>) => void;
};

export function TemplateForm({ variables, values, onChange }: Props) {
  if (variables.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        This template has no variables.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {variables.map((v) => (
        <div key={v} className="space-y-1.5">
          <Label htmlFor={`var-${v}`}>{v}</Label>
          <Input
            id={`var-${v}`}
            value={values[v] ?? ""}
            onChange={(e) =>
              onChange({ ...values, [v]: e.target.value })
            }
          />
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Type-check + commit**

```bash
cd admin-ui && npx tsc --noEmit && cd ..
git add admin-ui/src/components/playground/TemplateForm.tsx
git commit -m "feat(admin-ui): TemplateForm variable inputs"
```

---

### Task 14: Add template mode to `PlaygroundInput`

**Files:**
- Modify: `admin-ui/src/components/playground/PlaygroundInput.tsx`

- [ ] **Step 1: Extend the component with a mode toggle + template dropdown + render preview**

Update the imports at the top:

```tsx
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { TemplateForm } from "@/components/playground/TemplateForm";
import { api } from "@/lib/api";
import type { components } from "@/lib/api.types";

type TemplatesResponse = components["schemas"]["PlaygroundTemplatesResponse"];
type RenderResponse = components["schemas"]["PlaygroundRenderResponse"];
```

Extend the `Props` type to accept an `initialTemplate` hint (for the "Open in playground →" deep link):

```tsx
type Props = {
  onSend: (payload: PlaygroundRunPayload) => void;
  isStreaming: boolean;
  initialTemplate?: string | null;
};
```

Add mode state + template state + template query near the top of the component:

```tsx
type Mode = "free" | "template";

const [mode, setMode] = useState<Mode>(initialTemplate ? "template" : "free");
const [selectedTemplate, setSelectedTemplate] = useState<string | null>(
  initialTemplate ?? null,
);
const [templateVars, setTemplateVars] = useState<Record<string, string>>({});

const templatesQuery = useQuery({
  queryKey: ["admin", "playground", "templates"],
  queryFn: () => api.get<TemplatesResponse>("/api/admin/playground/templates"),
});

// When template selection or vars change, re-render the user_prompt
useEffect(() => {
  if (mode !== "template" || !selectedTemplate) return;
  let cancelled = false;
  (async () => {
    try {
      const res = await api.post<RenderResponse>(
        "/api/admin/playground/render",
        { template_name: selectedTemplate, variables: templateVars },
      );
      if (!cancelled) setUserPrompt(res.rendered);
    } catch (e) {
      if (!cancelled) setUserPrompt("(failed to render template)");
    }
  })();
  return () => {
    cancelled = true;
  };
}, [mode, selectedTemplate, templateVars]);

const selectedTemplateInfo = templatesQuery.data?.templates.find(
  (t) => t.name === selectedTemplate,
);
```

Insert a mode toggle at the top of the rendered JSX, before the first `<Card>`:

```tsx
<div className="flex items-center gap-2 mb-4">
  <Button
    size="sm"
    variant={mode === "free" ? "default" : "outline"}
    onClick={() => setMode("free")}
  >
    Free-form
  </Button>
  <Button
    size="sm"
    variant={mode === "template" ? "default" : "outline"}
    onClick={() => setMode("template")}
  >
    From template
  </Button>
</div>
```

Insert a "Template" card between the "Prompt" card and "Advanced" card, rendered only when `mode === "template"`:

```tsx
{mode === "template" && (
  <Card>
    <CardHeader className="pb-2">
      <CardTitle className="text-base">Template</CardTitle>
    </CardHeader>
    <CardContent className="space-y-3">
      <div className="space-y-1.5">
        <Label htmlFor="template_select">Template</Label>
        <Select
          value={selectedTemplate ?? ""}
          onValueChange={(v) => {
            setSelectedTemplate(v);
            setTemplateVars({});
          }}
        >
          <SelectTrigger id="template_select">
            <SelectValue placeholder="(select a template)" />
          </SelectTrigger>
          <SelectContent>
            {(templatesQuery.data?.templates ?? []).map((t) => (
              <SelectItem key={t.name} value={t.name}>
                {t.name} ({t.active_version})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {selectedTemplateInfo && (
        <TemplateForm
          variables={selectedTemplateInfo.variables}
          values={templateVars}
          onChange={setTemplateVars}
        />
      )}
    </CardContent>
  </Card>
)}
```

(Place this between the "Prompt" card's closing `</Card>` and the "Advanced" card's opening `<Card>`.)

- [ ] **Step 2: Type-check + build**

```bash
cd admin-ui && npx tsc --noEmit && npm run build
```

Expected: both green.

- [ ] **Step 3: Commit**

```bash
cd ..
git add admin-ui/src/components/playground/PlaygroundInput.tsx
git commit -m "feat(admin-ui): template mode in PlaygroundInput"
```

---

### Task 15: Wire template mode through `PlaygroundPage` + query-param deep link

**Files:**
- Modify: `admin-ui/src/pages/PlaygroundPage.tsx`

- [ ] **Step 1: Read the `?template=` query param and pass it to `PlaygroundInput`**

Update imports at the top of `PlaygroundPage.tsx`:

```tsx
import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import { PlaygroundInput } from "@/components/playground/PlaygroundInput";
import type { PlaygroundRunPayload } from "@/components/playground/PlaygroundInput";
import { PlaygroundOutput } from "@/components/playground/PlaygroundOutput";
import type { PlaygroundUsage } from "@/components/playground/PlaygroundOutput";
import { parseSSE } from "@/lib/sseReader";
```

Inside `PlaygroundPage` component, read the search param:

```tsx
const [searchParams] = useSearchParams();
const initialTemplate = searchParams.get("template");
```

Pass it to `PlaygroundInput`:

```tsx
<PlaygroundInput
  onSend={send}
  isStreaming={isStreaming}
  initialTemplate={initialTemplate}
/>
```

- [ ] **Step 2: Type-check + commit**

```bash
cd admin-ui && npx tsc --noEmit && cd ..
git add admin-ui/src/pages/PlaygroundPage.tsx
git commit -m "feat(admin-ui): PlaygroundPage reads ?template= query param"
```

---

### Task 16: Add "Open in playground →" button to `PromptToolbar`

**Files:**
- Modify: `admin-ui/src/components/prompts/PromptToolbar.tsx`
- Modify: `admin-ui/src/pages/PromptsPage.tsx`

- [ ] **Step 1: Add the button + callback prop to `PromptToolbar.tsx`**

Extend `Props` to include a new callback:

```tsx
type Props = {
  isDirty: boolean;
  isSaving: boolean;
  isCreating: boolean;
  isSettingActive: boolean;
  canSetActive: boolean;
  onSave: () => void;
  onNewVersion: () => void;
  onSetActive: () => void;
  onOpenDiff: () => void;
  onOpenInPlayground: () => void;
};
```

Add the button as the last one in the toolbar row (after "Diff…"):

```tsx
<Button size="sm" variant="ghost" onClick={onOpenInPlayground}>
  Open in playground →
</Button>
```

- [ ] **Step 2: Wire the callback in `PromptsPage.tsx`**

Add a navigation import at the top (if not already present):

```tsx
import { useNavigate } from "react-router-dom";
```

Inside `PromptsPage`, add:

```tsx
const navigate = useNavigate();
```

Pass the callback to `PromptToolbar`:

```tsx
onOpenInPlayground={() =>
  selected && navigate(`/ai/playground?template=${encodeURIComponent(selected.name)}`)
}
```

- [ ] **Step 3: Type-check + build**

```bash
cd admin-ui && npx tsc --noEmit && npm run build
```

Expected: both green.

- [ ] **Step 4: Commit**

```bash
cd ..
git add admin-ui/src/components/prompts/PromptToolbar.tsx admin-ui/src/pages/PromptsPage.tsx
git commit -m "feat(admin-ui): 'Open in playground →' button on prompt toolbar"
```

---

**End of Chunk 4.** Playground is feature-complete: free-form mode, template mode, deep-link from Prompts page. Next chunk is smoke + merge.

---

## Chunk 5: Smoke test and merge

### Task 17: Write the smoke test checklist

**Files:**
- Create: `docs/admin-dashboard-phase4c-smoke-test.md` (at parent FlexLoop level)

- [ ] **Step 1: Write the checklist**

```markdown
# Phase 4c (AI Playground) smoke test

Manual checklist plus automated Playwright subset.

## Environment

- [ ] Backend running
- [ ] Admin UI built
- [ ] Valid AI provider config in `app_settings` (can use a fake/stub for headless smoke — the smoke script monkeypatches `create_adapter`)
- [ ] At least 2 prompts in `prompts/` for the template-mode test (the script uses scratch prompts via `PROMPTS_DIR`)
- [ ] Logged in as admin

## Playground page — free-form mode

- [ ] Navigate to /admin/ai/playground — sidebar item enabled, page loads
- [ ] Two panels visible: input on the left, output on the right
- [ ] System/user textareas present, "Send" button disabled while user prompt is empty
- [ ] Fill in a user prompt, click Send → streaming badge appears, content accumulates in the output pre
- [ ] Token counts (input, output, cache_read) + latency_ms appear in the Usage card after the stream finishes
- [ ] "streaming…" badge disappears after the `done` event

## Try parse as JSON

- [ ] With a response that is NOT valid JSON, toggle "Try parse as JSON" on → parse error appears in red box
- [ ] With a response that IS valid JSON (e.g. `{"hello": "world"}`), the parse result shows formatted `<pre>`

## Error handling

- [ ] With a garbage provider override, send → output shows the error message without a 500 page
- [ ] Running more than once — each send clears the previous output first

## Template mode

- [ ] Toggle to "From template" mode
- [ ] Template dropdown lists all prompts with their active version in parentheses
- [ ] Selecting a template populates the variable form
- [ ] Filling in variables triggers a server render and updates the user_prompt textarea with the rendered content
- [ ] Click Send — the rendered content is what gets sent (not the raw template)

## Open in playground (cross-link)

- [ ] From /admin/ai/prompts, select a prompt, click "Open in playground →" — navigates to /admin/ai/playground?template=<name>
- [ ] Playground auto-selects template mode with the pre-picked template
- [ ] Variable form renders, render preview populates on empty vars

## Regression checks

- [ ] iOS-facing endpoints still work: `curl http://localhost:8000/api/plans?user_id=1`
- [ ] Phase 4b Prompts page still loads at /admin/ai/prompts
- [ ] Phase 4a Config page still loads at /admin/ai/config

## Automated

- [ ] `uv run pytest -q` — full suite green (expected 404 tests)
- [ ] `cd admin-ui && npm run build` — succeeds
- [ ] Playwright smoke script at `/tmp/smoke_phase4c.py` — all checks green
```

- [ ] **Step 2: Commit to parent**

```bash
cd /Users/flyingchickens/Projects/FlexLoop
git add docs/admin-dashboard-phase4c-smoke-test.md
git commit -m "docs(admin): phase 4c smoke test checklist"
cd /Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase4c
```

---

### Task 18: Run the automated Playwright smoke test

The phase 4c smoke is trickier than 4a/4b because the backend `/run` endpoint is SSE streaming AND requires a real AI provider OR a monkeypatched `create_adapter`. Since the Playwright test runs the real backend, monkeypatching isn't trivial. Two options:

- **Option A (preferred):** run the backend with a `FAKE_ADAPTER=1` env var that `create_adapter` honors to return a stub adapter. This requires a small addition to `flexloop.ai.factory`.
- **Option B:** skip the streaming part in the headless test and rely on the pytest integration tests for streaming coverage. The headless test covers: page loads, tree/template dropdown populates, variable form renders, send button is disabled correctly, "Open in playground" deep link navigation. NOT the actual stream.

Go with **Option B** to avoid modifying `flexloop.ai.factory`. The pytest integration tests already cover the streaming path with monkeypatch.

- [ ] **Step 1: Reuse or recreate the playwright venv**

```bash
if [ ! -x /tmp/phase4b-playwright-venv/bin/python3 ]; then
  python3 -m venv /tmp/phase4c-playwright-venv
  /tmp/phase4c-playwright-venv/bin/pip install playwright
  /tmp/phase4c-playwright-venv/bin/playwright install chromium
else
  ln -sf /tmp/phase4b-playwright-venv /tmp/phase4c-playwright-venv
fi
```

- [ ] **Step 2: Create `/tmp/seed_phase4c_smoke.py`** — seeds admin user + a scratch prompts dir with 2 prompts (mirrors phase 4b's seed script). The playground's template dropdown reads from this dir via `PROMPTS_DIR`.

- [ ] **Step 3: Create `/tmp/smoke_phase4c.py`** — Playwright script covering:
  1. Login
  2. Navigate to /ai/playground
  3. Verify both panels render
  4. Verify "Send" is disabled initially (empty user prompt)
  5. Type into user prompt → Send becomes enabled
  6. **Skip the actual Send click** (would hit real AI provider)
  7. Toggle to "From template" mode → dropdown lists templates
  8. Select plan_generation → variable form renders
  9. Navigate to /ai/prompts → click a prompt → click "Open in playground →" → verify URL contains `?template=<name>` and template mode is auto-selected
  10. Regression: GET /api/plans?user_id=1 returns 200

- [ ] **Step 4: Run the smoke**

```bash
cd /Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase4c
rm -f /tmp/flexloop-phase4c-smoke.db
rm -rf /tmp/flexloop-phase4c-prompts
DATABASE_URL='sqlite+aiosqlite:////tmp/flexloop-phase4c-smoke.db' \
  PROMPTS_DIR=/tmp/flexloop-phase4c-prompts \
  uv run python /tmp/seed_phase4c_smoke.py
DATABASE_URL='sqlite+aiosqlite:////tmp/flexloop-phase4c-smoke.db' \
  PROMPTS_DIR=/tmp/flexloop-phase4c-prompts \
  python3 /Users/flyingchickens/.claude/plugins/cache/anthropic-agent-skills/example-skills/b0cbd3df1533/skills/webapp-testing/scripts/with_server.py \
  --server 'uv run uvicorn flexloop.main:app --port 8000' \
  --port 8000 --timeout 60 \
  -- /tmp/phase4c-playwright-venv/bin/python3 /tmp/smoke_phase4c.py
```

Expected: ALL SMOKE TESTS PASSED.

- [ ] **Step 5: Mark checklist as executed**

Prepend to `docs/admin-dashboard-phase4c-smoke-test.md`:

```markdown
> **Automated Playwright smoke executed YYYY-MM-DD — all checks ✅.**
```

Commit the update to the parent FlexLoop repo's docs.

---

### Task 19: Merge `feat/admin-dashboard-phase4c-playground` to main

- [ ] **Step 1: Verify clean + commit count**

```bash
cd /Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase4c
git status
git log --oneline main..HEAD | wc -l
```

Expected: clean, ~18-20 commits.

- [ ] **Step 2: Fast-forward merge**

```bash
cd /Users/flyingchickens/Projects/FlexLoop/flexloop-server
git checkout main
git merge --ff-only feat/admin-dashboard-phase4c-playground
```

- [ ] **Step 3: Full suite on main**

```bash
uv run pytest -q
```

Expected: 404 tests green.

- [ ] **Step 4: Push main**

```bash
git push origin main
```

- [ ] **Step 5: Bump parent submodule**

```bash
cd /Users/flyingchickens/Projects/FlexLoop
git add flexloop-server
git commit -m "chore: bump flexloop-server to admin dashboard phase 4c"
```

- [ ] **Step 6: Clean up worktree + feature branch**

```bash
cd /Users/flyingchickens/Projects/FlexLoop/flexloop-server
git worktree remove /Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase4c
git branch -d feat/admin-dashboard-phase4c-playground
```

- [ ] **Step 7: Update memory status file**

Edit `/Users/flyingchickens/.claude/projects/-Users-flyingchickens-Projects-FlexLoop/memory/project_admin_dashboard_status.md`:
- Mark phase 4c COMPLETE
- Move phase 4d (AI Usage dashboard) into "next up"

---

**End of Chunk 5.** Plan 4c is shipped.

---

## Summary

**Backend deliverables:**
- `src/flexloop/ai/base.py` — new `StreamEvent` dataclass + concrete `LLMAdapter.stream_generate` fallback
- `src/flexloop/ai/openai_adapter.py` — `stream_generate` override with true per-delta events
- `src/flexloop/admin/routers/playground.py` — 3 endpoints (run/templates/render) with `StreamingResponse` for SSE
- `src/flexloop/main.py` — register router
- 2 test files (~21 tests total): `test_adapter_streaming.py` (9 unit), `test_admin_playground.py` (12 integration)

**Frontend deliverables:**
- `admin-ui/src/lib/sseReader.ts` — minimal SSE parser over fetch+ReadableStream
- `admin-ui/src/pages/PlaygroundPage.tsx` — two-panel page with SSE wiring + query-param deep link
- `admin-ui/src/components/playground/` — 3 sub-components: `PlaygroundInput`, `PlaygroundOutput`, `TemplateForm`
- `admin-ui/src/components/prompts/PromptToolbar.tsx` + `PromptsPage.tsx` — "Open in playground →" button
- `admin-ui/src/App.tsx` + `AppSidebar.tsx` — new route + enabled sidebar item
- `admin-ui/src/lib/api.types.ts` — regenerated

**Docs:** `docs/admin-dashboard-phase4c-smoke-test.md`

**End state:** operators can type any system/user prompt pair into the playground, watch the response stream in real time, toggle "Try parse as JSON" to catch malformed responses, switch to template mode to render a registered prompt with variables, and deep-link from the Prompts editor. Phase 4d (AI Usage dashboard) is the last sub-plan remaining.
