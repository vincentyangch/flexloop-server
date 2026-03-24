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
        name="Bench Press", muscle_group="chest", equipment="barbell",
        category="compound", difficulty="intermediate",
    )
    db_session.add_all([user, exercise])
    await db_session.commit()
    return user, exercise


@pytest.mark.asyncio
async def test_first_set_creates_prs(client, seed_user_exercise):
    user, exercise = seed_user_exercise

    # Create a workout
    create_resp = await client.post("/api/workouts", json={
        "user_id": user.id, "source": "ad_hoc",
    })
    workout_id = create_resp.json()["id"]

    # Check PR for first ever set — should create records but not alert (first time)
    resp = await client.post(f"/api/workouts/{workout_id}/check-pr", json={
        "exercise_id": exercise.id, "set_number": 1, "set_type": "working",
        "weight": 80.0, "reps": 8,
    })
    assert resp.status_code == 200
    data = resp.json()
    # First set creates 1RM PR (always a PR on first set)
    assert any(pr["type"] == "estimated_1rm" for pr in data["new_prs"])


@pytest.mark.asyncio
async def test_new_pr_detected(client, seed_user_exercise):
    user, exercise = seed_user_exercise

    # Create workout and establish baseline
    create_resp = await client.post("/api/workouts", json={
        "user_id": user.id, "source": "ad_hoc",
    })
    workout_id = create_resp.json()["id"]

    # First set — establishes baseline
    await client.post(f"/api/workouts/{workout_id}/check-pr", json={
        "exercise_id": exercise.id, "set_number": 1, "set_type": "working",
        "weight": 80.0, "reps": 8,
    })

    # Second set with more weight — should be a new 1RM PR
    resp = await client.post(f"/api/workouts/{workout_id}/check-pr", json={
        "exercise_id": exercise.id, "set_number": 2, "set_type": "working",
        "weight": 85.0, "reps": 8,
    })
    data = resp.json()
    pr_1rm = [pr for pr in data["new_prs"] if pr["type"] == "estimated_1rm"]
    assert len(pr_1rm) == 1
    assert pr_1rm[0]["value"] > pr_1rm[0]["previous"]


@pytest.mark.asyncio
async def test_no_pr_on_lower_weight(client, seed_user_exercise):
    user, exercise = seed_user_exercise

    create_resp = await client.post("/api/workouts", json={
        "user_id": user.id, "source": "ad_hoc",
    })
    workout_id = create_resp.json()["id"]

    # Establish baseline
    await client.post(f"/api/workouts/{workout_id}/check-pr", json={
        "exercise_id": exercise.id, "set_number": 1, "set_type": "working",
        "weight": 100.0, "reps": 5,
    })

    # Lower weight, fewer reps — no PR
    resp = await client.post(f"/api/workouts/{workout_id}/check-pr", json={
        "exercise_id": exercise.id, "set_number": 2, "set_type": "working",
        "weight": 80.0, "reps": 5,
    })
    data = resp.json()
    assert len(data["new_prs"]) == 0


@pytest.mark.asyncio
async def test_get_user_prs(client, seed_user_exercise):
    user, exercise = seed_user_exercise

    create_resp = await client.post("/api/workouts", json={
        "user_id": user.id, "source": "ad_hoc",
    })
    workout_id = create_resp.json()["id"]

    # Create some PRs
    await client.post(f"/api/workouts/{workout_id}/check-pr", json={
        "exercise_id": exercise.id, "set_number": 1, "set_type": "working",
        "weight": 100.0, "reps": 5,
    })

    # Fetch user PRs
    resp = await client.get(f"/api/users/{user.id}/prs")
    assert resp.status_code == 200
    prs = resp.json()
    assert len(prs) >= 1  # At least 1RM PR


@pytest.mark.asyncio
async def test_get_exercise_prs(client, seed_user_exercise):
    user, exercise = seed_user_exercise

    create_resp = await client.post("/api/workouts", json={
        "user_id": user.id, "source": "ad_hoc",
    })
    workout_id = create_resp.json()["id"]

    await client.post(f"/api/workouts/{workout_id}/check-pr", json={
        "exercise_id": exercise.id, "set_number": 1, "set_type": "working",
        "weight": 100.0, "reps": 5,
    })

    resp = await client.get(f"/api/exercises/{exercise.id}/prs")
    assert resp.status_code == 200
    prs = resp.json()
    assert len(prs) >= 1
