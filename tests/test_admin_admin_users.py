"""Integration tests for /api/admin/admin-users."""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import SESSION_COOKIE_NAME, create_session, hash_password, verify_password
from flexloop.models.admin_user import AdminUser


async def _make_admin_and_cookie(db: AsyncSession, username: str = "t") -> tuple[AdminUser, dict[str, str]]:
    a = AdminUser(username=username, password_hash=hash_password("password123"))
    db.add(a); await db.commit(); await db.refresh(a)
    token, _ = await create_session(db, admin_user_id=a.id)
    return a, {SESSION_COOKIE_NAME: token}


class TestListAdminUsers:
    async def test_auth(self, client: AsyncClient) -> None:
        assert (await client.get("/api/admin/admin-users")).status_code == 401

    async def test_response_has_no_password_hash(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, cookies = await _make_admin_and_cookie(db_session)
        res = await client.get("/api/admin/admin-users", cookies=cookies)
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 1
        assert "password_hash" not in body["items"][0]
        assert "password" not in body["items"][0]


class TestCreateAdminUser:
    async def test_hashes_password(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, cookies = await _make_admin_and_cookie(db_session)
        res = await client.post(
            "/api/admin/admin-users",
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
            json={"username": "newadmin", "password": "freshpass1"},
        )
        assert res.status_code == 201
        body = res.json()
        assert body["username"] == "newadmin"
        assert "password" not in body
        assert "password_hash" not in body

        # Verify DB hash matches
        result = await db_session.execute(
            select(AdminUser).where(AdminUser.username == "newadmin")
        )
        row = result.scalar_one()
        assert verify_password("freshpass1", row.password_hash)

    async def test_rejects_short_password(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, cookies = await _make_admin_and_cookie(db_session)
        res = await client.post(
            "/api/admin/admin-users",
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
            json={"username": "x", "password": "short"},
        )
        assert res.status_code == 422


class TestUpdateAdminUser:
    async def test_password_update_rehashes(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        admin, cookies = await _make_admin_and_cookie(db_session)
        other = AdminUser(username="other", password_hash=hash_password("oldpassword"))
        db_session.add(other); await db_session.commit(); await db_session.refresh(other)

        res = await client.put(
            f"/api/admin/admin-users/{other.id}",
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
            json={"password": "newpassword1"},
        )
        assert res.status_code == 200

        await db_session.refresh(other)
        assert verify_password("newpassword1", other.password_hash)

    async def test_deactivate(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        admin, cookies = await _make_admin_and_cookie(db_session)
        other = AdminUser(username="other", password_hash=hash_password("oldpassword"))
        db_session.add(other); await db_session.commit(); await db_session.refresh(other)

        res = await client.put(
            f"/api/admin/admin-users/{other.id}",
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
            json={"is_active": False},
        )
        assert res.status_code == 200
        assert res.json()["is_active"] is False


class TestDeleteAdminUser:
    async def test_cannot_delete_self(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        admin, cookies = await _make_admin_and_cookie(db_session)
        res = await client.delete(
            f"/api/admin/admin-users/{admin.id}",
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
        )
        assert res.status_code == 400

    async def test_delete_other(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        admin, cookies = await _make_admin_and_cookie(db_session)
        other = AdminUser(username="other", password_hash=hash_password("oldpassword"))
        db_session.add(other); await db_session.commit(); await db_session.refresh(other)

        res = await client.delete(
            f"/api/admin/admin-users/{other.id}",
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
        )
        assert res.status_code == 204
