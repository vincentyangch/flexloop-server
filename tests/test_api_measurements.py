import pytest

from flexloop.models.user import User


@pytest.fixture
async def user(db_session):
    user = User(
        name="Test User", gender="male", age=28, height=180.0,
        weight=82.0, weight_unit="kg", height_unit="cm",
        experience_level="intermediate", goals="hypertrophy",
        available_equipment=[],
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.mark.asyncio
async def test_create_measurement(client, user):
    response = await client.post("/api/measurements", json={
        "user_id": user.id,
        "date": "2026-03-23",
        "type": "waist",
        "value": 82.5,
        "notes": "Morning measurement",
    })
    assert response.status_code == 201
    assert response.json()["value"] == 82.5


@pytest.mark.asyncio
async def test_list_measurements(client, user):
    await client.post("/api/measurements", json={
        "user_id": user.id, "date": "2026-03-20", "type": "waist", "value": 83.0,
    })
    await client.post("/api/measurements", json={
        "user_id": user.id, "date": "2026-03-23", "type": "waist", "value": 82.5,
    })
    await client.post("/api/measurements", json={
        "user_id": user.id, "date": "2026-03-23", "type": "chest", "value": 100.0,
    })

    response = await client.get(f"/api/users/{user.id}/measurements?type=waist")
    assert response.status_code == 200
    assert len(response.json()) == 2
