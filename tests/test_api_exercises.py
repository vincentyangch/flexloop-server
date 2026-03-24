import pytest

from flexloop.models.exercise import Exercise


@pytest.fixture
async def seed_exercises(db_session):
    exercises = [
        Exercise(name="Bench Press", muscle_group="chest", equipment="barbell",
                 category="compound", difficulty="intermediate"),
        Exercise(name="Squat", muscle_group="quads", equipment="barbell",
                 category="compound", difficulty="intermediate"),
        Exercise(name="Push-Up", muscle_group="chest", equipment="bodyweight",
                 category="compound", difficulty="beginner"),
        Exercise(name="Bicep Curl", muscle_group="biceps", equipment="dumbbell",
                 category="isolation", difficulty="beginner"),
    ]
    db_session.add_all(exercises)
    await db_session.commit()


@pytest.mark.asyncio
async def test_list_exercises(client, seed_exercises):
    response = await client.get("/api/exercises")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 4
    assert len(data["exercises"]) == 4


@pytest.mark.asyncio
async def test_search_exercises_by_muscle_group(client, seed_exercises):
    response = await client.get("/api/exercises?muscle_group=chest")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert all(e["muscle_group"] == "chest" for e in data["exercises"])


@pytest.mark.asyncio
async def test_search_exercises_by_equipment(client, seed_exercises):
    response = await client.get("/api/exercises?equipment=bodyweight")
    data = response.json()
    assert data["total"] == 1
    assert data["exercises"][0]["name"] == "Push-Up"


@pytest.mark.asyncio
async def test_search_exercises_by_query(client, seed_exercises):
    response = await client.get("/api/exercises?q=curl")
    data = response.json()
    assert data["total"] == 1
    assert data["exercises"][0]["name"] == "Bicep Curl"


@pytest.mark.asyncio
async def test_get_exercise_by_id(client, seed_exercises):
    list_resp = await client.get("/api/exercises")
    exercise_id = list_resp.json()["exercises"][0]["id"]

    response = await client.get(f"/api/exercises/{exercise_id}")
    assert response.status_code == 200
    assert response.json()["id"] == exercise_id


@pytest.mark.asyncio
async def test_get_exercise_not_found(client):
    response = await client.get("/api/exercises/999")
    assert response.status_code == 404
