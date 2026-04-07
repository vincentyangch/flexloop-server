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
