import pytest
from pydantic import ValidationError
from flexloop.schemas.plan import PlanGenerateRequest
from flexloop.ai.plan_modes import PLAN_MODES, VALID_PLAN_MODES


def test_plan_modes_has_all_keys():
    expected = {
        "full_body_3", "upper_lower_4", "ppl_6", "arnold_6",
        "body_part_5", "ppl_3", "phul_4",
    }
    assert set(PLAN_MODES.keys()) == expected


def test_valid_plan_modes_matches_keys():
    assert VALID_PLAN_MODES == set(PLAN_MODES.keys())


def test_each_mode_has_required_fields():
    for key, mode in PLAN_MODES.items():
        assert "plan_name" in mode, f"{key} missing plan_name"
        assert "split_type" in mode, f"{key} missing split_type"
        assert "cycle_length" in mode, f"{key} missing cycle_length"
        assert "description" in mode, f"{key} missing description"
        assert isinstance(mode["cycle_length"], int)


def test_plan_generate_request_valid():
    req = PlanGenerateRequest(user_id=1, plan_mode="ppl_6")
    assert req.plan_mode == "ppl_6"


def test_plan_generate_request_invalid_mode():
    with pytest.raises(ValidationError):
        PlanGenerateRequest(user_id=1, plan_mode="invalid_mode")


def test_plan_generate_request_missing_mode():
    with pytest.raises(ValidationError):
        PlanGenerateRequest(user_id=1)


from flexloop.ai.validators import validate_plan_v2_output


def test_format_plan_profile_excludes_name_height_equipment():
    from flexloop.routers.ai import format_plan_profile
    from unittest.mock import MagicMock

    user = MagicMock()
    user.gender = "male"
    user.age = 28
    user.weight = 82.0
    user.weight_unit = "kg"
    user.experience_level = "intermediate"
    user.goals = "hypertrophy"
    user.name = "Test"
    user.height = 180.0
    user.available_equipment = ["barbell"]

    profile = format_plan_profile(user)
    assert "male" in profile
    assert "28" in profile
    assert "82.0" in profile
    assert "intermediate" in profile
    assert "hypertrophy" in profile
    assert "Test" not in profile
    assert "180" not in profile
    assert "barbell" not in profile


def test_validate_plan_v2_valid():
    data = {
        "days": [
            {
                "day_number": 1,
                "label": "Push A",
                "focus": "chest,shoulders,triceps",
                "exercise_groups": [
                    {
                        "group_type": "straight",
                        "order": 1,
                        "exercises": [{"exercise_name": "Bench Press", "sets": 4, "reps": 8}],
                    }
                ],
            }
        ]
    }
    result = validate_plan_v2_output(data)
    assert result.is_valid


def test_validate_plan_v2_missing_days():
    result = validate_plan_v2_output({})
    assert not result.is_valid


def test_validate_plan_v2_empty_days():
    result = validate_plan_v2_output({"days": []})
    assert not result.is_valid


def test_validate_plan_v2_missing_exercise_groups():
    data = {"days": [{"day_number": 1, "label": "Push"}]}
    result = validate_plan_v2_output(data)
    assert not result.is_valid
