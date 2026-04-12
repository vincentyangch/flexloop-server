import pytest

from flexloop.routers import ai as ai_router
from flexloop.models.user import User
from flexloop.models.ai import AIUsage


@pytest.fixture
async def user(db_session):
    user = User(
        name="Test User", gender="male", age=28, height=180.0,
        weight=82.0, weight_unit="kg", height_unit="cm",
        experience_level="intermediate", goals="hypertrophy",
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


def test_get_ai_coach_passes_codex_settings_to_factory(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, object] = {}

    monkeypatch.setattr(ai_router.settings, "ai_provider", "openai-codex")
    monkeypatch.setattr(ai_router.settings, "ai_model", "gpt-5.1-codex-max")
    monkeypatch.setattr(ai_router.settings, "ai_api_key", "")
    monkeypatch.setattr(ai_router.settings, "ai_base_url", "")
    monkeypatch.setattr(ai_router.settings, "codex_auth_file", "/tmp/coach-auth.json")
    monkeypatch.setattr(ai_router.settings, "ai_reasoning_effort", "minimal")
    monkeypatch.setattr(
        ai_router, "create_adapter", lambda **kwargs: captured.update(kwargs) or "adapter"
    )
    monkeypatch.setattr(
        ai_router,
        "PromptManager",
        lambda prompts_dir: {"prompts_dir": prompts_dir},
    )
    monkeypatch.setattr(
        ai_router,
        "AICoach",
        lambda adapter, prompt_manager: {
            "adapter": adapter,
            "prompt_manager": prompt_manager,
        },
    )

    coach = ai_router.get_ai_coach()

    assert coach["adapter"] == "adapter"
    assert captured["codex_auth_file"] == "/tmp/coach-auth.json"
    assert captured["reasoning_effort"] == "minimal"


def test_get_plan_refiner_passes_codex_settings_to_factory(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict[str, object] = {}

    monkeypatch.setattr(ai_router.settings, "ai_provider", "openai-codex")
    monkeypatch.setattr(ai_router.settings, "ai_model", "gpt-5.1-codex-max")
    monkeypatch.setattr(ai_router.settings, "ai_api_key", "")
    monkeypatch.setattr(ai_router.settings, "ai_base_url", "")
    monkeypatch.setattr(ai_router.settings, "codex_auth_file", "/tmp/refiner-auth.json")
    monkeypatch.setattr(ai_router.settings, "ai_reasoning_effort", "high")
    monkeypatch.setattr(
        ai_router, "create_adapter", lambda **kwargs: captured.update(kwargs) or "adapter"
    )
    monkeypatch.setattr(
        ai_router,
        "PromptManager",
        lambda prompts_dir: {"prompts_dir": prompts_dir},
    )
    monkeypatch.setattr(
        ai_router,
        "PlanRefiner",
        lambda adapter, prompt_manager: {
            "adapter": adapter,
            "prompt_manager": prompt_manager,
        },
    )

    refiner = ai_router.get_plan_refiner()

    assert refiner["adapter"] == "adapter"
    assert captured["codex_auth_file"] == "/tmp/refiner-auth.json"
    assert captured["reasoning_effort"] == "high"
