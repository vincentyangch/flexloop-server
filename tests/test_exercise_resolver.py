from unittest.mock import MagicMock

from flexloop.ai.exercise_resolver import resolve_exercise_name


def _make_exercise(name: str, id: int) -> MagicMock:
    ex = MagicMock()
    ex.name = name
    ex.id = id
    return ex


def _make_library() -> dict:
    exercises = [
        _make_exercise("Barbell Bench Press", 1),
        _make_exercise("Incline Dumbbell Press", 2),
        _make_exercise("Leg Press", 3),
        _make_exercise("Barbell Squat", 4),
        _make_exercise("Romanian Deadlift", 5),
    ]
    return {e.name.lower(): e for e in exercises}


def test_exact_match():
    lib = _make_library()
    result = resolve_exercise_name("Barbell Bench Press", lib)
    assert result is not None
    assert result.id == 1


def test_case_insensitive_match():
    lib = _make_library()
    result = resolve_exercise_name("barbell bench press", lib)
    assert result is not None
    assert result.id == 1


def test_exact_preferred_over_substring():
    lib = _make_library()
    result = resolve_exercise_name("Leg Press", lib)
    assert result is not None
    assert result.id == 3


def test_substring_fallback():
    lib = _make_library()
    result = resolve_exercise_name("Bench Press", lib)
    assert result is not None
    assert result.id == 1


def test_no_match_returns_none():
    lib = _make_library()
    result = resolve_exercise_name("Cable Fly", lib)
    assert result is None


def test_empty_name_returns_none():
    lib = _make_library()
    result = resolve_exercise_name("", lib)
    assert result is None
