"""Integration tests for /api/admin/plans (standard CRUD endpoints).

Day-level endpoints (POST/PUT/DELETE /days[/{day_number}]) are covered in
test_admin_plans_days.py to keep this file focused on the CRUD surface.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import SESSION_COOKIE_NAME, create_session, hash_password
from flexloop.models.admin_user import AdminUser
from flexloop.models.plan import ExerciseGroup, Plan, PlanDay, PlanExercise
from flexloop.models.user import User


async def _make_admin_and_cookie(db: AsyncSession) -> dict[str, str]:
    admin = AdminUser(username="tester", password_hash=hash_password("password123"))
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    token, _ = await create_session(db, admin_user_id=admin.id)
    return {SESSION_COOKIE_NAME: token}


async def _make_user(db: AsyncSession) -> User:
    user = User(
        name="Plan Owner", gender="other", age=30, height=180, weight=80,
        weight_unit="kg", height_unit="cm", experience_level="intermediate",
        goals="", available_equipment=[],
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _make_plan(
    db: AsyncSession,
    *,
    user_id: int,
    name: str = "Test Plan",
    status: str = "active",
) -> Plan:
    plan = Plan(
        user_id=user_id,
        name=name,
        split_type="upper_lower",
        cycle_length=4,
        status=status,
        ai_generated=False,
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return plan


class TestListPlans:
    async def test_requires_auth(self, client: AsyncClient) -> None:
        assert (await client.get("/api/admin/plans")).status_code == 401

    async def test_empty_list(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.get("/api/admin/plans", cookies=cookies)
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 0
        assert body["items"] == []
        assert body["page"] == 1

    async def test_lists_plans_with_embedded_days(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        user = await _make_user(db_session)
        plan = await _make_plan(db_session, user_id=user.id, name="Upper / Lower")
        # Add a day with an empty group so the eager-load path is exercised.
        day = PlanDay(plan_id=plan.id, day_number=1, label="Upper A", focus="chest, back")
        db_session.add(day)
        await db_session.commit()

        res = await client.get("/api/admin/plans", cookies=cookies)
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 1
        item = body["items"][0]
        assert item["id"] == plan.id
        assert item["user_id"] == user.id
        assert item["name"] == "Upper / Lower"
        assert len(item["days"]) == 1
        assert item["days"][0]["day_number"] == 1
        assert item["days"][0]["label"] == "Upper A"
        assert item["days"][0]["exercise_groups"] == []

    async def test_filter_by_user_id(
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
        await _make_plan(db_session, user_id=u1.id, name="P1")
        await _make_plan(db_session, user_id=u2.id, name="P2")

        res = await client.get(
            f"/api/admin/plans?filter[user_id]={u1.id}", cookies=cookies
        )
        assert res.status_code == 200
        assert res.json()["total"] == 1
        assert res.json()["items"][0]["name"] == "P1"

    async def test_filter_by_status(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        user = await _make_user(db_session)
        await _make_plan(db_session, user_id=user.id, name="Active one", status="active")
        await _make_plan(db_session, user_id=user.id, name="Archived one", status="archived")

        res = await client.get(
            "/api/admin/plans?filter[status]=archived", cookies=cookies
        )
        assert res.status_code == 200
        assert res.json()["total"] == 1
        assert res.json()["items"][0]["name"] == "Archived one"

    async def test_rejects_unknown_filter(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.get(
            "/api/admin/plans?filter[nonexistent]=x", cookies=cookies
        )
        assert res.status_code == 400

    async def test_search_on_name(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        user = await _make_user(db_session)
        await _make_plan(db_session, user_id=user.id, name="Hypertrophy Block")
        await _make_plan(db_session, user_id=user.id, name="Strength Block")

        res = await client.get(
            "/api/admin/plans?search=hypertrophy", cookies=cookies
        )
        assert res.status_code == 200
        assert res.json()["total"] == 1
        assert res.json()["items"][0]["name"] == "Hypertrophy Block"


class TestGetPlan:
    async def test_requires_auth(self, client: AsyncClient) -> None:
        assert (await client.get("/api/admin/plans/1")).status_code == 401

    async def test_returns_404_for_missing(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.get("/api/admin/plans/9999", cookies=cookies)
        assert res.status_code == 404

    async def test_returns_plan_with_nested_days(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        user = await _make_user(db_session)
        plan = await _make_plan(db_session, user_id=user.id)
        day = PlanDay(plan_id=plan.id, day_number=1, label="Day 1", focus="full body")
        db_session.add(day)
        await db_session.commit()
        await db_session.refresh(day)

        res = await client.get(f"/api/admin/plans/{plan.id}", cookies=cookies)
        assert res.status_code == 200
        body = res.json()
        assert body["id"] == plan.id
        assert body["name"] == "Test Plan"
        assert len(body["days"]) == 1
        assert body["days"][0]["day_number"] == 1
