import pytest
from datetime import date
from sqlalchemy import select

from flexloop.models.user import User
from flexloop.models.exercise import Exercise
from flexloop.models.plan import Plan, PlanDay, ExerciseGroup, PlanExercise


@pytest.fixture
async def user_and_exercise(db_session):
    user = User(
        name="Test User", gender="male", age=28, height=180.0,
        weight=82.0, weight_unit="kg", height_unit="cm",
        experience_level="intermediate", goals="hypertrophy",
        available_equipment=["barbell"],
    )
    exercise = Exercise(
        name="Bench Press", muscle_group="chest", equipment="barbell",
        category="compound", difficulty="intermediate",
    )
    db_session.add_all([user, exercise])
    await db_session.commit()
    return user, exercise


@pytest.mark.asyncio
async def test_create_plan_with_superset(db_session, user_and_exercise):
    user, exercise = user_and_exercise

    plan = Plan(
        user_id=user.id, name="PPL Block 1", split_type="ppl",
        block_start=date(2026, 3, 23), block_end=date(2026, 5, 3),
        status="active", ai_generated=True,
    )
    db_session.add(plan)
    await db_session.commit()

    day = PlanDay(plan_id=plan.id, day_number=1, label="Push A", focus="chest,shoulders,triceps")
    db_session.add(day)
    await db_session.commit()

    group = ExerciseGroup(
        plan_day_id=day.id, group_type="straight", order=1, rest_after_group_sec=90,
    )
    db_session.add(group)
    await db_session.commit()

    plan_exercise = PlanExercise(
        plan_day_id=day.id, exercise_group_id=group.id, exercise_id=exercise.id,
        order=1, sets=4, reps=8, weight=80.0, rpe_target=8.0,
    )
    db_session.add(plan_exercise)
    await db_session.commit()

    result = await db_session.execute(select(Plan).where(Plan.id == plan.id))
    saved_plan = result.scalar_one()
    assert saved_plan.name == "PPL Block 1"
    assert saved_plan.ai_generated is True

    result = await db_session.execute(
        select(PlanExercise).where(PlanExercise.plan_day_id == day.id)
    )
    saved_pe = result.scalar_one()
    assert saved_pe.sets == 4
    assert saved_pe.weight == 80.0
