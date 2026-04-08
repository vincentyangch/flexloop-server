"""Integration tests for /api/admin/users."""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import SESSION_COOKIE_NAME, create_session, hash_password
from flexloop.models.admin_user import AdminUser
from flexloop.models.user import User


async def _make_admin_and_cookie(db: AsyncSession) -> dict[str, str]:
    """Create an admin user + session; return a cookie dict usable on httpx client."""
    admin = AdminUser(username="tester", password_hash=hash_password("password123"))
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    token, _ = await create_session(db, admin_user_id=admin.id)
    return {SESSION_COOKIE_NAME: token}


async def _seed_users(db: AsyncSession, n: int) -> list[User]:
    users = [
        User(
            name=f"User{i}", gender="other", age=20 + i, height=170.0, weight=70.0,
            weight_unit="kg", height_unit="cm", experience_level="intermediate",
            goals="stay fit", available_equipment=["barbell"],
        )
        for i in range(n)
    ]
    db.add_all(users)
    await db.commit()
    for u in users:
        await db.refresh(u)
    return users


class TestListUsers:
    async def test_requires_auth(self, client: AsyncClient) -> None:
        res = await client.get("/api/admin/users")
        assert res.status_code == 401

    async def test_empty_list(self, client: AsyncClient, db_session: AsyncSession) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.get("/api/admin/users", cookies=cookies)
        assert res.status_code == 200
        body = res.json()
        assert body == {"items": [], "total": 0, "page": 1, "per_page": 50, "total_pages": 0}

    async def test_returns_seeded_users(self, client: AsyncClient, db_session: AsyncSession) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        await _seed_users(db_session, 3)
        res = await client.get("/api/admin/users", cookies=cookies)
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 3
        assert len(body["items"]) == 3
        assert body["items"][0]["name"] == "User0"
        assert "available_equipment" in body["items"][0]

    async def test_pagination(self, client: AsyncClient, db_session: AsyncSession) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        await _seed_users(db_session, 5)
        res = await client.get("/api/admin/users?page=2&per_page=2", cookies=cookies)
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 5
        assert body["total_pages"] == 3
        assert len(body["items"]) == 2
        assert body["items"][0]["name"] == "User2"

    async def test_search_by_name(self, client: AsyncClient, db_session: AsyncSession) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        await _seed_users(db_session, 3)
        res = await client.get("/api/admin/users?search=User1", cookies=cookies)
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 1
        assert body["items"][0]["name"] == "User1"

    async def test_sort_name_desc(self, client: AsyncClient, db_session: AsyncSession) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        await _seed_users(db_session, 3)
        res = await client.get("/api/admin/users?sort=name:desc", cookies=cookies)
        assert res.status_code == 200
        names = [u["name"] for u in res.json()["items"]]
        assert names == ["User2", "User1", "User0"]

    async def test_bogus_sort_column_rejected(self, client: AsyncClient, db_session: AsyncSession) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.get("/api/admin/users?sort=password:asc", cookies=cookies)
        assert res.status_code == 400

    async def test_filter_experience_level(self, client: AsyncClient, db_session: AsyncSession) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        db_session.add(User(
            name="Beginner Bob", gender="m", age=25, height=180, weight=80,
            weight_unit="kg", height_unit="cm", experience_level="beginner",
            goals="start lifting", available_equipment=[],
        ))
        db_session.add(User(
            name="Advanced Alice", gender="f", age=30, height=170, weight=60,
            weight_unit="kg", height_unit="cm", experience_level="advanced",
            goals="compete", available_equipment=[],
        ))
        await db_session.commit()
        res = await client.get(
            "/api/admin/users?filter[experience_level]=beginner",
            cookies=cookies,
        )
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 1
        assert body["items"][0]["name"] == "Beginner Bob"

    async def test_bogus_filter_rejected(self, client: AsyncClient, db_session: AsyncSession) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.get("/api/admin/users?filter[secret]=1", cookies=cookies)
        assert res.status_code == 400


class TestGetUserDetail:
    async def test_requires_auth(self, client: AsyncClient) -> None:
        res = await client.get("/api/admin/users/1")
        assert res.status_code == 401

    async def test_returns_user(self, client: AsyncClient, db_session: AsyncSession) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        users = await _seed_users(db_session, 1)
        res = await client.get(f"/api/admin/users/{users[0].id}", cookies=cookies)
        assert res.status_code == 200
        assert res.json()["id"] == users[0].id
        assert res.json()["name"] == "User0"

    async def test_404_on_missing(self, client: AsyncClient, db_session: AsyncSession) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.get("/api/admin/users/99999", cookies=cookies)
        assert res.status_code == 404
