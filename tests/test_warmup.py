import pytest

from flexloop.services.warmup import generate_warmup_sets
from flexloop.models.exercise import Exercise


def test_warmup_for_100kg_compound():
    sets = generate_warmup_sets(100.0, "compound")
    assert len(sets) >= 2
    # First set should be bar weight
    assert sets[0]["weight"] == 20.0
    assert sets[0]["reps"] == 10
    # Last set should be around 80% of working weight
    assert sets[-1]["weight"] <= 80.0
    assert sets[-1]["weight"] >= 70.0
    # Weights should be ascending
    for i in range(1, len(sets)):
        assert sets[i]["weight"] > sets[i - 1]["weight"]


def test_warmup_for_60kg_compound():
    sets = generate_warmup_sets(60.0, "compound")
    assert len(sets) >= 2
    assert sets[0]["weight"] == 20.0


def test_no_warmup_for_isolation():
    sets = generate_warmup_sets(30.0, "isolation")
    assert sets == []


def test_no_warmup_for_light_weight():
    sets = generate_warmup_sets(15.0, "compound")
    assert sets == []


def test_warmup_weights_rounded_to_2_5():
    sets = generate_warmup_sets(87.5, "compound")
    for s in sets:
        assert s["weight"] % 2.5 == 0


def test_warmup_for_225lbs_compound():
    sets = generate_warmup_sets(225.0, "compound", "barbell", weight_unit="lbs")
    assert len(sets) >= 2
    # First set should be bar weight (45 lbs)
    assert sets[0]["weight"] == 45.0
    assert sets[0]["reps"] == 10
    # Weights should be ascending
    for i in range(1, len(sets)):
        assert sets[i]["weight"] > sets[i - 1]["weight"]


def test_warmup_lbs_weights_rounded_to_10():
    sets = generate_warmup_sets(225.0, "compound", "barbell", weight_unit="lbs")
    for s in sets:
        assert s["weight"] % 10 == 0 or s["weight"] == 45.0


def test_no_warmup_for_light_weight_lbs():
    sets = generate_warmup_sets(35.0, "compound", "barbell", weight_unit="lbs")
    assert sets == []


@pytest.mark.asyncio
async def test_warmup_api_endpoint(client, db_session):
    exercise = Exercise(
        name="Squat", muscle_group="quads", equipment="barbell",
        category="compound", difficulty="intermediate",
    )
    db_session.add(exercise)
    await db_session.commit()

    resp = await client.get(f"/api/warmup/{exercise.id}?working_weight=100")
    assert resp.status_code == 200
    data = resp.json()
    assert data["exercise_name"] == "Squat"
    assert data["working_weight"] == 100.0
    assert len(data["warmup_sets"]) >= 2


@pytest.mark.asyncio
async def test_warmup_api_isolation_returns_empty(client, db_session):
    exercise = Exercise(
        name="Bicep Curl", muscle_group="biceps", equipment="dumbbell",
        category="isolation", difficulty="beginner",
    )
    db_session.add(exercise)
    await db_session.commit()

    resp = await client.get(f"/api/warmup/{exercise.id}?working_weight=15")
    assert resp.status_code == 200
    assert resp.json()["warmup_sets"] == []
