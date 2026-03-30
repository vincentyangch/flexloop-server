import pytest
from datetime import datetime, timedelta

from flexloop.models.user import User
from flexloop.models.exercise import Exercise
from flexloop.models.workout import WorkoutSession, WorkoutSet, SessionFeedback
from flexloop.services.deload import detect_fatigue, generate_deload_week


@pytest.fixture
async def user(db_session):
    user = User(
        name="Test User", gender="male", age=28, height=180.0,
        weight=82.0, weight_unit="kg", height_unit="cm",
        experience_level="intermediate", goals="hypertrophy",
        available_equipment=["barbell"],
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.fixture
async def exercise(db_session):
    ex = Exercise(
        name="Squat", muscle_group="quads", equipment="barbell",
        category="compound", difficulty="intermediate",
    )
    db_session.add(ex)
    await db_session.commit()
    return ex


@pytest.mark.asyncio
async def test_no_deload_with_insufficient_data(db_session, user):
    report = await detect_fatigue(user.id, db_session)
    assert report["deload_recommended"] is False
    assert "Not enough" in report["reason"]


@pytest.mark.asyncio
async def test_no_deload_with_healthy_training(db_session, user, exercise):
    # Create 4 sessions with moderate RPE
    now = datetime.now()
    for i in range(4):
        session = WorkoutSession(
            user_id=user.id, source="plan",
            started_at=now - timedelta(days=10 - i * 2),
            completed_at=now - timedelta(days=10 - i * 2, hours=-1),
        )
        db_session.add(session)
        await db_session.flush()

        for s in range(1, 4):
            workout_set = WorkoutSet(
                session_id=session.id, exercise_id=exercise.id,
                set_number=s, set_type="working",
                weight=100.0, reps=5, rpe=7.0,
            )
            db_session.add(workout_set)

    await db_session.commit()

    report = await detect_fatigue(user.id, db_session)
    assert report["deload_recommended"] is False


@pytest.mark.asyncio
async def test_deload_recommended_with_rising_rpe(db_session, user, exercise):
    now = datetime.now()
    rpes = [7.0, 8.0, 8.5, 9.0, 9.5]

    for i, rpe in enumerate(rpes):
        session = WorkoutSession(
            user_id=user.id, source="plan",
            started_at=now - timedelta(days=12 - i * 2),
            completed_at=now - timedelta(days=12 - i * 2, hours=-1),
        )
        db_session.add(session)
        await db_session.flush()

        for s in range(1, 4):
            workout_set = WorkoutSet(
                session_id=session.id, exercise_id=exercise.id,
                set_number=s, set_type="working",
                weight=100.0, reps=5, rpe=rpe,
            )
            db_session.add(workout_set)

    await db_session.commit()

    report = await detect_fatigue(user.id, db_session)
    assert any(s["signal"] == "rising_rpe" for s in report["signals"])


def test_generate_deload_week():
    exercises = [
        {"exercise_id": 1, "sets": 4, "reps": 8, "weight": 80.0},
        {"exercise_id": 2, "sets": 3, "reps": 10, "weight": 24.0},
        {"exercise_id": 3, "sets": 3, "reps": 12, "weight": None},
    ]

    deload = generate_deload_week(exercises)
    assert len(deload) == 3

    # Sets should be reduced
    assert deload[0]["sets"] == 2  # 4 -> 2
    assert deload[1]["sets"] == 2  # 3 -> min 2

    # Weight should be reduced by ~40%
    assert deload[0]["weight"] == 48.0  # 80 * 0.6
    assert deload[1]["weight"] == 14.4  # 24 * 0.6

    # No weight exercise stays None
    assert deload[2]["weight"] is None

    # All should have deload notes
    assert all("DELOAD" in d["notes"] for d in deload)


@pytest.mark.asyncio
async def test_deload_api_endpoint(client, user):
    resp = await client.get(f"/api/deload/{user.id}/check")
    assert resp.status_code == 200
    data = resp.json()
    assert "deload_recommended" in data
    assert "signals" in data
    assert "confidence" in data
