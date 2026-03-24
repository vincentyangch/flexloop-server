from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_plan_output(data: dict) -> ValidationResult:
    errors = []

    required_fields = ["plan_name", "split_type", "block_weeks", "days"]
    for f in required_fields:
        if f not in data:
            errors.append(f"Missing required field: {f}")

    if "days" in data:
        if not isinstance(data["days"], list) or len(data["days"]) == 0:
            errors.append("'days' must be a non-empty list")
        else:
            for i, day in enumerate(data["days"]):
                if "exercise_groups" not in day:
                    errors.append(f"Day {i + 1} missing 'exercise_groups'")
                elif not isinstance(day["exercise_groups"], list):
                    errors.append(f"Day {i + 1} 'exercise_groups' must be a list")

    return ValidationResult(is_valid=len(errors) == 0, errors=errors)


def validate_review_output(data: dict) -> ValidationResult:
    errors = []

    required_fields = ["summary", "suggestions"]
    for f in required_fields:
        if f not in data:
            errors.append(f"Missing required field: {f}")

    if "suggestions" in data:
        if not isinstance(data["suggestions"], list):
            errors.append("'suggestions' must be a list")
        else:
            for i, s in enumerate(data["suggestions"]):
                if "text" not in s:
                    errors.append(f"Suggestion {i + 1} missing 'text'")
                if "confidence" not in s:
                    errors.append(f"Suggestion {i + 1} missing 'confidence'")
                elif s["confidence"] not in ("high", "medium", "low"):
                    errors.append(f"Suggestion {i + 1} has invalid confidence: {s['confidence']}")

    return ValidationResult(is_valid=len(errors) == 0, errors=errors)
