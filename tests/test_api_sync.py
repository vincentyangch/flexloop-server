import pytest

from flexloop.models.cycle_tracker import CycleTracker
from flexloop.models.exercise import Exercise
from flexloop.models.plan import ExerciseGroup, Plan, PlanDay, PlanExercise
from flexloop.models.user import User


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


@pytest.mark.asyncio
async def test_sync_completed_plan_workout_advances_cycle(client, db_session, seed_data):
    user, exercise = seed_data
    plan = Plan(
        user_id=user.id,
        name="Two Day Plan",
        split_type="upper_lower",
        cycle_length=2,
        status="active",
        ai_generated=False,
    )
    db_session.add(plan)
    await db_session.flush()

    days = []
    for day_number, label in [(1, "Upper"), (2, "Lower")]:
        day = PlanDay(
            plan_id=plan.id,
            day_number=day_number,
            label=label,
            focus=label.lower(),
        )
        db_session.add(day)
        await db_session.flush()

        group = ExerciseGroup(plan_day_id=day.id, group_type="straight", order=1)
        db_session.add(group)
        await db_session.flush()

        db_session.add(
            PlanExercise(
                plan_day_id=day.id,
                exercise_group_id=group.id,
                exercise_id=exercise.id,
                order=1,
                sets=3,
                reps=5,
            )
        )
        days.append(day)

    db_session.add(CycleTracker(user_id=user.id, plan_id=plan.id, next_day_number=1))
    await db_session.commit()

    response = await client.post("/api/sync", json={
        "user_id": user.id,
        "workouts": [
            {
                "plan_day_id": days[0].id,
                "source": "plan",
                "started_at": "2026-03-23T10:00:00",
                "completed_at": "2026-03-23T11:00:00",
                "sets": [
                    {
                        "exercise_id": exercise.id,
                        "set_number": 1,
                        "set_type": "working",
                        "weight": 100.0,
                        "reps": 5,
                    }
                ],
            }
        ],
    })

    assert response.status_code == 200
    assert response.json()["workouts_synced"] == 1

    next_response = await client.get(f"/api/users/{user.id}/next-workout")
    assert next_response.status_code == 200
    next_data = next_response.json()
    assert next_data["next_day_number"] == 2
    assert next_data["day"]["label"] == "Lower"
