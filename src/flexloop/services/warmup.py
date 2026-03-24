def generate_warmup_sets(working_weight: float, exercise_category: str = "compound") -> list[dict]:
    """Generate warm-up sets ramping up to the working weight.

    Only generates warm-ups for compound exercises with meaningful weight.
    Returns a list of warm-up set suggestions.
    """
    if exercise_category != "compound" or working_weight <= 20:
        return []

    bar_weight = 20.0  # Standard barbell
    sets = []

    # Define warm-up steps as (percentage of working weight, reps)
    steps = [
        (0.0, 10),   # Bar only
        (0.4, 8),    # 40%
        (0.6, 5),    # 60%
        (0.8, 3),    # 80%
    ]

    for pct, reps in steps:
        weight = round_to_nearest(working_weight * pct, 2.5) if pct > 0 else bar_weight

        # Skip if weight is same as or less than bar
        if pct > 0 and weight <= bar_weight:
            continue

        # Skip if weight is same as previous set
        if sets and weight <= sets[-1]["weight"]:
            continue

        # Skip if weight is too close to working weight (within 5kg)
        if working_weight - weight < 5 and pct < 0.9:
            continue

        sets.append({
            "weight": weight,
            "reps": reps,
            "percentage": int(pct * 100) if pct > 0 else 0,
            "rest_sec": 30 if pct < 0.6 else 45,
        })

    return sets


def round_to_nearest(value: float, increment: float) -> float:
    """Round to nearest weight increment (e.g., 2.5kg plates)."""
    return round(value / increment) * increment
