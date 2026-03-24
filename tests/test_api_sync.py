import pytest

from flexloop.models.user import User
from flexloop.models.exercise import Exercise


@pytest.fixture
async def seed_data(db_session):
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
async def test_sync_push_workouts(client, seed_data):
    user, exercise = seed_data

    response = await client.post("/api/sync", json={
        "user_id": user.id,
        "workouts": [
            {
                "source": "ad_hoc",
                "started_at": "2026-03-23T10:00:00",
                "completed_at": "2026-03-23T11:00:00",
                "sets": [
                    {
                        "exercise_id": exercise.id, "set_number": 1,
                        "set_type": "working", "weight": 100.0, "reps": 5,
                    }
                ],
            }
        ],
    })
    assert response.status_code == 200
    data = response.json()
    assert data["workouts_synced"] == 1

    # Verify workout was persisted
    workouts_resp = await client.get(f"/api/users/{user.id}/workouts")
    assert len(workouts_resp.json()) == 1
    assert len(workouts_resp.json()[0]["sets"]) == 1


@pytest.mark.asyncio
async def test_sync_empty_payload(client, seed_data):
    user, _ = seed_data
    response = await client.post("/api/sync", json={
        "user_id": user.id,
        "workouts": [],
    })
    assert response.status_code == 200
    assert response.json()["workouts_synced"] == 0


@pytest.mark.asyncio
async def test_sync_multiple_workouts(client, seed_data):
    user, exercise = seed_data

    response = await client.post("/api/sync", json={
        "user_id": user.id,
        "workouts": [
            {
                "source": "plan",
                "started_at": "2026-03-22T10:00:00",
                "completed_at": "2026-03-22T11:00:00",
                "sets": [
                    {"exercise_id": exercise.id, "set_number": 1,
                     "set_type": "working", "weight": 95.0, "reps": 5},
                ],
            },
            {
                "source": "ad_hoc",
                "started_at": "2026-03-23T10:00:00",
                "sets": [],
            },
        ],
    })
    assert response.status_code == 200
    assert response.json()["workouts_synced"] == 2
