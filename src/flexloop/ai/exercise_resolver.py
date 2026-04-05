"""Shared exercise name resolution with fuzzy matching."""


def resolve_exercise_name(name: str, exercise_library: dict):
    """Resolve an exercise name to an Exercise object from the library.

    Matching priority:
    1. Exact match (case-insensitive)
    2. Substring match (prefer closest length match)

    Args:
        name: Exercise name to resolve.
        exercise_library: Dict mapping lowercase exercise names to Exercise objects.

    Returns:
        Exercise object if found, None otherwise.
    """
    if not name:
        return None

    normalized = name.strip().lower()

    # 1. Exact match
    if normalized in exercise_library:
        return exercise_library[normalized]

    # 2. Substring match — prefer key closest in length to input
    candidates = []
    for key, ex in exercise_library.items():
        if normalized in key or key in normalized:
            candidates.append((key, ex))

    if candidates:
        candidates.sort(key=lambda pair: abs(len(pair[0]) - len(normalized)))
        return candidates[0][1]

    return None
