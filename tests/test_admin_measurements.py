"""Integration tests for /api/admin/measurements."""
from __future__ import annotations

from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import SESSION_COOKIE_NAME, create_session, hash_password
from flexloop.models.admin_user import AdminUser
from flexloop.models.measurement import Measurement
from flexloop.models.user import User


async def _make_admin_and_cookie(db: AsyncSession) -> dict[str, str]:
    admin = AdminUser(username="t", password_hash=hash_password("password123"))
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    token, _ = await create_session(db, admin_user_id=admin.id)
    return {SESSION_COOKIE_NAME: token}


async def _make_user(db: AsyncSession) -> User:
    u = User(
        name="M Owner",
        gender="f",
        age=30,
        height=165,
        weight=60,
        weight_unit="kg",
        height_unit="cm",
        experience_level="intermediate",
        goals="",
        available_equipment=[],
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


class TestMeasurements:
    async def test_list_requires_auth(self, client: AsyncClient) -> None:
        assert (await client.get("/api/admin/measurements")).status_code == 401

    async def test_create_list_delete(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        user = await _make_user(db_session)

        # Create
        res = await client.post(
            "/api/admin/measurements",
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
            json={
                "user_id": user.id,
                "date": "2026-04-01",
                "type": "weight",
                "value": 60.5,
                "notes": "morning",
            },
        )
        assert res.status_code == 201
        mid = res.json()["id"]

        # List
        res = await client.get(
            f"/api/admin/measurements?filter[user_id]={user.id}",
            cookies=cookies,
        )
        assert res.json()["total"] == 1

        # Delete
        res = await client.delete(
            f"/api/admin/measurements/{mid}",
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
        )
        assert res.status_code == 204

    async def test_filter_by_type(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        user = await _make_user(db_session)
        db_session.add(
            Measurement(user_id=user.id, date=date(2026, 1, 1), type="weight", value=60)
        )
        db_session.add(
            Measurement(user_id=user.id, date=date(2026, 1, 1), type="body_fat", value=18)
        )
        await db_session.commit()

        res = await client.get("/api/admin/measurements?filter[type]=weight", cookies=cookies)
        assert res.json()["total"] == 1
