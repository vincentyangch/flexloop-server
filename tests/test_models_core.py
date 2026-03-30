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
        height=180.0,
        weight=82.0,
        weight_unit="kg",
        height_unit="cm",
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
    assert saved.weight_unit == "kg"
    assert saved.height_unit == "cm"
    assert saved.created_at is not None


@pytest.mark.asyncio
async def test_create_user_imperial(db_session):
    user = User(
        name="Imperial User",
        gender="female",
        age=25,
        height=66.0,
        weight=145.0,
        weight_unit="lbs",
        height_unit="in",
        experience_level="beginner",
        goals="strength",
        available_equipment=["dumbbells"],
    )
    db_session.add(user)
    await db_session.commit()

    result = await db_session.execute(select(User).where(User.name == "Imperial User"))
    saved = result.scalar_one()
    assert saved.weight == 145.0
    assert saved.weight_unit == "lbs"
    assert saved.height == 66.0
    assert saved.height_unit == "in"


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
