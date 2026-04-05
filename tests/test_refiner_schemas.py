from pathlib import Path

import pytest
from pydantic import ValidationError

from flexloop.schemas.ai import (
    SuggestSwapRequest,
    AdjustVolumeRequest,
    ExplainExerciseRequest,
    PlanRefineRequest,
)


def test_suggest_swap_request_valid():
    req = SuggestSwapRequest(user_id=1, day_number=1, exercise_name="Bench Press")
    assert req.day_number == 1


def test_adjust_volume_request_valid():
    req = AdjustVolumeRequest(user_id=1, day_number=3, direction="lighter")
    assert req.direction == "lighter"


def test_adjust_volume_request_invalid_direction():
    with pytest.raises(ValidationError):
        AdjustVolumeRequest(user_id=1, day_number=3, direction="extreme")


def test_explain_request_valid():
    req = ExplainExerciseRequest(user_id=1, day_number=1, exercise_name="Squat")
    assert req.exercise_name == "Squat"


def test_plan_refine_request_valid():
    req = PlanRefineRequest(
        user_id=1,
        message="Make leg day lighter",
        history=[{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello"}],
    )
    assert req.message == "Make leg day lighter"
    assert len(req.history) == 2


def test_plan_refine_request_empty_history():
    req = PlanRefineRequest(user_id=1, message="test", history=[])
    assert req.history == []


def test_refinement_prompt_renders():
    prompts_dir = Path(__file__).parent.parent / "prompts"
    if not prompts_dir.exists():
        pytest.skip("prompts directory not found")
    from flexloop.ai.prompts import PromptManager
    manager = PromptManager(prompts_dir)
    rendered = manager.render(
        "plan_refinement",
        user_profile="Gender: male, Age: 28\nWeight: 82.0kg\nExperience: intermediate\nGoals: hypertrophy",
        plan_structure="Day 1 (Push A): Bench Press 4x8, Incline DB Press 3x10",
        exercise_library="Barbell Bench Press, Incline Dumbbell Press, Dumbbell Fly",
        weight_unit="kg",
    )
    assert "82.0kg" in rendered
    assert "Push A" in rendered
    assert "Dumbbell Fly" in rendered
    assert "{{user_profile}}" not in rendered
