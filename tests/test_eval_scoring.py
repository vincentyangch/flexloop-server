from evals.runner import score_plan


def test_score_valid_plan():
    profile = {
        "days_per_week": 3,
        "criteria": {
            "min_exercises_per_day": 4,
            "max_exercises_per_day": 7,
        },
    }

    plan = {
        "plan_name": "Test Plan",
        "split_type": "full_body",
        "cycle_length": 3,
        "days": [
            {
                "day_number": 1, "label": "Day A", "focus": "full body",
                "exercise_groups": [
                    {"group_type": "straight", "exercises": [
                        {"exercise_name": "Squat", "sets": 3, "reps": 8, "rpe_target": 7},
                        {"exercise_name": "Bench Press", "sets": 3, "reps": 8, "rpe_target": 7},
                        {"exercise_name": "Row", "sets": 3, "reps": 8, "rpe_target": 7},
                        {"exercise_name": "Plank", "sets": 3, "reps": 30, "rpe_target": 6},
                    ]},
                ],
            },
            {
                "day_number": 2, "label": "Day B", "focus": "full body",
                "exercise_groups": [
                    {"group_type": "straight", "exercises": [
                        {"exercise_name": "Deadlift", "sets": 3, "reps": 5, "rpe_target": 8},
                        {"exercise_name": "OHP", "sets": 3, "reps": 8, "rpe_target": 7},
                        {"exercise_name": "Pull-Up", "sets": 3, "reps": 8, "rpe_target": 7},
                        {"exercise_name": "Curl", "sets": 3, "reps": 12, "rpe_target": 6},
                    ]},
                ],
            },
            {
                "day_number": 3, "label": "Day C", "focus": "full body",
                "exercise_groups": [
                    {"group_type": "straight", "exercises": [
                        {"exercise_name": "Front Squat", "sets": 3, "reps": 8, "rpe_target": 7},
                        {"exercise_name": "Incline Press", "sets": 3, "reps": 8, "rpe_target": 7},
                        {"exercise_name": "Cable Row", "sets": 3, "reps": 10, "rpe_target": 7},
                        {"exercise_name": "Lateral Raise", "sets": 3, "reps": 12, "rpe_target": 6},
                    ]},
                ],
            },
        ],
    }

    result = score_plan(plan, profile)
    assert result["percentage"] >= 80  # Should score well
    assert result["score"] > 0


def test_score_none_plan():
    result = score_plan(None, {"criteria": {}})
    assert result["percentage"] == 0


def test_score_wrong_day_count():
    profile = {"days_per_week": 6, "criteria": {}}
    plan = {
        "days": [
            {"day_number": 1, "exercise_groups": [{"exercises": [{"sets": 3, "reps": 8}]}]},
            {"day_number": 2, "exercise_groups": [{"exercises": [{"sets": 3, "reps": 8}]}]},
        ],
    }
    result = score_plan(plan, profile)
    day_check = next(c for c in result["checks"] if c["name"] == "day_count")
    assert day_check["passed"] is False


def test_score_barbell_constraint():
    profile = {
        "days_per_week": 1,
        "criteria": {
            "no_barbell": True,
            "min_exercises_per_day": 1,
            "max_exercises_per_day": 10,
        },
    }
    plan = {
        "days": [{
            "day_number": 1,
            "exercise_groups": [{
                "exercises": [
                    {"exercise_name": "Barbell Bench Press", "sets": 3, "reps": 8, "rpe_target": 7},
                ],
            }],
        }],
    }
    result = score_plan(plan, profile)
    barbell_check = next(c for c in result["checks"] if c["name"] == "no_barbell")
    assert barbell_check["passed"] is False


def test_score_missing_rpe():
    profile = {"days_per_week": 1, "criteria": {"min_exercises_per_day": 1, "max_exercises_per_day": 10}}
    plan = {
        "days": [{
            "day_number": 1,
            "exercise_groups": [{
                "exercises": [
                    {"exercise_name": "Squat", "sets": 3, "reps": 8},  # no rpe_target
                ],
            }],
        }],
    }
    result = score_plan(plan, profile)
    rpe_check = next(c for c in result["checks"] if c["name"] == "has_rpe")
    assert rpe_check["passed"] is False
