import pytest

from flexloop.models.user import User
from flexloop.models.exercise import Exercise


@pytest.fixture
async def seed_user_exercise(db_session):
    user = User(
        name="Test User", gender="male", age=28, height_cm=180.0,
        weight_kg=82.0, experience_level="intermediate", goals="hypertrophy",
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
async def test_create_workout_session(client, seed_user_exercise):
    user, _ = seed_user_exercise
    response = await client.post("/api/workouts", json={
        "user_id": user.id,
        "source": "ad_hoc",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["user_id"] == user.id
    assert data["source"] == "ad_hoc"
    assert data["started_at"] is not None
    assert data["completed_at"] is None


@pytest.mark.asyncio
async def test_update_workout_add_sets(client, seed_user_exercise):
    user, exercise = seed_user_exercise

    create_resp = await client.post("/api/workouts", json={
        "user_id": user.id, "source": "ad_hoc",
    })
    session_id = create_resp.json()["id"]

    response = await client.put(f"/api/workouts/{session_id}", json={
        "sets": [
            {"exercise_id": exercise.id, "set_number": 1, "set_type": "working",
             "weight": 100.0, "reps": 5, "rpe": 7.5},
            {"exercise_id": exercise.id, "set_number": 2, "set_type": "working",
             "weight": 100.0, "reps": 5, "rpe": 8.0},
        ],
    })
    assert response.status_code == 200
    data = response.json()
    assert len(data["sets"]) == 2
    assert data["sets"][0]["weight"] == 100.0


@pytest.mark.asyncio
async def test_complete_workout(client, seed_user_exercise):
    user, _ = seed_user_exercise

    create_resp = await client.post("/api/workouts", json={
        "user_id": user.id, "source": "ad_hoc",
    })
    session_id = create_resp.json()["id"]

    response = await client.put(f"/api/workouts/{session_id}", json={
        "completed_at": "2026-03-23T11:00:00",
    })
    assert response.status_code == 200
    assert response.json()["completed_at"] is not None


@pytest.mark.asyncio
async def test_get_workout_session(client, seed_user_exercise):
    user, _ = seed_user_exercise

    create_resp = await client.post("/api/workouts", json={
        "user_id": user.id, "source": "ad_hoc",
    })
    session_id = create_resp.json()["id"]

    response = await client.get(f"/api/workouts/{session_id}")
    assert response.status_code == 200
    assert response.json()["id"] == session_id


@pytest.mark.asyncio
async def test_list_user_workouts(client, seed_user_exercise):
    user, _ = seed_user_exercise

    await client.post("/api/workouts", json={"user_id": user.id, "source": "ad_hoc"})
    await client.post("/api/workouts", json={"user_id": user.id, "source": "plan"})

    response = await client.get(f"/api/users/{user.id}/workouts")
    assert response.status_code == 200
    assert len(response.json()) == 2


@pytest.mark.asyncio
async def test_submit_session_feedback(client, seed_user_exercise):
    user, _ = seed_user_exercise

    create_resp = await client.post("/api/workouts", json={
        "user_id": user.id, "source": "ad_hoc",
    })
    session_id = create_resp.json()["id"]

    response = await client.post(f"/api/workouts/{session_id}/feedback", json={
        "sleep_quality": 4,
        "energy_level": 3,
        "session_difficulty": 4,
    })
    assert response.status_code == 201
    assert response.json()["sleep_quality"] == 4
