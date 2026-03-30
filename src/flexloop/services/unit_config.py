UNIT_CONFIG = {
    "kg": {
        "bar_weight": 20.0,
        "barbell_increment": 5.0,
        "dumbbell_increment": 2.5,
        "default_increment": 2.5,
        "min_meaningful_weight": 20.0,
        "same_weight_tolerance": 2.5,
        "label": "kg",
    },
    "lbs": {
        "bar_weight": 45.0,
        "barbell_increment": 10.0,
        "dumbbell_increment": 5.0,
        "default_increment": 5.0,
        "min_meaningful_weight": 45.0,
        "same_weight_tolerance": 5.0,
        "label": "lbs",
    },
}


def get_unit_config(weight_unit: str) -> dict:
    return UNIT_CONFIG.get(weight_unit, UNIT_CONFIG["kg"])
