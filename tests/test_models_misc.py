import pytest
from datetime import date, datetime
from sqlalchemy import select

from flexloop.models.user import User
from flexloop.models.exercise import Exercise
from flexloop.models.ai import AIReview, AIChatMessage, AIUsage
from flexloop.models.template import Template
from flexloop.models.measurement import Measurement
from flexloop.models.personal_record import PersonalRecord
from flexloop.models.notification import Notification
from flexloop.models.backup import Backup


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
async def test_ai_review(db_session, user):
    review = AIReview(
        user_id=user.id, review_type="block",
        input_summary="8-week PPL block data",
        output_json={"summary": "Good progress"},
        suggestions_json=[{"text": "Increase squat volume", "confidence": "high"}],
        model_used="gpt-4o-mini",
        input_tokens=1500, output_tokens=800, estimated_cost=0.003,
    )
    db_session.add(review)
    await db_session.commit()

    result = await db_session.execute(select(AIReview).where(AIReview.user_id == user.id))
    saved = result.scalar_one()
    assert saved.model_used == "gpt-4o-mini"
    assert saved.input_tokens == 1500


@pytest.mark.asyncio
async def test_ai_chat_message(db_session, user):
    msg = AIChatMessage(
        user_id=user.id, role="user",
        content="Why did you change my squat day?",
        input_tokens=50, output_tokens=0,
    )
    db_session.add(msg)
    await db_session.commit()

    result = await db_session.execute(select(AIChatMessage).where(AIChatMessage.user_id == user.id))
    saved = result.scalar_one()
    assert saved.role == "user"


@pytest.mark.asyncio
async def test_ai_usage(db_session, user):
    usage = AIUsage(
        user_id=user.id, month="2026-03",
        total_input_tokens=5000, total_output_tokens=3000,
        estimated_cost=0.012, call_count=5,
    )
    db_session.add(usage)
    await db_session.commit()

    result = await db_session.execute(select(AIUsage).where(AIUsage.user_id == user.id))
    saved = result.scalar_one()
    assert saved.call_count == 5


@pytest.mark.asyncio
async def test_template(db_session, user):
    template = Template(
        user_id=user.id, name="Quick Push Day",
        exercises_json=[{"exercise_id": 1, "sets": 3, "reps": 10}],
    )
    db_session.add(template)
    await db_session.commit()

    result = await db_session.execute(select(Template).where(Template.user_id == user.id))
    saved = result.scalar_one()
    assert saved.name == "Quick Push Day"


@pytest.mark.asyncio
async def test_measurement(db_session, user):
    m = Measurement(
        user_id=user.id, date=date(2026, 3, 23),
        type="waist", value_cm=82.5, notes="Morning measurement",
    )
    db_session.add(m)
    await db_session.commit()

    result = await db_session.execute(select(Measurement).where(Measurement.user_id == user.id))
    saved = result.scalar_one()
    assert saved.value_cm == 82.5


@pytest.mark.asyncio
async def test_personal_record(db_session, user):
    exercise = Exercise(
        name="Squat", muscle_group="quads", equipment="barbell",
        category="compound", difficulty="intermediate",
    )
    db_session.add(exercise)
    await db_session.commit()

    pr = PersonalRecord(
        user_id=user.id, exercise_id=exercise.id,
        pr_type="estimated_1rm", value=140.0,
        achieved_at=datetime(2026, 3, 23, 10, 30, 0),
    )
    db_session.add(pr)
    await db_session.commit()

    result = await db_session.execute(
        select(PersonalRecord).where(PersonalRecord.user_id == user.id)
    )
    saved = result.scalar_one()
    assert saved.value == 140.0
    assert saved.pr_type == "estimated_1rm"


@pytest.mark.asyncio
async def test_notification(db_session, user):
    n = Notification(
        user_id=user.id, type="pr_achieved",
        title="New PR!", body="You hit a new squat PR: 140kg estimated 1RM",
    )
    db_session.add(n)
    await db_session.commit()

    result = await db_session.execute(select(Notification).where(Notification.user_id == user.id))
    saved = result.scalar_one()
    assert saved.read is False


@pytest.mark.asyncio
async def test_backup(db_session):
    b = Backup(
        filename="flexloop_backup_2026-03-23.db",
        size_bytes=1024000, schema_version="1.0.0",
    )
    db_session.add(b)
    await db_session.commit()

    result = await db_session.execute(select(Backup))
    saved = result.scalar_one()
    assert saved.filename == "flexloop_backup_2026-03-23.db"
