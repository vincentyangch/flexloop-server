"""Integration tests for /api/admin/config/codex-status."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import SESSION_COOKIE_NAME, create_session, hash_password
from flexloop.config import settings
from flexloop.models.admin_user import AdminUser
from tests.fixtures.auth_json_factory import make_auth_json


@pytest.fixture(autouse=True)
def _restore_codex_auth_file() -> None:
    original = settings.codex_auth_file
    yield
    settings.codex_auth_file = original


async def _make_admin_and_cookie(db: AsyncSession) -> dict[str, str]:
    admin = AdminUser(username="tester", password_hash=hash_password("password123"))
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    token, _ = await create_session(db, admin_user_id=admin.id)
    return {SESSION_COOKIE_NAME: token}


class TestCodexStatus:
    async def test_get_codex_status_requires_admin(self, client: AsyncClient) -> None:
        assert (await client.get("/api/admin/config/codex-status")).status_code == 401

    async def test_get_codex_status_healthy(
        self, client: AsyncClient, db_session: AsyncSession, tmp_path
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        auth_file = make_auth_json(tmp_path / "auth.json")
        settings.codex_auth_file = str(auth_file)

        res = await client.get("/api/admin/config/codex-status", cookies=cookies)

        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "healthy"
        assert body["file_exists"] is True
        assert body["file_path"] == str(auth_file.resolve())
        assert body["auth_mode"] == "chatgpt"
        assert body["account_email"] == "operator@example.com"
        assert body["error"] is None
        assert body["error_code"] is None
        assert body["days_since_refresh"] is not None
        assert body["days_since_refresh"] < 1

    async def test_get_codex_status_aging(
        self, client: AsyncClient, db_session: AsyncSession, tmp_path
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        auth_file = make_auth_json(
            tmp_path / "auth.json",
            last_refresh=datetime.now(timezone.utc) - timedelta(days=6),
        )
        settings.codex_auth_file = str(auth_file)

        res = await client.get("/api/admin/config/codex-status", cookies=cookies)

        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "degraded_yellow"
        assert body["file_exists"] is True
        assert body["days_since_refresh"] is not None
        assert 5 < body["days_since_refresh"] < 7

    async def test_get_codex_status_stale(
        self, client: AsyncClient, db_session: AsyncSession, tmp_path
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        auth_file = make_auth_json(
            tmp_path / "auth.json",
            last_refresh=datetime.now(timezone.utc) - timedelta(days=10),
        )
        settings.codex_auth_file = str(auth_file)

        res = await client.get("/api/admin/config/codex-status", cookies=cookies)

        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "degraded_red"
        assert body["error_code"] == "stale"

    async def test_get_codex_status_missing_file(
        self, client: AsyncClient, db_session: AsyncSession, tmp_path
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        settings.codex_auth_file = str(tmp_path / "missing.json")

        res = await client.get("/api/admin/config/codex-status", cookies=cookies)

        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "unconfigured"
        assert body["file_exists"] is False
        assert body["error_code"] == "missing"

    async def test_get_codex_status_malformed(
        self, client: AsyncClient, db_session: AsyncSession, tmp_path
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        auth_file = make_auth_json(tmp_path / "auth.json", raw_override="{broken")
        settings.codex_auth_file = str(auth_file)

        res = await client.get("/api/admin/config/codex-status", cookies=cookies)

        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "down"
        assert body["file_exists"] is True
        assert body["error_code"] == "malformed"

    async def test_get_codex_status_uncached(
        self, client: AsyncClient, db_session: AsyncSession, tmp_path
    ) -> None:
        from flexloop.admin.routers.config import get_codex_status

        admin = AdminUser(username="statusadmin", password_hash=hash_password("password123"))
        db_session.add(admin)
        await db_session.commit()
        await db_session.refresh(admin)
        auth_file = make_auth_json(tmp_path / "auth.json")
        settings.codex_auth_file = str(auth_file)

        first = await get_codex_status(_admin=admin)
        make_auth_json(auth_file, raw_override="{broken")
        second = await get_codex_status(_admin=admin)

        assert first.status == "healthy"
        assert second.status == "down"
        assert second.error_code == "malformed"
