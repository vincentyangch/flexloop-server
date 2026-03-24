from flexloop.ai.validators import validate_plan_output, validate_review_output


def test_validate_valid_plan_output():
    output = {
        "plan_name": "PPL Block 1",
        "split_type": "ppl",
        "block_weeks": 6,
        "days": [
            {
                "day_number": 1,
                "label": "Push A",
                "focus": "chest,shoulders,triceps",
                "exercise_groups": [
                    {
                        "group_type": "straight",
                        "rest_after_group_sec": 90,
                        "exercises": [
                            {
                                "exercise_name": "Bench Press",
                                "sets": 4, "reps": 8, "rpe_target": 8.0,
                            }
                        ],
                    }
                ],
            }
        ],
    }
    result = validate_plan_output(output)
    assert result.is_valid
    assert result.errors == []


def test_validate_invalid_plan_output_missing_days():
    output = {"plan_name": "Test", "split_type": "ppl", "block_weeks": 6}
    result = validate_plan_output(output)
    assert not result.is_valid
    assert len(result.errors) > 0


def test_validate_invalid_plan_output_empty_days():
    output = {"plan_name": "Test", "split_type": "ppl", "block_weeks": 6, "days": []}
    result = validate_plan_output(output)
    assert not result.is_valid


def test_validate_invalid_plan_output_missing_exercise_groups():
    output = {
        "plan_name": "Test", "split_type": "ppl", "block_weeks": 6,
        "days": [{"day_number": 1, "label": "Push"}],
    }
    result = validate_plan_output(output)
    assert not result.is_valid


def test_validate_valid_review_output():
    output = {
        "summary": "Good progress overall",
        "progressing": ["Bench: +5kg over 4 weeks"],
        "stalling": ["Squat: flat for 3 weeks"],
        "suggestions": [
            {
                "text": "Deload squat",
                "confidence": "high",
                "reasoning": "3 weeks flat at RPE 9+",
            }
        ],
        "deload_recommended": False,
    }
    result = validate_review_output(output)
    assert result.is_valid


def test_validate_invalid_review_missing_summary():
    output = {"suggestions": []}
    result = validate_review_output(output)
    assert not result.is_valid


def test_validate_invalid_review_bad_confidence():
    output = {
        "summary": "Test",
        "suggestions": [
            {"text": "Do more", "confidence": "very_high", "reasoning": "because"}
        ],
    }
    result = validate_review_output(output)
    assert not result.is_valid


def test_validate_invalid_review_missing_suggestion_fields():
    output = {
        "summary": "Test",
        "suggestions": [{"reasoning": "because"}],
    }
    result = validate_review_output(output)
    assert not result.is_valid
    assert len(result.errors) == 2  # missing text and confidence
