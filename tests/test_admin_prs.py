"""Integration tests for /api/admin/prs."""
from __future__ import annotations

from datetime import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import SESSION_COOKIE_NAME, create_session, hash_password
from flexloop.models.admin_user import AdminUser
from flexloop.models.exercise import Exercise
from flexloop.models.personal_record import PersonalRecord
from flexloop.models.user import User


async def _make_admin_and_cookie(db: AsyncSession) -> dict[str, str]:
    admin = AdminUser(username="t", password_hash=hash_password("password123"))
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    token, _ = await create_session(db, admin_user_id=admin.id)
    return {SESSION_COOKIE_NAME: token}


async def _make_user_and_exercise(db: AsyncSession) -> tuple[User, Exercise]:
    u = User(
        name="PR Owner",
        gender="m",
        age=28,
        height=175,
        weight=80,
        weight_unit="kg",
        height_unit="cm",
        experience_level="intermediate",
        goals="",
        available_equipment=[],
    )
    e = Exercise(
        name="Bench Press",
        muscle_group="chest",
        equipment="barbell",
        category="compound",
        difficulty="intermediate",
    )
    db.add_all([u, e])
    await db.commit()
    await db.refresh(u)
    await db.refresh(e)
    return u, e


class TestPRs:
    async def test_list_requires_auth(self, client: AsyncClient) -> None:
        assert (await client.get("/api/admin/prs")).status_code == 401

    async def test_create_and_list(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        user, ex = await _make_user_and_exercise(db_session)

        res = await client.post(
            "/api/admin/prs",
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
            json={
                "user_id": user.id,
                "exercise_id": ex.id,
                "pr_type": "max_weight",
                "value": 120.0,
                "achieved_at": "2026-04-01T12:00:00",
            },
        )
        assert res.status_code == 201

        res = await client.get(
            f"/api/admin/prs?filter[user_id]={user.id}",
            cookies=cookies,
        )
        assert res.json()["total"] == 1
        assert res.json()["items"][0]["pr_type"] == "max_weight"

    async def test_filter_by_exercise(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        user, ex = await _make_user_and_exercise(db_session)
        db_session.add(
            PersonalRecord(
                user_id=user.id,
                exercise_id=ex.id,
                pr_type="max_weight",
                value=100,
                achieved_at=datetime.utcnow(),
            )
        )
        await db_session.commit()

        res = await client.get(
            f"/api/admin/prs?filter[exercise_id]={ex.id}",
            cookies=cookies,
        )
        assert res.json()["total"] == 1
