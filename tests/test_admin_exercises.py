"""Integration tests for /api/admin/exercises."""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import SESSION_COOKIE_NAME, create_session, hash_password
from flexloop.models.admin_user import AdminUser
from flexloop.models.exercise import Exercise


async def _cookie(db: AsyncSession) -> dict[str, str]:
    a = AdminUser(username="t", password_hash=hash_password("password123"))
    db.add(a); await db.commit(); await db.refresh(a)
    token, _ = await create_session(db, admin_user_id=a.id)
    return {SESSION_COOKIE_NAME: token}


class TestExercises:
    async def test_auth(self, client: AsyncClient) -> None:
        assert (await client.get("/api/admin/exercises")).status_code == 401

    async def test_create_and_search_by_name(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        res = await client.post(
            "/api/admin/exercises",
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
            json={
                "name": "Bulgarian Split Squat", "muscle_group": "legs",
                "equipment": "dumbbell", "category": "compound",
                "difficulty": "intermediate",
            },
        )
        assert res.status_code == 201

        res = await client.get(
            "/api/admin/exercises?search=bulgarian", cookies=cookies,
        )
        assert res.json()["total"] == 1

    async def test_filter_by_muscle_group(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        db_session.add(Exercise(
            name="Squat", muscle_group="legs", equipment="barbell",
            category="compound", difficulty="intermediate",
        ))
        db_session.add(Exercise(
            name="Bench", muscle_group="chest", equipment="barbell",
            category="compound", difficulty="intermediate",
        ))
        await db_session.commit()

        res = await client.get(
            "/api/admin/exercises?filter[muscle_group]=legs", cookies=cookies,
        )
        assert res.json()["total"] == 1
        assert res.json()["items"][0]["name"] == "Squat"
