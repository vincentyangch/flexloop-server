def generate_warmup_sets(
    working_weight: float,
    exercise_category: str = "compound",
    equipment: str = "barbell",
) -> list[dict]:
    """Generate warm-up sets ramping up to the working weight.

    Only generates warm-ups for compound exercises with meaningful weight.
    Working weight is always in kg (server stores kg).
    Returns warm-up weights rounded to equipment-appropriate increments.
    """
    if exercise_category != "compound" or working_weight <= 20:
        return []

    bar_weight, increment = _equipment_config(equipment)
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


def _equipment_config(equipment: str) -> tuple[float, float]:
    """Return (bar_weight_kg, plate_increment_kg) for equipment type."""
    equip = equipment.lower()
    if equip == "barbell":
        return 20.0, 5.0    # 20kg bar, 2x2.5kg plates = 5kg steps
    elif equip in ("dumbbell", "dumbbells"):
        return 0.0, 2.5     # no bar, 2.5kg dumbbell steps
    else:
        return 0.0, 2.5     # default


def round_to_nearest(value: float, increment: float) -> float:
    """Round to nearest weight increment."""
    return round(value / increment) * increment
