import json
import pytest
from pathlib import Path
from sqlalchemy import select

from flexloop.models.exercise import Exercise


@pytest.mark.asyncio
async def test_seed_exercises(db_session):
    data_path = Path(__file__).parent.parent / "data" / "exercises_core.json"
    with open(data_path) as f:
        exercises_data = json.load(f)

    for ex in exercises_data:
        db_session.add(Exercise(**ex))
    await db_session.commit()

    result = await db_session.execute(select(Exercise))
    exercises = result.scalars().all()
    assert len(exercises) == len(exercises_data)
    assert len(exercises) >= 80  # at least 80 exercises
    assert all(e.name for e in exercises)
    assert all(e.muscle_group for e in exercises)


@pytest.mark.asyncio
async def test_exercise_muscle_group_coverage(db_session):
    data_path = Path(__file__).parent.parent / "data" / "exercises_core.json"
    with open(data_path) as f:
        exercises_data = json.load(f)

    muscle_groups = {ex["muscle_group"] for ex in exercises_data}
    expected = {"chest", "quads", "hamstrings", "glutes", "back", "shoulders",
                "biceps", "triceps", "core", "calves"}
    assert expected.issubset(muscle_groups)


@pytest.mark.asyncio
async def test_exercise_equipment_coverage(db_session):
    data_path = Path(__file__).parent.parent / "data" / "exercises_core.json"
    with open(data_path) as f:
        exercises_data = json.load(f)

    equipment = {ex["equipment"] for ex in exercises_data}
    expected = {"barbell", "dumbbell", "bodyweight", "cable", "machine"}
    assert expected.issubset(equipment)
