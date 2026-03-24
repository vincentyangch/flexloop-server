import pytest

from flexloop.models.user import User
from flexloop.models.ai import AIUsage


@pytest.fixture
async def user(db_session):
    user = User(
        name="Test User", gender="male", age=28, height_cm=180.0,
        weight_kg=82.0, experience_level="intermediate", goals="hypertrophy",
        available_equipment=["barbell", "dumbbells"],
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.mark.asyncio
async def test_ai_usage_endpoint_empty(client, user):
    response = await client.get(f"/api/ai/usage?user_id={user.id}")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_ai_usage_endpoint_with_data(client, user, db_session):
    usage = AIUsage(
        user_id=user.id, month="2026-03",
        total_input_tokens=5000, total_output_tokens=3000,
        estimated_cost=0.012, call_count=5,
    )
    db_session.add(usage)
    await db_session.commit()

    response = await client.get(f"/api/ai/usage?user_id={user.id}")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["month"] == "2026-03"
    assert data[0]["call_count"] == 5
    assert data[0]["estimated_cost"] == 0.012
