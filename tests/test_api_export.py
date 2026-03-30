import pytest
from datetime import datetime

from flexloop.models.user import User
from flexloop.models.exercise import Exercise
from flexloop.models.workout import WorkoutSession, WorkoutSet


@pytest.fixture
async def seed_data(db_session):
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

    session = WorkoutSession(
        user_id=user.id, source="ad_hoc",
        started_at=datetime(2026, 3, 23, 10, 0, 0),
        completed_at=datetime(2026, 3, 23, 11, 0, 0),
    )
    db_session.add(session)
    await db_session.commit()

    workout_set = WorkoutSet(
        session_id=session.id, exercise_id=exercise.id,
        set_number=1, set_type="working", weight=100.0, reps=5, rpe=8.0,
    )
    db_session.add(workout_set)
    await db_session.commit()

    return user


@pytest.mark.asyncio
async def test_export_json(client, seed_data):
    user = seed_data
    response = await client.get(f"/api/export?user_id={user.id}&format=json")
    assert response.status_code == 200
    data = response.json()
    assert "user" in data
    assert "workouts" in data
    assert len(data["workouts"]) == 1
    assert len(data["workouts"][0]["sets"]) == 1


@pytest.mark.asyncio
async def test_export_single_session(client, seed_data):
    user = seed_data
    workouts_resp = await client.get(f"/api/users/{user.id}/workouts")
    session_id = workouts_resp.json()[0]["id"]

    response = await client.get(f"/api/export/session/{session_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == session_id
    assert len(data["sets"]) == 1


@pytest.mark.asyncio
async def test_export_session_not_found(client):
    response = await client.get("/api/export/session/999")
    assert response.status_code == 404
