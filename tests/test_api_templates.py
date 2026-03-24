import pytest

from flexloop.models.user import User


@pytest.fixture
async def user(db_session):
    user = User(
        name="Test User", gender="male", age=28, height_cm=180.0,
        weight_kg=82.0, experience_level="intermediate", goals="hypertrophy",
        available_equipment=[],
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.mark.asyncio
async def test_create_template(client, user):
    response = await client.post("/api/templates", json={
        "user_id": user.id,
        "name": "Quick Push Day",
        "exercises_json": [
            {"exercise_id": 1, "sets": 3, "reps": 10, "group_type": "straight"},
        ],
    })
    assert response.status_code == 201
    assert response.json()["name"] == "Quick Push Day"


@pytest.mark.asyncio
async def test_list_templates(client, user):
    await client.post("/api/templates", json={
        "user_id": user.id, "name": "Push Day",
        "exercises_json": [{"exercise_id": 1, "sets": 3, "reps": 10}],
    })
    await client.post("/api/templates", json={
        "user_id": user.id, "name": "Pull Day",
        "exercises_json": [{"exercise_id": 2, "sets": 3, "reps": 10}],
    })

    response = await client.get(f"/api/templates?user_id={user.id}")
    assert response.status_code == 200
    assert len(response.json()) == 2


@pytest.mark.asyncio
async def test_update_template(client, user):
    create_resp = await client.post("/api/templates", json={
        "user_id": user.id, "name": "Push Day",
        "exercises_json": [{"exercise_id": 1, "sets": 3, "reps": 10}],
    })
    template_id = create_resp.json()["id"]

    response = await client.put(f"/api/templates/{template_id}", json={
        "name": "Heavy Push Day",
    })
    assert response.status_code == 200
    assert response.json()["name"] == "Heavy Push Day"


@pytest.mark.asyncio
async def test_delete_template(client, user):
    create_resp = await client.post("/api/templates", json={
        "user_id": user.id, "name": "Push Day",
        "exercises_json": [{"exercise_id": 1, "sets": 3, "reps": 10}],
    })
    template_id = create_resp.json()["id"]

    response = await client.delete(f"/api/templates/{template_id}")
    assert response.status_code == 204

    response = await client.get(f"/api/templates/{template_id}")
    assert response.status_code == 404
