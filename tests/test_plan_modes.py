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
