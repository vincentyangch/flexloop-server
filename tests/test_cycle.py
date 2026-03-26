import pytest

from flexloop.models.cycle_tracker import CycleTracker
from flexloop.models.exercise import Exercise
from flexloop.models.plan import ExerciseGroup, Plan, PlanDay, PlanExercise
from flexloop.models.user import User


@pytest.fixture
async def user(db_session):
    user = User(
        name="Test User", gender="male", age=28, height_cm=180.0,
        weight_kg=82.0, experience_level="intermediate", goals="strength",
        available_equipment=["barbell"],
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.fixture
async def exercise(db_session):
    ex = Exercise(
        name="Squat", muscle_group="legs", equipment="barbell",
        category="compound", difficulty="intermediate",
    )
    db_session.add(ex)
    await db_session.commit()
    return ex


@pytest.fixture
async def plan_with_tracker(db_session, user, exercise):
    """Create a 3-day cycle plan with a tracker at day 1."""
    plan = Plan(
        user_id=user.id, name="PPL Cycle", split_type="ppl",
        cycle_length=3, status="active", ai_generated=False,
    )
    db_session.add(plan)
    await db_session.flush()

    for day_num, label in [(1, "Push"), (2, "Pull"), (3, "Legs")]:
        day = PlanDay(plan_id=plan.id, day_number=day_num, label=label, focus=label.lower())
        db_session.add(day)
        await db_session.flush()

        group = ExerciseGroup(plan_day_id=day.id, group_type="straight", order=1)
        db_session.add(group)
        await db_session.flush()

        pe = PlanExercise(
            plan_day_id=day.id, exercise_group_id=group.id,
            exercise_id=exercise.id, order=1, sets=3, reps=5,
        )
        db_session.add(pe)

    tracker = CycleTracker(user_id=user.id, plan_id=plan.id, next_day_number=1)
    db_session.add(tracker)
    await db_session.commit()
    return plan


@pytest.mark.asyncio
async def test_get_next_workout(client, user, plan_with_tracker):
    resp = await client.get(f"/api/users/{user.id}/next-workout")
    assert resp.status_code == 200
    data = resp.json()
    assert data["next_day_number"] == 1
    assert data["day"]["label"] == "Push"
    assert data["cycle_length"] == 3
    assert len(data["day"]["exercise_groups"]) == 1


@pytest.mark.asyncio
async def test_get_next_workout_no_tracker(client, user):
    resp = await client.get(f"/api/users/{user.id}/next-workout")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_complete_workout_advances_day(client, user, plan_with_tracker):
    # Day 1 -> Day 2
    resp = await client.post(f"/api/users/{user.id}/complete-workout")
    assert resp.status_code == 200
    data = resp.json()
    assert data["completed_day_number"] == 1
    assert data["next_day_number"] == 2

    # Verify next-workout now returns day 2
    resp = await client.get(f"/api/users/{user.id}/next-workout")
    assert resp.json()["day"]["label"] == "Pull"


@pytest.mark.asyncio
async def test_complete_workout_wraps_around(client, user, plan_with_tracker):
    # Complete days 1, 2, 3 -> should wrap to 1
    await client.post(f"/api/users/{user.id}/complete-workout")  # 1->2
    await client.post(f"/api/users/{user.id}/complete-workout")  # 2->3
    resp = await client.post(f"/api/users/{user.id}/complete-workout")  # 3->1
    assert resp.json()["next_day_number"] == 1

    # Verify we're back to Push
    resp = await client.get(f"/api/users/{user.id}/next-workout")
    assert resp.json()["day"]["label"] == "Push"
