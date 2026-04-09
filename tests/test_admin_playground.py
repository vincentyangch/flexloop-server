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
