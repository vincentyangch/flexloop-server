"""Integration tests for the admin Plan day endpoints.

These endpoints let an operator hand-edit a plan's day/group/exercise/set
structure without round-tripping through the full plan JSON. A day is the
atomic save unit per spec §9.3 — PUT replaces an entire day's contents.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from flexloop.admin.auth import SESSION_COOKIE_NAME, create_session, hash_password
from flexloop.models.admin_user import AdminUser
from flexloop.models.exercise import Exercise
from flexloop.models.plan import ExerciseGroup, Plan, PlanDay, PlanExercise
from flexloop.models.user import User


async def _make_admin_and_cookie(db: AsyncSession) -> dict[str, str]:
    admin = AdminUser(username="tester", password_hash=hash_password("password123"))
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    token, _ = await create_session(db, admin_user_id=admin.id)
    return {SESSION_COOKIE_NAME: token}


async def _setup_plan_with_exercises(db: AsyncSession) -> tuple[Plan, list[Exercise]]:
    """Create a user, an empty plan, and two exercises for the tests to use."""
    user = User(
        name="Plan Owner", gender="other", age=30, height=180, weight=80,
        weight_unit="kg", height_unit="cm", experience_level="intermediate",
        goals="", available_equipment=[],
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    plan = Plan(
        user_id=user.id, name="Test Plan", split_type="upper_lower",
        cycle_length=4, status="active", ai_generated=False,
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)

    e1 = Exercise(
        name="Bench Press", muscle_group="chest", equipment="barbell",
        category="strength", difficulty="intermediate",
    )
    e2 = Exercise(
        name="Overhead Press", muscle_group="shoulders", equipment="barbell",
        category="strength", difficulty="intermediate",
    )
    db.add_all([e1, e2])
    await db.commit()
    await db.refresh(e1)
    await db.refresh(e2)

    return plan, [e1, e2]


async def _reload_day(db: AsyncSession, plan_id: int, day_number: int) -> PlanDay | None:
    result = await db.execute(
        select(PlanDay)
        .options(
            selectinload(PlanDay.exercise_groups).selectinload(ExerciseGroup.exercises)
        )
        .where(PlanDay.plan_id == plan_id, PlanDay.day_number == day_number)
    )
    return result.scalar_one_or_none()


class TestAddDay:
    async def test_requires_auth(self, client: AsyncClient) -> None:
        res = await client.post(
            "/api/admin/plans/1/days",
            json={"day_number": 1, "label": "x", "focus": ""},
            headers={"Origin": "http://localhost:5173"},
        )
        assert res.status_code == 401

    async def test_404_when_plan_missing(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.post(
            "/api/admin/plans/9999/days",
            json={"day_number": 1, "label": "Day 1", "focus": "full body"},
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
        )
        assert res.status_code == 404

    async def test_adds_empty_day(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        plan, _ = await _setup_plan_with_exercises(db_session)

        res = await client.post(
            f"/api/admin/plans/{plan.id}/days",
            json={"day_number": 1, "label": "Upper A", "focus": "chest, back"},
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
        )
        assert res.status_code == 201
        body = res.json()
        assert body["day_number"] == 1
        assert body["label"] == "Upper A"
        assert body["focus"] == "chest, back"
        assert body["exercise_groups"] == []

    async def test_adds_day_with_full_nested_payload(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        plan, [e1, e2] = await _setup_plan_with_exercises(db_session)

        payload = {
            "day_number": 1,
            "label": "Upper A",
            "focus": "chest, shoulders",
            "exercise_groups": [
                {
                    "group_type": "straight",
                    "order": 1,
                    "rest_after_group_sec": 120,
                    "exercises": [
                        {
                            "exercise_id": e1.id,
                            "order": 1,
                            "sets": 4,
                            "reps": 8,
                            "weight": 100.0,
                            "rpe_target": 7.5,
                            "sets_json": [
                                {"set_number": 1, "target_weight": 100, "target_reps": 8, "target_rpe": 7},
                                {"set_number": 2, "target_weight": 100, "target_reps": 8, "target_rpe": 7.5},
                            ],
                        },
                        {
                            "exercise_id": e2.id,
                            "order": 2,
                            "sets": 3,
                            "reps": 6,
                        },
                    ],
                }
            ],
        }
        res = await client.post(
            f"/api/admin/plans/{plan.id}/days",
            json=payload,
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
        )
        assert res.status_code == 201
        body = res.json()
        assert len(body["exercise_groups"]) == 1
        group = body["exercise_groups"][0]
        assert group["group_type"] == "straight"
        assert len(group["exercises"]) == 2
        assert group["exercises"][0]["exercise_id"] == e1.id
        assert group["exercises"][0]["sets"] == 4
        assert group["exercises"][0]["sets_json"][0]["target_weight"] == 100
        assert group["exercises"][1]["exercise_id"] == e2.id

        # Verify DB state reflects the nested shape.
        day = await _reload_day(db_session, plan.id, 1)
        assert day is not None
        assert len(day.exercise_groups) == 1
        assert len(day.exercise_groups[0].exercises) == 2

    async def test_rejects_duplicate_day_number(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        plan, _ = await _setup_plan_with_exercises(db_session)

        # First add
        res1 = await client.post(
            f"/api/admin/plans/{plan.id}/days",
            json={"day_number": 1, "label": "A", "focus": ""},
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
        )
        assert res1.status_code == 201

        # Second add with same day_number
        res2 = await client.post(
            f"/api/admin/plans/{plan.id}/days",
            json={"day_number": 1, "label": "B", "focus": ""},
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
        )
        assert res2.status_code == 409
        assert "day_number" in res2.json()["detail"].lower()

    async def test_rejects_unknown_field_on_day(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        plan, _ = await _setup_plan_with_exercises(db_session)
        res = await client.post(
            f"/api/admin/plans/{plan.id}/days",
            json={"day_number": 1, "label": "x", "focus": "", "totally_wrong": True},
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
        )
        assert res.status_code == 422


class TestReplaceDay:
    async def test_requires_auth(self, client: AsyncClient) -> None:
        res = await client.put(
            "/api/admin/plans/1/days/1",
            json={"label": "x", "exercise_groups": []},
            headers={"Origin": "http://localhost:5173"},
        )
        assert res.status_code == 401

    async def test_404_when_plan_missing(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.put(
            "/api/admin/plans/9999/days/1",
            json={"label": "x", "exercise_groups": []},
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
        )
        assert res.status_code == 404

    async def test_404_when_day_missing(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        plan, _ = await _setup_plan_with_exercises(db_session)
        res = await client.put(
            f"/api/admin/plans/{plan.id}/days/7",
            json={"label": "x", "exercise_groups": []},
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
        )
        assert res.status_code == 404

    async def test_replaces_entire_day_contents(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """The PUT endpoint clears the day's existing groups/exercises and
        replaces them from the payload atomically.
        """
        cookies = await _make_admin_and_cookie(db_session)
        plan, [e1, e2] = await _setup_plan_with_exercises(db_session)

        # Seed: create a day with 1 group, 1 exercise via POST.
        await client.post(
            f"/api/admin/plans/{plan.id}/days",
            json={
                "day_number": 1,
                "label": "Old label",
                "focus": "old focus",
                "exercise_groups": [
                    {
                        "group_type": "straight",
                        "order": 1,
                        "rest_after_group_sec": 90,
                        "exercises": [
                            {"exercise_id": e1.id, "order": 1, "sets": 3, "reps": 10}
                        ],
                    }
                ],
            },
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
        )

        # Replace with a completely different structure.
        res = await client.put(
            f"/api/admin/plans/{plan.id}/days/1",
            json={
                "label": "New label",
                "focus": "new focus",
                "exercise_groups": [
                    {
                        "group_type": "superset",
                        "order": 1,
                        "rest_after_group_sec": 60,
                        "exercises": [
                            {"exercise_id": e2.id, "order": 1, "sets": 5, "reps": 5}
                        ],
                    },
                    {
                        "group_type": "straight",
                        "order": 2,
                        "rest_after_group_sec": 120,
                        "exercises": [],
                    },
                ],
            },
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["label"] == "New label"
        assert body["focus"] == "new focus"
        assert len(body["exercise_groups"]) == 2
        assert body["exercise_groups"][0]["group_type"] == "superset"
        assert body["exercise_groups"][0]["exercises"][0]["exercise_id"] == e2.id
        assert body["exercise_groups"][0]["exercises"][0]["sets"] == 5
        assert body["exercise_groups"][1]["exercises"] == []

        # Verify the old exercise row was deleted — not orphaned.
        from sqlalchemy import select as _select
        orphans = await db_session.execute(
            _select(PlanExercise).where(PlanExercise.exercise_id == e1.id)
        )
        assert orphans.scalar_one_or_none() is None

    async def test_replaces_with_empty_groups(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Submitting an empty exercise_groups list clears the day — this
        is how an admin "empties" a day without deleting it.
        """
        cookies = await _make_admin_and_cookie(db_session)
        plan, [e1, _] = await _setup_plan_with_exercises(db_session)
        await client.post(
            f"/api/admin/plans/{plan.id}/days",
            json={
                "day_number": 1,
                "label": "Day 1",
                "focus": "chest",
                "exercise_groups": [
                    {
                        "group_type": "straight",
                        "order": 1,
                        "rest_after_group_sec": 90,
                        "exercises": [
                            {"exercise_id": e1.id, "order": 1, "sets": 3, "reps": 10}
                        ],
                    }
                ],
            },
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
        )

        res = await client.put(
            f"/api/admin/plans/{plan.id}/days/1",
            json={"label": "Day 1", "exercise_groups": []},
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
        )
        assert res.status_code == 200
        assert res.json()["exercise_groups"] == []


class TestDeleteDay:
    async def test_requires_auth(self, client: AsyncClient) -> None:
        assert (
            await client.delete(
                "/api/admin/plans/1/days/1",
                headers={"Origin": "http://localhost:5173"},
            )
        ).status_code == 401

    async def test_404_when_plan_missing(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.delete(
            "/api/admin/plans/9999/days/1",
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
        )
        assert res.status_code == 404

    async def test_404_when_day_missing(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        plan, _ = await _setup_plan_with_exercises(db_session)
        res = await client.delete(
            f"/api/admin/plans/{plan.id}/days/7",
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
        )
        assert res.status_code == 404

    async def test_delete_cascades_to_groups_and_exercises(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        plan, [e1, _] = await _setup_plan_with_exercises(db_session)
        res = await client.post(
            f"/api/admin/plans/{plan.id}/days",
            json={
                "day_number": 1,
                "label": "Day 1",
                "focus": "chest",
                "exercise_groups": [
                    {
                        "group_type": "straight",
                        "order": 1,
                        "rest_after_group_sec": 90,
                        "exercises": [
                            {"exercise_id": e1.id, "order": 1, "sets": 3, "reps": 10}
                        ],
                    }
                ],
            },
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
        )
        assert res.status_code == 201
        day_body = res.json()
        day_id = day_body["id"]
        group_id = day_body["exercise_groups"][0]["id"]
        plan_ex_id = day_body["exercise_groups"][0]["exercises"][0]["id"]

        res = await client.delete(
            f"/api/admin/plans/{plan.id}/days/1",
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
        )
        assert res.status_code == 204

        from sqlalchemy import select as _select
        assert (
            await db_session.execute(_select(PlanDay).where(PlanDay.id == day_id))
        ).scalar_one_or_none() is None
        assert (
            await db_session.execute(
                _select(ExerciseGroup).where(ExerciseGroup.id == group_id)
            )
        ).scalar_one_or_none() is None
        assert (
            await db_session.execute(
                _select(PlanExercise).where(PlanExercise.id == plan_ex_id)
            )
        ).scalar_one_or_none() is None

        # Plan itself still exists.
        assert (
            await db_session.execute(_select(Plan).where(Plan.id == plan.id))
        ).scalar_one_or_none() is not None
