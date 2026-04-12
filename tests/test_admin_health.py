from datetime import datetime, timezone

import pytest

from flexloop.admin.routers import health as health_router
from flexloop.ai.codex_auth import CodexAuthSnapshot


def _codex_snapshot(**overrides) -> CodexAuthSnapshot:
    data = {
        "status": "healthy",
        "file_exists": True,
        "file_path": "/tmp/codex-auth.json",
        "auth_mode": "chatgpt",
        "last_refresh": datetime.now(timezone.utc),
        "days_since_refresh": 0.25,
        "account_email": "operator@example.com",
        "error": None,
        "error_code": None,
    }
    data.update(overrides)
    return CodexAuthSnapshot(**data)


@pytest.fixture(autouse=True)
def _reset_health_ai_state():
    snapshot = {
        "ai_provider": health_router._settings.ai_provider,
        "ai_model": health_router._settings.ai_model,
        "ai_api_key": health_router._settings.ai_api_key,
        "ai_base_url": health_router._settings.ai_base_url,
        "codex_auth_file": health_router._settings.codex_auth_file,
    }
    cache = health_router._ai_cache
    cache_at = health_router._ai_cache_at
    health_router._ai_cache = None
    health_router._ai_cache_at = 0
    yield
    for key, value in snapshot.items():
        setattr(health_router._settings, key, value)
    health_router._ai_cache = cache
    health_router._ai_cache_at = cache_at


@pytest.fixture
async def logged_in_client(client):
    """Create an admin and log in. Returns a client with the session cookie set."""
    from flexloop.admin.bootstrap import create_admin_user
    from tests.conftest import test_session_factory

    async with test_session_factory() as db:
        await create_admin_user(db, "healthtester", "testpw12345")
        await db.commit()

    r = await client.post(
        "/api/admin/auth/login",
        json={"username": "healthtester", "password": "testpw12345"},
    )
    assert r.status_code == 200
    return client


async def test_health_requires_auth(client):
    r = await client.get("/api/admin/health")
    assert r.status_code == 401


async def test_health_returns_structured_payload(logged_in_client):
    r = await logged_in_client.get("/api/admin/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("healthy", "degraded", "down")
    assert "checked_at" in body
    assert "components" in body
    assert "database" in body["components"]
    assert body["components"]["database"]["status"] == "healthy"
    assert "ms" in body["components"]["database"]
    assert "table_row_counts" in body["components"]["database"]
    assert "system" in body
    assert "python" in body["system"]
    assert "recent_errors" in body
    assert isinstance(body["recent_errors"], list)


async def test_health_includes_ai_provider(logged_in_client):
    r = await logged_in_client.get("/api/admin/health")
    body = r.json()
    ai = body["components"]["ai_provider"]
    assert ai["status"] in ("healthy", "degraded", "unconfigured")
    assert "provider" in ai
    assert "model" in ai
    assert isinstance(ai["has_key"], bool)
    assert isinstance(ai["reachable"], bool)


async def test_health_includes_disk(logged_in_client):
    r = await logged_in_client.get("/api/admin/health")
    disk = r.json()["components"]["disk"]
    # Should have stats or an error
    if "error" not in disk:
        assert isinstance(disk["total_bytes"], int)
        assert isinstance(disk["free_bytes"], int)
        assert isinstance(disk["used_pct"], (int, float))
        assert 0 <= disk["used_pct"] <= 100


async def test_health_includes_memory(logged_in_client):
    r = await logged_in_client.get("/api/admin/health")
    mem = r.json()["components"]["memory"]
    if "error" not in mem:
        assert isinstance(mem["rss_bytes"], int)
        assert mem["rss_bytes"] > 0


async def test_health_includes_backups(logged_in_client):
    r = await logged_in_client.get("/api/admin/health")
    bk = r.json()["components"]["backups"]
    if "error" not in bk:
        assert isinstance(bk["count"], int)
        assert isinstance(bk["total_bytes"], int)


async def test_health_includes_migrations(logged_in_client):
    r = await logged_in_client.get("/api/admin/health")
    mig = r.json()["components"]["migrations"]
    # In test env alembic.ini may not be available, so accept error or data
    if "error" not in mig:
        assert "current_rev" in mig
        assert "head_rev" in mig
        assert isinstance(mig["in_sync"], bool)


async def test_health_ai_provider_branch_codex_healthy(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict[str, object] = {}

    class FakeReader:
        def __init__(self, path: str) -> None:
            captured["path"] = path

        def snapshot(self) -> CodexAuthSnapshot:
            captured["snapshot_calls"] = captured.get("snapshot_calls", 0) + 1
            return _codex_snapshot(days_since_refresh=0.5)

        def read_access_token(self) -> str:
            raise AssertionError("_check_ai_provider() must use snapshot()")

    monkeypatch.setattr(health_router, "CodexAuthReader", FakeReader)
    health_router._settings.ai_provider = "openai-codex"
    health_router._settings.ai_model = "gpt-5.1-codex-max"
    health_router._settings.codex_auth_file = "/tmp/codex-auth.json"

    result = await health_router._check_ai_provider()

    assert result["status"] == "healthy"
    assert result["provider"] == "openai-codex"
    assert result["model"] == "gpt-5.1-codex-max"
    assert result["file_exists"] is True
    assert result["file_path"] == "/tmp/codex-auth.json"
    assert result["auth_mode"] == "chatgpt"
    assert result["account_email"] == "operator@example.com"
    assert result["days_since_refresh"] == 0.5
    assert result["error"] is None
    assert result["error_code"] is None
    assert result["has_key"] is False
    assert result["reachable"] is False
    assert captured["path"] == "/tmp/codex-auth.json"
    assert captured["snapshot_calls"] == 1


async def test_health_ai_provider_branch_codex_missing(
    monkeypatch: pytest.MonkeyPatch,
):
    class FakeReader:
        def __init__(self, path: str) -> None:
            self.path = path

        def snapshot(self) -> CodexAuthSnapshot:
            return _codex_snapshot(
                status="unconfigured",
                file_exists=False,
                file_path=self.path,
                auth_mode=None,
                last_refresh=None,
                days_since_refresh=None,
                account_email=None,
                error="auth.json not found",
                error_code="missing",
            )

    monkeypatch.setattr(health_router, "CodexAuthReader", FakeReader)
    health_router._settings.ai_provider = "openai-codex"
    health_router._settings.ai_model = "gpt-5.1-codex-max"
    health_router._settings.codex_auth_file = "/tmp/missing-auth.json"

    result = await health_router._check_ai_provider()

    assert result["status"] == "unconfigured"
    assert result["provider"] == "openai-codex"
    assert result["file_exists"] is False
    assert result["file_path"] == "/tmp/missing-auth.json"
    assert result["error"] == "auth.json not found"
    assert result["error_code"] == "missing"


async def test_health_ai_provider_branch_non_codex_unaffected():
    health_router._settings.ai_provider = "openai"
    health_router._settings.ai_model = "gpt-4o-mini"
    health_router._settings.ai_api_key = ""
    health_router._settings.ai_base_url = ""

    result = await health_router._check_ai_provider()

    assert result["status"] == "unconfigured"
    assert result["provider"] == "openai"
    assert result["model"] == "gpt-4o-mini"
    assert result["has_key"] is False
    assert result["reachable"] is False
    assert "file_exists" not in result
    assert "auth_mode" not in result


async def test_health_codex_check_cache_respects_60s_ttl(
    monkeypatch: pytest.MonkeyPatch,
):
    snapshots = iter([
        _codex_snapshot(status="healthy", days_since_refresh=0.2),
        _codex_snapshot(status="down", error="should not be read", error_code="malformed"),
    ])

    class FakeReader:
        def __init__(self, path: str) -> None:
            self.path = path

        def snapshot(self) -> CodexAuthSnapshot:
            return next(snapshots)

    now = {"value": 100.0}
    monkeypatch.setattr(health_router.time, "time", lambda: now["value"])
    monkeypatch.setattr(health_router, "CodexAuthReader", FakeReader)
    health_router._settings.ai_provider = "openai-codex"
    health_router._settings.ai_model = "gpt-5.1-codex-max"
    health_router._settings.codex_auth_file = "/tmp/cached-auth.json"

    first = await health_router._check_ai_provider()
    now["value"] = 130.0
    second = await health_router._check_ai_provider()

    assert first["status"] == "healthy"
    assert "cached" not in first
    assert second["status"] == "healthy"
    assert second["cached"] is True


async def test_health_ai_provider_cache_invalidates_on_provider_switch(
    monkeypatch: pytest.MonkeyPatch,
):
    class FakeReader:
        def __init__(self, path: str) -> None:
            self.path = path

        def snapshot(self) -> CodexAuthSnapshot:
            return _codex_snapshot(
                status="degraded_yellow",
                file_path=self.path,
                days_since_refresh=6.0,
            )

    now = {"value": 100.0}
    monkeypatch.setattr(health_router.time, "time", lambda: now["value"])
    monkeypatch.setattr(health_router, "CodexAuthReader", FakeReader)

    health_router._settings.ai_provider = "openai"
    health_router._settings.ai_model = "gpt-4o-mini"
    health_router._settings.ai_api_key = ""
    health_router._settings.ai_base_url = ""
    first = await health_router._check_ai_provider()

    health_router._settings.ai_provider = "openai-codex"
    health_router._settings.ai_model = "gpt-5.1-codex-max"
    health_router._settings.codex_auth_file = "/tmp/provider-switch-auth.json"
    now["value"] = 101.0
    second = await health_router._check_ai_provider()

    assert first["provider"] == "openai"
    assert second["provider"] == "openai-codex"
    assert second["status"] == "degraded_yellow"
    assert second["file_path"] == "/tmp/provider-switch-auth.json"
    assert "cached" not in second
