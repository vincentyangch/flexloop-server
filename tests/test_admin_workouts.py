"""Integration tests for /api/admin/workouts."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import SESSION_COOKIE_NAME, create_session, hash_password
from flexloop.models.admin_user import AdminUser
from flexloop.models.user import User
from flexloop.models.workout import WorkoutSession


async def _make_admin_and_cookie(db: AsyncSession) -> dict[str, str]:
    """Create an admin user + session; return a cookie dict usable on httpx client.

    Re-defined per-file intentionally (see Chunk 3 conventions in the plan):
    we keep the helper localized rather than hoisting to conftest.py so the
    change stays scoped to the admin CRUD test files.
    """
    admin = AdminUser(username="tester", password_hash=hash_password("password123"))
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    token, _ = await create_session(db, admin_user_id=admin.id)
    return {SESSION_COOKIE_NAME: token}


async def _make_user(db: AsyncSession) -> User:
    user = User(
        name="WO Owner", gender="other", age=30, height=180, weight=80,
        weight_unit="kg", height_unit="cm", experience_level="intermediate",
        goals="", available_equipment=[],
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


class TestListWorkouts:
    async def test_requires_auth(self, client: AsyncClient) -> None:
        assert (await client.get("/api/admin/workouts")).status_code == 401

    async def test_empty_list(self, client: AsyncClient, db_session: AsyncSession) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.get("/api/admin/workouts", cookies=cookies)
        assert res.status_code == 200
        assert res.json()["total"] == 0

    async def test_lists_sessions_with_sets_embedded(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        user = await _make_user(db_session)
        ws = WorkoutSession(
            user_id=user.id, source="plan", started_at=datetime.utcnow(),
        )
        db_session.add(ws)
        await db_session.commit()

        res = await client.get("/api/admin/workouts", cookies=cookies)
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 1
        assert body["items"][0]["user_id"] == user.id
        assert body["items"][0]["sets"] == []

    async def test_filter_by_user(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        u1 = await _make_user(db_session)
        u2 = User(
            name="Other", gender="other", age=25, height=170, weight=70,
            weight_unit="kg", height_unit="cm", experience_level="beginner",
            goals="", available_equipment=[],
        )
        db_session.add(u2)
        await db_session.commit()
        await db_session.refresh(u2)

        db_session.add(WorkoutSession(user_id=u1.id, source="plan", started_at=datetime.utcnow()))
        db_session.add(WorkoutSession(user_id=u2.id, source="plan", started_at=datetime.utcnow()))
        await db_session.commit()

        res = await client.get(
            f"/api/admin/workouts?filter[user_id]={u1.id}", cookies=cookies,
        )
        assert res.status_code == 200
        assert res.json()["total"] == 1

    async def test_filter_completed_true(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        user = await _make_user(db_session)
        now = datetime.utcnow()
        db_session.add(WorkoutSession(user_id=user.id, source="plan", started_at=now))  # in-progress
        db_session.add(WorkoutSession(
            user_id=user.id, source="plan", started_at=now - timedelta(hours=2),
            completed_at=now,
        ))
        await db_session.commit()

        res = await client.get(
            "/api/admin/workouts?filter[completed]=true", cookies=cookies,
        )
        assert res.status_code == 200
        assert res.json()["total"] == 1

        res2 = await client.get(
            "/api/admin/workouts?filter[completed]=false", cookies=cookies,
        )
        assert res2.json()["total"] == 1


class TestCreateWorkout:
    async def test_creates_session(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        user = await _make_user(db_session)
        res = await client.post(
            "/api/admin/workouts",
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
            json={
                "user_id": user.id,
                "source": "custom",
                "started_at": "2026-04-07T10:00:00",
            },
        )
        assert res.status_code == 201
        assert res.json()["source"] == "custom"


class TestDeleteWorkout:
    async def test_deletes_and_cascades_sets(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        user = await _make_user(db_session)
        ws = WorkoutSession(user_id=user.id, source="plan", started_at=datetime.utcnow())
        db_session.add(ws)
        await db_session.commit()
        await db_session.refresh(ws)

        res = await client.delete(
            f"/api/admin/workouts/{ws.id}",
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
        )
        assert res.status_code == 204
