import pytest


@pytest.mark.asyncio
async def test_create_profile(client):
    response = await client.post("/api/profiles", json={
        "name": "Test User",
        "gender": "male",
        "age": 28,
        "height_cm": 180.0,
        "weight_kg": 82.0,
        "experience_level": "intermediate",
        "goals": "hypertrophy",
        "available_equipment": ["barbell", "dumbbells"],
    })
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test User"
    assert data["id"] is not None


@pytest.mark.asyncio
async def test_get_profile(client):
    create_resp = await client.post("/api/profiles", json={
        "name": "Test User",
        "gender": "female",
        "age": 25,
        "height_cm": 165.0,
        "weight_kg": 60.0,
        "experience_level": "beginner",
        "goals": "general fitness",
        "available_equipment": [],
    })
    user_id = create_resp.json()["id"]

    response = await client.get(f"/api/profiles/{user_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "Test User"


@pytest.mark.asyncio
async def test_get_profile_not_found(client):
    response = await client.get("/api/profiles/999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_profile(client):
    create_resp = await client.post("/api/profiles", json={
        "name": "Test User",
        "gender": "male",
        "age": 28,
        "height_cm": 180.0,
        "weight_kg": 82.0,
        "experience_level": "intermediate",
        "goals": "hypertrophy",
        "available_equipment": [],
    })
    user_id = create_resp.json()["id"]

    response = await client.put(f"/api/profiles/{user_id}", json={
        "weight_kg": 84.0,
        "goals": "strength",
    })
    assert response.status_code == 200
    assert response.json()["weight_kg"] == 84.0
    assert response.json()["goals"] == "strength"
    assert response.json()["name"] == "Test User"
