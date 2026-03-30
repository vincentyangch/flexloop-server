import pytest

from flexloop.models.exercise import Exercise
from flexloop.models.user import User


@pytest.fixture
async def user(db_session):
    user = User(
        name="Test User", gender="male", age=28, height=180.0,
        weight=82.0, weight_unit="kg", height_unit="cm",
        experience_level="intermediate", goals="hypertrophy",
        available_equipment=["barbell", "dumbbell"],
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.fixture
async def exercise(db_session):
    ex = Exercise(
        name="Bench Press", muscle_group="chest", equipment="barbell",
        category="compound", difficulty="intermediate",
    )
    db_session.add(ex)
    await db_session.commit()
    return ex


def _plan_payload(user_id, exercise_id, name="Push Day Plan"):
    return {
        "user_id": user_id,
        "name": name,
        "split_type": "push_pull_legs",
        "cycle_length": 3,
        "days": [
            {
                "day_number": 1,
                "label": "Push",
                "focus": "chest, shoulders, triceps",
                "exercise_groups": [
                    {
                        "group_type": "straight",
                        "order": 1,
                        "rest_after_group_sec": 120,
                        "exercises": [
                            {
                                "exercise_id": exercise_id,
                                "order": 1,
                                "sets": 3,
                                "reps": 5,
                                "weight": 80.0,
                                "rpe_target": 7.0,
                                "sets_json": [
                                    {"set_number": 1, "target_weight": 80, "target_reps": 5, "target_rpe": 7},
                                    {"set_number": 2, "target_weight": 80, "target_reps": 5, "target_rpe": 8},
                                    {"set_number": 3, "target_weight": 80, "target_reps": 5, "target_rpe": 8.5},
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    }


@pytest.mark.asyncio
async def test_create_plan(client, user, exercise):
    resp = await client.post("/api/plans", json=_plan_payload(user.id, exercise.id))
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Push Day Plan"
    assert data["cycle_length"] == 3
    assert data["status"] == "active"
    assert len(data["days"]) == 1
    assert len(data["days"][0]["exercise_groups"]) == 1
    ex = data["days"][0]["exercise_groups"][0]["exercises"][0]
    assert ex["sets_json"] is not None
    assert len(ex["sets_json"]) == 3


@pytest.mark.asyncio
async def test_list_plans(client, user, exercise):
    await client.post("/api/plans", json=_plan_payload(user.id, exercise.id, "Plan A"))
    await client.post("/api/plans", json=_plan_payload(user.id, exercise.id, "Plan B"))

    resp = await client.get(f"/api/plans?user_id={user.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2


@pytest.mark.asyncio
async def test_list_plans_filter_status(client, user, exercise):
    resp1 = await client.post("/api/plans", json=_plan_payload(user.id, exercise.id, "Plan A"))
    plan_id = resp1.json()["id"]
    await client.post("/api/plans", json=_plan_payload(user.id, exercise.id, "Plan B"))

    # Archive one
    await client.put(f"/api/plans/{plan_id}/archive")

    resp = await client.get(f"/api/plans?user_id={user.id}&status=active")
    assert resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_get_plan(client, user, exercise):
    create_resp = await client.post("/api/plans", json=_plan_payload(user.id, exercise.id))
    plan_id = create_resp.json()["id"]

    resp = await client.get(f"/api/plans/{plan_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == plan_id


@pytest.mark.asyncio
async def test_get_plan_not_found(client):
    resp = await client.get("/api/plans/999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_plan_name(client, user, exercise):
    create_resp = await client.post("/api/plans", json=_plan_payload(user.id, exercise.id))
    plan_id = create_resp.json()["id"]

    resp = await client.put(f"/api/plans/{plan_id}", json={"name": "Updated Plan"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Plan"


@pytest.mark.asyncio
async def test_update_plan_days(client, user, exercise):
    create_resp = await client.post("/api/plans", json=_plan_payload(user.id, exercise.id))
    plan_id = create_resp.json()["id"]

    # Replace days with 2 days
    resp = await client.put(f"/api/plans/{plan_id}", json={
        "days": [
            {"day_number": 1, "label": "Day A", "focus": "upper"},
            {"day_number": 2, "label": "Day B", "focus": "lower"},
        ],
    })
    assert resp.status_code == 200
    assert len(resp.json()["days"]) == 2


@pytest.mark.asyncio
async def test_activate_plan(client, user, exercise):
    resp1 = await client.post("/api/plans", json=_plan_payload(user.id, exercise.id, "Plan A"))
    resp2 = await client.post("/api/plans", json=_plan_payload(user.id, exercise.id, "Plan B"))
    plan_a_id = resp1.json()["id"]
    plan_b_id = resp2.json()["id"]

    # Activate plan B (should deactivate plan A)
    resp = await client.put(f"/api/plans/{plan_b_id}/activate")
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"

    # Check plan A is inactive
    resp_a = await client.get(f"/api/plans/{plan_a_id}")
    assert resp_a.json()["status"] == "inactive"


@pytest.mark.asyncio
async def test_archive_plan(client, user, exercise):
    create_resp = await client.post("/api/plans", json=_plan_payload(user.id, exercise.id))
    plan_id = create_resp.json()["id"]

    resp = await client.put(f"/api/plans/{plan_id}/archive")
    assert resp.status_code == 200
    assert resp.json()["status"] == "inactive"


@pytest.mark.asyncio
async def test_delete_plan(client, user, exercise):
    create_resp = await client.post("/api/plans", json=_plan_payload(user.id, exercise.id))
    plan_id = create_resp.json()["id"]

    resp = await client.delete(f"/api/plans/{plan_id}")
    assert resp.status_code == 204

    resp = await client.get(f"/api/plans/{plan_id}")
    assert resp.status_code == 404
