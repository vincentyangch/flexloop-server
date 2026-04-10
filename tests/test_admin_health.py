import pytest


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
