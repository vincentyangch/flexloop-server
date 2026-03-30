from flexloop.services.unit_config import get_unit_config


def generate_warmup_sets(
    working_weight: float,
    exercise_category: str = "compound",
    equipment: str = "barbell",
    weight_unit: str = "kg",
) -> list[dict]:
    """Generate warm-up sets ramping up to the working weight.

    Only generates warm-ups for compound exercises with meaningful weight.
    Returns warm-up weights rounded to equipment-appropriate increments.
    """
    config = get_unit_config(weight_unit)

    if exercise_category != "compound" or working_weight <= config["min_meaningful_weight"]:
        return []

    bar_weight, increment = _equipment_config(equipment, weight_unit=weight_unit)
    sets = []

    # Define warm-up steps as (percentage of working weight, reps)
    steps = [
        (0.0, 10),   # Bar only
        (0.4, 8),    # 40%
        (0.6, 5),    # 60%
        (0.8, 3),    # 80%
    ]

    for pct, reps in steps:
        if pct > 0:
            weight = round_to_nearest(working_weight * pct, increment)
            weight = max(weight, bar_weight if bar_weight > 0 else increment)
        else:
            # "Bar only" set — skip for non-barbell equipment
            if bar_weight <= 0:
                continue
            weight = bar_weight

        # Skip if weight is same as or less than bar (except bar-only set)
        if pct > 0 and bar_weight > 0 and weight <= bar_weight:
            continue

        # Skip if weight is same as previous set
        if sets and weight <= sets[-1]["weight"]:
            continue

        # Skip if weight is too close to working weight (within one increment)
        if working_weight - weight < increment and pct < 0.9:
            continue

        sets.append({
            "weight": weight,
            "reps": reps,
            "percentage": int(pct * 100) if pct > 0 else 0,
            "rest_sec": 30 if pct < 0.6 else 45,
        })

    return sets


def _equipment_config(equipment: str, weight_unit: str = "kg") -> tuple[float, float]:
    """Return (bar_weight, plate_increment) for equipment type and unit."""
    config = get_unit_config(weight_unit)
    equip = equipment.lower()
    if equip == "barbell":
        return config["bar_weight"], config["barbell_increment"]
    elif equip in ("dumbbell", "dumbbells"):
        return 0.0, config["dumbbell_increment"]
    else:
        return 0.0, config["default_increment"]


def round_to_nearest(value: float, increment: float) -> float:
    """Round to nearest weight increment."""
    return round(value / increment) * increment
