import pytest
from sqlalchemy import select

from flexloop.models.user import User
from flexloop.models.exercise import Exercise
from flexloop.models.volume_landmark import VolumeLandmark


@pytest.mark.asyncio
async def test_create_user(db_session):
    user = User(
        name="Test User",
        gender="male",
        age=28,
        height_cm=180.0,
        weight_kg=82.0,
        experience_level="intermediate",
        goals="hypertrophy",
        available_equipment=["barbell", "dumbbells", "pull_up_bar"],
    )
    db_session.add(user)
    await db_session.commit()

    result = await db_session.execute(select(User).where(User.name == "Test User"))
    saved = result.scalar_one()
    assert saved.name == "Test User"
    assert saved.experience_level == "intermediate"
    assert "barbell" in saved.available_equipment
    assert saved.created_at is not None


@pytest.mark.asyncio
async def test_create_exercise(db_session):
    exercise = Exercise(
        name="Barbell Bench Press",
        muscle_group="chest",
        equipment="barbell",
        category="compound",
        difficulty="intermediate",
    )
    db_session.add(exercise)
    await db_session.commit()

    result = await db_session.execute(
        select(Exercise).where(Exercise.name == "Barbell Bench Press")
    )
    saved = result.scalar_one()
    assert saved.muscle_group == "chest"
    assert saved.category == "compound"
    assert saved.source_plugin is None


@pytest.mark.asyncio
async def test_create_volume_landmark(db_session):
    landmark = VolumeLandmark(
        muscle_group="chest",
        experience_level="intermediate",
        mv_sets=6,
        mev_sets=10,
        mav_sets=16,
        mrv_sets=20,
    )
    db_session.add(landmark)
    await db_session.commit()

    result = await db_session.execute(
        select(VolumeLandmark).where(
            VolumeLandmark.muscle_group == "chest",
            VolumeLandmark.experience_level == "intermediate",
        )
    )
    saved = result.scalar_one()
    assert saved.mev_sets == 10
    assert saved.mrv_sets == 20
