"""Integration tests for /api/admin/config."""
from __future__ import annotations

from types import SimpleNamespace

import httpx
import openai
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import SESSION_COOKIE_NAME, create_session, hash_password
from flexloop.config import _DB_BACKED_FIELDS, settings
from flexloop.models.admin_audit_log import AdminAuditLog
from flexloop.models.admin_user import AdminUser
from flexloop.models.app_settings import AppSettings
from tests.fixtures.auth_json_factory import make_auth_json


ORIGIN = "http://localhost:5173"


def _usage() -> SimpleNamespace:
    return SimpleNamespace(
        prompt_tokens=5,
        completion_tokens=2,
        prompt_tokens_details=SimpleNamespace(cached_tokens=0),
    )


def _stream_chunk(delta: str | None = None, usage=None) -> SimpleNamespace:
    choices = []
    if delta is not None:
        choices = [SimpleNamespace(delta=SimpleNamespace(content=delta))]
    return SimpleNamespace(choices=choices, usage=usage)


class _CodexChatCompletions:
    def __init__(self, owner: "_CodexAsyncOpenAI") -> None:
        self._owner = owner

    async def create(self, **kwargs):
        _CodexAsyncOpenAI.chat_requests.append(
            {"api_key": self._owner.api_key, "kwargs": kwargs}
        )
        if _CodexAsyncOpenAI.chat_error is not None:
            raise _CodexAsyncOpenAI.chat_error

        async def _stream():
            yield _stream_chunk("codex ")
            yield _stream_chunk("ok")
            yield _stream_chunk(usage=_usage())

        return _stream()


class _CodexResponses:
    def __init__(self, owner: "_CodexAsyncOpenAI") -> None:
        self._owner = owner

    async def create(self, **kwargs):
        _CodexAsyncOpenAI.responses_requests.append(
            {"api_key": self._owner.api_key, "kwargs": kwargs}
        )
        return SimpleNamespace(
            output="fallback",
            usage=SimpleNamespace(
                input_tokens=3,
                output_tokens=1,
                input_tokens_details={"cached_tokens": 0},
            ),
        )


class _CodexAsyncOpenAI:
    chat_requests: list[dict] = []
    responses_requests: list[dict] = []
    chat_error: Exception | None = None

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.default_headers = default_headers
        self.chat = SimpleNamespace(completions=_CodexChatCompletions(self))
        self.responses = _CodexResponses(self)

    @classmethod
    def reset(cls) -> None:
        cls.chat_requests = []
        cls.responses_requests = []
        cls.chat_error = None


@pytest.fixture(autouse=True)
def _restore_settings_singleton():
    """Snapshot the runtime-mutable fields on ``settings`` before each test
    and restore them on teardown.

    Prevents state leakage between tests — especially important because
    ``test_refreshes_settings_singleton`` writes values like
    ``admin_allowed_origins=["https://admin.example.com"]`` that would
    otherwise block future admin write tests at the CSRF layer.
    """
    snapshot = {f: getattr(settings, f) for f in _DB_BACKED_FIELDS}
    # Copy lists so subsequent mutations don't alias the snapshot
    for key, value in list(snapshot.items()):
        if isinstance(value, list):
            snapshot[key] = list(value)
    yield
    for key, value in snapshot.items():
        setattr(settings, key, value)


async def _make_admin_and_cookie(db: AsyncSession) -> tuple[AdminUser, dict[str, str]]:
    admin = AdminUser(username="tester", password_hash=hash_password("password123"))
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    token, _ = await create_session(db, admin_user_id=admin.id)
    return admin, {SESSION_COOKIE_NAME: token}


async def _seed_default_app_settings(db: AsyncSession) -> AppSettings:
    row = AppSettings(
        id=1,
        ai_provider="openai",
        ai_model="gpt-4o-mini",
        ai_api_key="sk-test-1234567xyz",
        ai_base_url="",
        codex_auth_file="~/.codex/auth.json",
        ai_reasoning_effort="medium",
        ai_temperature=0.7,
        ai_max_tokens=2000,
        ai_review_frequency="block",
        ai_review_block_weeks=6,
        admin_allowed_origins=["http://localhost:5173", "http://localhost:8000"],
    )
    db.add(row)
    await db.commit()
    return row


class TestGetConfig:
    async def test_requires_auth(self, client: AsyncClient) -> None:
        assert (await client.get("/api/admin/config")).status_code == 401

    async def test_404_when_row_missing(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, cookies = await _make_admin_and_cookie(db_session)
        res = await client.get("/api/admin/config", cookies=cookies)
        assert res.status_code == 404

    async def test_returns_masked_api_key(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, cookies = await _make_admin_and_cookie(db_session)
        await _seed_default_app_settings(db_session)
        res = await client.get("/api/admin/config", cookies=cookies)
        assert res.status_code == 200
        body = res.json()
        assert body["ai_provider"] == "openai"
        assert body["ai_model"] == "gpt-4o-mini"
        # Masked: last 3 chars preserved, everything else bullets
        assert body["ai_api_key"].endswith("xyz")
        assert "sk-test" not in body["ai_api_key"]
        assert body["ai_max_tokens"] == 2000
        assert body["admin_allowed_origins"] == [
            "http://localhost:5173",
            "http://localhost:8000",
        ]

    async def test_empty_key_returns_empty_string(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, cookies = await _make_admin_and_cookie(db_session)
        row = await _seed_default_app_settings(db_session)
        row.ai_api_key = ""
        await db_session.commit()
        res = await client.get("/api/admin/config", cookies=cookies)
        assert res.status_code == 200
        assert res.json()["ai_api_key"] == ""

    async def test_get_config_includes_new_fields(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, cookies = await _make_admin_and_cookie(db_session)
        await _seed_default_app_settings(db_session)

        res = await client.get("/api/admin/config", cookies=cookies)

        assert res.status_code == 200
        body = res.json()
        assert body["codex_auth_file"] == "~/.codex/auth.json"
        assert body["ai_reasoning_effort"] == "medium"


class TestUpdateConfig:
    async def test_requires_auth(self, client: AsyncClient) -> None:
        res = await client.put(
            "/api/admin/config",
            json={"ai_provider": "anthropic"},
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 401

    async def test_404_when_row_missing(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, cookies = await _make_admin_and_cookie(db_session)
        res = await client.put(
            "/api/admin/config",
            json={"ai_provider": "anthropic"},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 404

    async def test_updates_fields(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, cookies = await _make_admin_and_cookie(db_session)
        await _seed_default_app_settings(db_session)
        res = await client.put(
            "/api/admin/config",
            json={
                "ai_provider": "anthropic",
                "ai_model": "claude-3-5-sonnet",
                "ai_temperature": 0.3,
            },
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["ai_provider"] == "anthropic"
        assert body["ai_model"] == "claude-3-5-sonnet"
        assert body["ai_temperature"] == 0.3
        # Unchanged fields still present
        assert body["ai_max_tokens"] == 2000

    async def test_updates_api_key_plaintext(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, cookies = await _make_admin_and_cookie(db_session)
        await _seed_default_app_settings(db_session)
        res = await client.put(
            "/api/admin/config",
            json={"ai_api_key": "sk-new-key-9999abc"},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 200
        # Response is masked, not plaintext
        assert res.json()["ai_api_key"].endswith("abc")
        assert "sk-new-key" not in res.json()["ai_api_key"]
        # DB has the plaintext
        row = (
            await db_session.execute(select(AppSettings).where(AppSettings.id == 1))
        ).scalar_one()
        assert row.ai_api_key == "sk-new-key-9999abc"

    async def test_put_config_updates_codex_fields(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, cookies = await _make_admin_and_cookie(db_session)
        await _seed_default_app_settings(db_session)

        res = await client.put(
            "/api/admin/config",
            json={
                "codex_auth_file": "/tmp/custom-codex-auth.json",
                "ai_reasoning_effort": "high",
            },
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )

        assert res.status_code == 200
        body = res.json()
        assert body["codex_auth_file"] == "/tmp/custom-codex-auth.json"
        assert body["ai_reasoning_effort"] == "high"
        row = (
            await db_session.execute(select(AppSettings).where(AppSettings.id == 1))
        ).scalar_one()
        assert row.codex_auth_file == "/tmp/custom-codex-auth.json"
        assert row.ai_reasoning_effort == "high"

    async def test_masked_key_input_is_treated_as_no_change(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """If the client PUTs the masked form back (e.g. didn't touch the
        key field), the server must NOT overwrite the stored plaintext
        with the bullets.
        """
        _, cookies = await _make_admin_and_cookie(db_session)
        await _seed_default_app_settings(db_session)
        # Fetch to learn the current masked value
        get_res = await client.get("/api/admin/config", cookies=cookies)
        masked_key = get_res.json()["ai_api_key"]
        # Submit it back unchanged
        res = await client.put(
            "/api/admin/config",
            json={"ai_api_key": masked_key, "ai_provider": "anthropic"},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 200
        # DB still has the original plaintext
        row = (
            await db_session.execute(select(AppSettings).where(AppSettings.id == 1))
        ).scalar_one()
        assert row.ai_api_key == "sk-test-1234567xyz"
        assert row.ai_provider == "anthropic"

    async def test_rejects_unknown_field(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, cookies = await _make_admin_and_cookie(db_session)
        await _seed_default_app_settings(db_session)
        res = await client.put(
            "/api/admin/config",
            json={"totally_wrong_field": "whatever"},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 422

    async def test_writes_audit_log_on_change(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        admin, cookies = await _make_admin_and_cookie(db_session)
        await _seed_default_app_settings(db_session)
        res = await client.put(
            "/api/admin/config",
            json={"ai_provider": "anthropic", "ai_temperature": 0.3},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 200
        entries = (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "config_update")
            )
        ).scalars().all()
        assert len(entries) == 1
        entry = entries[0]
        assert entry.admin_user_id == admin.id
        assert entry.target_type == "app_settings"
        assert entry.target_id == "1"
        assert entry.before_json is not None
        assert entry.after_json is not None
        assert entry.before_json["ai_provider"] == "openai"
        assert entry.after_json["ai_provider"] == "anthropic"
        # API key must be masked in both snapshots
        assert "sk-test" not in entry.before_json["ai_api_key"]
        assert "sk-test" not in entry.after_json["ai_api_key"]

    async def test_put_config_audit_log_captures_new_fields(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        admin, cookies = await _make_admin_and_cookie(db_session)
        await _seed_default_app_settings(db_session)

        res = await client.put(
            "/api/admin/config",
            json={
                "codex_auth_file": "/tmp/audit-auth.json",
                "ai_reasoning_effort": "low",
            },
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )

        assert res.status_code == 200
        entry = (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "config_update")
            )
        ).scalar_one()
        assert entry.admin_user_id == admin.id
        assert entry.before_json["codex_auth_file"] == "~/.codex/auth.json"
        assert entry.after_json["codex_auth_file"] == "/tmp/audit-auth.json"
        assert entry.before_json["ai_reasoning_effort"] == "medium"
        assert entry.after_json["ai_reasoning_effort"] == "low"

    async def test_no_audit_log_when_nothing_changes(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, cookies = await _make_admin_and_cookie(db_session)
        await _seed_default_app_settings(db_session)
        res = await client.put(
            "/api/admin/config",
            json={"ai_provider": "openai"},  # same as current
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 200
        entries = (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "config_update")
            )
        ).all()
        assert len(entries) == 0

    async def test_refreshes_settings_singleton(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """After PUT, the in-memory settings singleton must reflect the
        new values — this is what makes the CSRF middleware pick up a new
        allowed-origins list without restart.
        """
        from flexloop.config import settings

        _, cookies = await _make_admin_and_cookie(db_session)
        await _seed_default_app_settings(db_session)
        res = await client.put(
            "/api/admin/config",
            json={"admin_allowed_origins": ["https://admin.example.com"]},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 200
        assert settings.admin_allowed_origins == ["https://admin.example.com"]


class TestTestConnection:
    async def test_requires_auth(self, client: AsyncClient) -> None:
        res = await client.post(
            "/api/admin/config/test-connection",
            json={},
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 401

    async def test_returns_ok_with_fake_adapter(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from flexloop.ai.base import LLMResponse
        from flexloop.admin.routers import config as config_router

        class _FakeAdapter:
            def __init__(self, *a, **kw):
                pass

            async def generate(self, system_prompt, user_prompt, temperature, max_tokens):
                return LLMResponse(content="Hello!", input_tokens=5, output_tokens=2)

        def _fake_create_adapter(*args, **kwargs):
            return _FakeAdapter()

        monkeypatch.setattr(config_router, "create_adapter", _fake_create_adapter)

        _, cookies = await _make_admin_and_cookie(db_session)
        await _seed_default_app_settings(db_session)
        res = await client.post(
            "/api/admin/config/test-connection",
            json={},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "ok"
        assert body["response_text"] == "Hello!"
        assert body["error"] is None
        assert isinstance(body["latency_ms"], int)
        assert body["latency_ms"] >= 0

    async def test_returns_error_when_adapter_raises(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from flexloop.admin.routers import config as config_router

        class _FailingAdapter:
            def __init__(self, *a, **kw):
                pass

            async def generate(self, *a, **kw):
                raise RuntimeError("boom")

        def _fake_create_adapter(*a, **kw):
            return _FailingAdapter()

        monkeypatch.setattr(config_router, "create_adapter", _fake_create_adapter)

        _, cookies = await _make_admin_and_cookie(db_session)
        await _seed_default_app_settings(db_session)
        res = await client.post(
            "/api/admin/config/test-connection",
            json={},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "error"
        assert body["response_text"] is None
        assert "boom" in body["error"]

    async def test_override_fields_are_used(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that the override payload is passed to create_adapter, not
        the saved config."""
        from flexloop.ai.base import LLMResponse
        from flexloop.admin.routers import config as config_router

        captured: dict = {}

        class _FakeAdapter:
            def __init__(self, *a, **kw):
                pass

            async def generate(self, *a, **kw):
                return LLMResponse(content="ok", input_tokens=1, output_tokens=1)

        def _fake_create_adapter(provider, model, api_key, base_url, **kwargs):
            captured["provider"] = provider
            captured["model"] = model
            captured["api_key"] = api_key
            captured["base_url"] = base_url
            return _FakeAdapter()

        monkeypatch.setattr(config_router, "create_adapter", _fake_create_adapter)

        _, cookies = await _make_admin_and_cookie(db_session)
        await _seed_default_app_settings(db_session)
        res = await client.post(
            "/api/admin/config/test-connection",
            json={
                "provider": "anthropic",
                "model": "claude-test",
                "api_key": "sk-override-abc",
                "base_url": "https://override.example.com",
            },
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 200
        assert captured["provider"] == "anthropic"
        assert captured["model"] == "claude-test"
        assert captured["api_key"] == "sk-override-abc"
        assert captured["base_url"] == "https://override.example.com"

    async def test_does_not_write_audit_log(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from flexloop.ai.base import LLMResponse
        from flexloop.admin.routers import config as config_router

        class _FakeAdapter:
            def __init__(self, *a, **kw):
                pass

            async def generate(self, *a, **kw):
                return LLMResponse(content="ok", input_tokens=1, output_tokens=1)

        monkeypatch.setattr(
            config_router, "create_adapter", lambda *a, **kw: _FakeAdapter()
        )
        _, cookies = await _make_admin_and_cookie(db_session)
        await _seed_default_app_settings(db_session)
        await client.post(
            "/api/admin/config/test-connection",
            json={},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        entries = (
            await db_session.execute(select(AdminAuditLog))
        ).all()
        assert len(entries) == 0

    async def test_unknown_provider_returns_error(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """`create_adapter` raises ValueError for unknown providers — the
        handler must catch it and return {status: 'error', ...}, not a 500.
        """
        _, cookies = await _make_admin_and_cookie(db_session)
        await _seed_default_app_settings(db_session)
        res = await client.post(
            "/api/admin/config/test-connection",
            json={"provider": "this_provider_does_not_exist_xyz"},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "error"
        assert body["response_text"] is None
        assert "this_provider_does_not_exist_xyz" in body["error"]
        assert isinstance(body["latency_ms"], int)
        assert body["latency_ms"] >= 0

    async def test_test_connection_codex_happy(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        auth_file = make_auth_json(tmp_path / "auth.json")
        _CodexAsyncOpenAI.reset()
        monkeypatch.setattr(
            "flexloop.ai.openai_codex_adapter.AsyncOpenAI", _CodexAsyncOpenAI
        )

        _, cookies = await _make_admin_and_cookie(db_session)
        row = await _seed_default_app_settings(db_session)
        row.ai_provider = "openai-codex"
        row.ai_model = "gpt-5.1-codex-max"
        row.codex_auth_file = str(auth_file)
        row.ai_reasoning_effort = "high"
        await db_session.commit()

        res = await client.post(
            "/api/admin/config/test-connection",
            json={},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )

        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "ok"
        assert body["response_text"] == "codex ok"
        assert _CodexAsyncOpenAI.chat_requests[-1]["api_key"] == "test-access-token-abc123"
        assert _CodexAsyncOpenAI.chat_requests[-1]["kwargs"]["reasoning_effort"] == "high"

    async def test_test_connection_codex_missing_file(
        self, client: AsyncClient, db_session: AsyncSession, tmp_path
    ) -> None:
        valid_auth_file = make_auth_json(tmp_path / "saved-auth.json")
        missing_auth_file = tmp_path / "missing-auth.json"

        _, cookies = await _make_admin_and_cookie(db_session)
        row = await _seed_default_app_settings(db_session)
        row.ai_provider = "openai-codex"
        row.ai_model = "gpt-5.1-codex-max"
        row.codex_auth_file = str(valid_auth_file)
        row.ai_reasoning_effort = "medium"
        await db_session.commit()

        res = await client.post(
            "/api/admin/config/test-connection",
            json={
                "provider": "openai-codex",
                "model": "gpt-5.1-codex-max",
                "codex_auth_file": str(missing_auth_file),
                "reasoning_effort": "minimal",
            },
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )

        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "error"
        assert body["response_text"] is None
        assert "not found" in body["error"]

    async def test_test_connection_codex_expired_token(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        auth_file = make_auth_json(tmp_path / "auth.json")
        request = httpx.Request("POST", "https://api.openai.test/chat")
        response = httpx.Response(401, request=request)
        _CodexAsyncOpenAI.reset()
        _CodexAsyncOpenAI.chat_error = openai.AuthenticationError(
            "expired token", response=response, body=None
        )
        monkeypatch.setattr(
            "flexloop.ai.openai_codex_adapter.AsyncOpenAI", _CodexAsyncOpenAI
        )

        _, cookies = await _make_admin_and_cookie(db_session)
        row = await _seed_default_app_settings(db_session)
        row.ai_provider = "openai-codex"
        row.ai_model = "gpt-5.1-codex-max"
        row.codex_auth_file = str(auth_file)
        row.ai_reasoning_effort = "low"
        await db_session.commit()

        res = await client.post(
            "/api/admin/config/test-connection",
            json={"reasoning_effort": "minimal"},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )

        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "error"
        assert body["response_text"] is None
        assert "expired token" in body["error"]
        assert (
            _CodexAsyncOpenAI.chat_requests[-1]["kwargs"]["reasoning_effort"]
            == "minimal"
        )
