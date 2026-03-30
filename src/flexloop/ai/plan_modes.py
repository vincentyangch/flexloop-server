PLAN_MODES = {
    "full_body_3": {
        "plan_name": "Full Body",
        "split_type": "full_body",
        "cycle_length": 3,
        "description": (
            "Cycle length: 3 days\n"
            "- Day 1 (Full Body A): quads, chest, back, shoulders, arms, core\n"
            "- Day 2 (Full Body B): hamstrings, chest, back, shoulders, arms, core\n"
            "- Day 3 (Full Body C): glutes, chest, back, shoulders, arms, core"
        ),
    },
    "upper_lower_4": {
        "plan_name": "Upper / Lower",
        "split_type": "upper_lower",
        "cycle_length": 4,
        "description": (
            "Cycle length: 4 days\n"
            "- Day 1 (Upper A): chest, back, shoulders, biceps, triceps\n"
            "- Day 2 (Lower A): quads, hamstrings, glutes, calves\n"
            "- Day 3 (Upper B): chest, back, shoulders, biceps, triceps\n"
            "- Day 4 (Lower B): quads, hamstrings, glutes, calves"
        ),
    },
    "ppl_6": {
        "plan_name": "Push / Pull / Legs",
        "split_type": "ppl",
        "cycle_length": 6,
        "description": (
            "Cycle length: 6 days\n"
            "- Day 1 (Push A): chest, shoulders, triceps\n"
            "- Day 2 (Pull A): back, biceps, rear delts\n"
            "- Day 3 (Legs A): quads, hamstrings, glutes, calves\n"
            "- Day 4 (Push B): chest, shoulders, triceps\n"
            "- Day 5 (Pull B): back, biceps, rear delts\n"
            "- Day 6 (Legs B): quads, hamstrings, glutes, calves"
        ),
    },
    "arnold_6": {
        "plan_name": "Arnold Split",
        "split_type": "arnold",
        "cycle_length": 6,
        "description": (
            "Cycle length: 6 days\n"
            "- Day 1 (Chest + Back A): chest, back\n"
            "- Day 2 (Shoulders + Arms A): shoulders, biceps, triceps\n"
            "- Day 3 (Legs A): quads, hamstrings, glutes, calves\n"
            "- Day 4 (Chest + Back B): chest, back\n"
            "- Day 5 (Shoulders + Arms B): shoulders, biceps, triceps\n"
            "- Day 6 (Legs B): quads, hamstrings, glutes, calves"
        ),
    },
    "body_part_5": {
        "plan_name": "Body Part Split",
        "split_type": "bro_split",
        "cycle_length": 5,
        "description": (
            "Cycle length: 5 days\n"
            "- Day 1 (Chest): chest, front delts\n"
            "- Day 2 (Back): back, rear delts\n"
            "- Day 3 (Shoulders): shoulders, traps\n"
            "- Day 4 (Legs): quads, hamstrings, glutes, calves\n"
            "- Day 5 (Arms): biceps, triceps, forearms"
        ),
    },
    "ppl_3": {
        "plan_name": "PPL (3-Day)",
        "split_type": "ppl",
        "cycle_length": 3,
        "description": (
            "Cycle length: 3 days\n"
            "- Day 1 (Push): chest, shoulders, triceps\n"
            "- Day 2 (Pull): back, biceps, rear delts\n"
            "- Day 3 (Legs): quads, hamstrings, glutes, calves"
        ),
    },
    "phul_4": {
        "plan_name": "PHUL",
        "split_type": "upper_lower",
        "cycle_length": 4,
        "description": (
            "Cycle length: 4 days\n"
            "- Day 1 (Upper Power): chest, back, shoulders — heavy compounds, 3-5 reps\n"
            "- Day 2 (Lower Power): quads, hamstrings, glutes — heavy compounds, 3-5 reps\n"
            "- Day 3 (Upper Hypertrophy): chest, back, shoulders, arms — moderate weight, 8-12 reps\n"
            "- Day 4 (Lower Hypertrophy): quads, hamstrings, glutes, calves — moderate weight, 8-12 reps"
        ),
    },
}

VALID_PLAN_MODES = set(PLAN_MODES.keys())
