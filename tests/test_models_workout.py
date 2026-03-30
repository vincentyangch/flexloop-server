import pytest
from datetime import datetime
from sqlalchemy import select

from flexloop.models.user import User
from flexloop.models.exercise import Exercise
from flexloop.models.workout import WorkoutSession, WorkoutSet, SessionFeedback


@pytest.fixture
async def user_and_exercise(db_session):
    user = User(
        name="Test User", gender="male", age=28, height=180.0,
        weight=82.0, weight_unit="kg", height_unit="cm",
        experience_level="intermediate", goals="hypertrophy",
        available_equipment=["barbell"],
    )
    exercise = Exercise(
        name="Squat", muscle_group="quads", equipment="barbell",
        category="compound", difficulty="intermediate",
    )
    db_session.add_all([user, exercise])
    await db_session.commit()
    return user, exercise


@pytest.mark.asyncio
async def test_create_workout_session_with_sets(db_session, user_and_exercise):
    user, exercise = user_and_exercise

    session = WorkoutSession(
        user_id=user.id, source="ad_hoc",
        started_at=datetime(2026, 3, 23, 10, 0, 0),
    )
    db_session.add(session)
    await db_session.commit()

    workout_set = WorkoutSet(
        session_id=session.id, exercise_id=exercise.id,
        set_number=1, set_type="working",
        weight=100.0, reps=5, rpe=8.0, rest_sec=180,
    )
    db_session.add(workout_set)
    await db_session.commit()

    result = await db_session.execute(
        select(WorkoutSet).where(WorkoutSet.session_id == session.id)
    )
    saved_set = result.scalar_one()
    assert saved_set.weight == 100.0
    assert saved_set.set_type == "working"


@pytest.mark.asyncio
async def test_session_feedback(db_session, user_and_exercise):
    user, _ = user_and_exercise

    session = WorkoutSession(
        user_id=user.id, source="plan",
        started_at=datetime(2026, 3, 23, 10, 0, 0),
        completed_at=datetime(2026, 3, 23, 11, 0, 0),
    )
    db_session.add(session)
    await db_session.commit()

    feedback = SessionFeedback(
        session_id=session.id, sleep_quality=4, energy_level=3,
        muscle_soreness_json={"quads": 3, "hamstrings": 2},
        session_difficulty=4, stress_level=2,
    )
    db_session.add(feedback)
    await db_session.commit()

    result = await db_session.execute(
        select(SessionFeedback).where(SessionFeedback.session_id == session.id)
    )
    saved = result.scalar_one()
    assert saved.sleep_quality == 4
    assert saved.muscle_soreness_json["quads"] == 3
