"""
FlexLoop AI Prompt Evaluation Runner

Runs test profiles against the AI plan generation prompt and scores outputs.

Usage:
    python -m evals.runner                    # Run all profiles
    python -m evals.runner --profile beginner_female_bodyweight  # Run one profile
    python -m evals.runner --provider openai --model gpt-4o-mini  # Specify model
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

from flexloop.ai.coach import AICoach
from flexloop.ai.factory import create_adapter
from flexloop.ai.prompts import PromptManager
from flexloop.config import settings


EVALS_DIR = Path(__file__).parent
RESULTS_DIR = EVALS_DIR / "results"
PROFILES_PATH = EVALS_DIR / "test_profiles.json"

# Known equipment-to-exercise mappings for validation
BARBELL_EXERCISES = {
    "barbell bench press", "barbell back squat", "front squat", "conventional deadlift",
    "barbell row", "overhead press", "barbell curl", "skull crusher",
    "close-grip bench press", "romanian deadlift", "hip thrust", "t-bar row",
    "pendlay row", "sumo deadlift", "decline bench press", "incline barbell press",
    "good morning", "stiff-leg deadlift", "barbell shrug", "preacher curl",
}

MACHINE_EXERCISES = {
    "leg press", "leg extension", "leg curl", "chest press machine", "pec deck",
    "machine shoulder press", "hack squat", "standing calf raise", "seated calf raise",
}


def format_profile(profile: dict) -> str:
    weight_unit = profile.get("weight_unit", "kg")
    height_unit = profile.get("height_unit", "cm")
    return (
        f"Name: {profile['name']}\n"
        f"Gender: {profile['gender']}, Age: {profile['age']}\n"
        f"Height: {profile['height']}{height_unit}, Weight: {profile['weight']}{weight_unit}\n"
        f"Experience: {profile['experience_level']}\n"
        f"Goals: {profile['goals']}\n"
        f"Available equipment: {', '.join(profile['available_equipment'])}\n"
        f"Days per week: {profile['days_per_week']}"
    )


def score_plan(plan_data: dict | None, profile: dict) -> dict:
    """Score an AI-generated plan against the profile's criteria."""
    criteria = profile.get("criteria", {})
    checks = []
    passed = 0
    total = 0

    if plan_data is None:
        return {
            "score": 0, "total": 1, "percentage": 0,
            "checks": [{"name": "valid_json", "passed": False, "detail": "AI returned invalid output"}],
        }

    # Check 1: Valid structure
    total += 1
    has_days = "days" in plan_data and len(plan_data.get("days", [])) > 0
    checks.append({"name": "valid_structure", "passed": has_days, "detail": f"Has {len(plan_data.get('days', []))} days"})
    if has_days: passed += 1

    # Check 2: Correct number of days
    total += 1
    day_count = len(plan_data.get("days", []))
    expected_days = profile["days_per_week"]
    days_ok = day_count == expected_days
    checks.append({"name": "day_count", "passed": days_ok, "detail": f"Expected {expected_days}, got {day_count}"})
    if days_ok: passed += 1

    # Check 3: Exercise count per day
    min_ex = criteria.get("min_exercises_per_day", 3)
    max_ex = criteria.get("max_exercises_per_day", 10)
    for day in plan_data.get("days", []):
        total += 1
        ex_count = sum(
            len(g.get("exercises", []))
            for g in day.get("exercise_groups", [])
        )
        in_range = min_ex <= ex_count <= max_ex
        checks.append({
            "name": f"exercise_count_day_{day.get('day_number', '?')}",
            "passed": in_range,
            "detail": f"Day {day.get('day_number')}: {ex_count} exercises (expected {min_ex}-{max_ex})",
        })
        if in_range: passed += 1

    # Check 4: No barbell exercises (if equipment doesn't include barbell)
    if "no_barbell" in criteria:
        total += 1
        all_exercises = _get_all_exercise_names(plan_data)
        barbell_found = [e for e in all_exercises if e.lower() in BARBELL_EXERCISES]
        no_barbell = len(barbell_found) == 0
        checks.append({
            "name": "no_barbell",
            "passed": no_barbell,
            "detail": f"Barbell exercises found: {barbell_found}" if barbell_found else "No barbell exercises",
        })
        if no_barbell: passed += 1

    # Check 5: No machine exercises (if equipment doesn't include machines)
    if "no_machine" in criteria:
        total += 1
        all_exercises = _get_all_exercise_names(plan_data)
        machine_found = [e for e in all_exercises if e.lower() in MACHINE_EXERCISES]
        no_machine = len(machine_found) == 0
        checks.append({
            "name": "no_machine",
            "passed": no_machine,
            "detail": f"Machine exercises found: {machine_found}" if machine_found else "No machine exercises",
        })
        if no_machine: passed += 1

    # Check 6: Has RPE targets
    total += 1
    all_exercises_data = _get_all_exercises_data(plan_data)
    has_rpe = any(e.get("rpe_target") for e in all_exercises_data)
    checks.append({"name": "has_rpe", "passed": has_rpe, "detail": "Has RPE targets" if has_rpe else "Missing RPE targets"})
    if has_rpe: passed += 1

    # Check 7: Has sets and reps
    total += 1
    has_sets_reps = all(
        e.get("sets") and e.get("reps")
        for e in all_exercises_data
    )
    checks.append({"name": "has_sets_reps", "passed": has_sets_reps, "detail": "All exercises have sets/reps" if has_sets_reps else "Some exercises missing sets/reps"})
    if has_sets_reps: passed += 1

    percentage = round(passed / total * 100) if total > 0 else 0
    return {"score": passed, "total": total, "percentage": percentage, "checks": checks}


def _get_all_exercise_names(plan_data: dict) -> list[str]:
    names = []
    for day in plan_data.get("days", []):
        for group in day.get("exercise_groups", []):
            for ex in group.get("exercises", []):
                name = ex.get("exercise_name", "")
                if name:
                    names.append(name)
    return names


def _get_all_exercises_data(plan_data: dict) -> list[dict]:
    exercises = []
    for day in plan_data.get("days", []):
        for group in day.get("exercise_groups", []):
            exercises.extend(group.get("exercises", []))
    return exercises


async def run_eval(
    profile: dict,
    provider: str | None = None,
    model: str | None = None,
) -> dict:
    """Run evaluation for a single profile."""
    adapter = create_adapter(
        provider=provider or settings.ai_provider,
        model=model or settings.ai_model,
        api_key=settings.ai_api_key,
        base_url=settings.ai_base_url,
    )
    prompt_manager = PromptManager("prompts")
    coach = AICoach(adapter=adapter, prompt_manager=prompt_manager)

    profile_text = format_profile(profile)
    print(f"\n{'='*60}")
    print(f"Profile: {profile['id']} ({profile['name']})")
    print(f"  {profile['experience_level']} | {profile['goals']} | {profile['days_per_week']} days/week")
    print(f"  Equipment: {', '.join(profile['available_equipment'])}")
    print(f"{'='*60}")

    plan_data, llm_response = await coach.generate_plan(profile_text)

    result = score_plan(plan_data, profile)
    result["profile_id"] = profile["id"]
    result["model"] = model or settings.ai_model
    result["provider"] = provider or settings.ai_provider
    result["input_tokens"] = llm_response.input_tokens
    result["output_tokens"] = llm_response.output_tokens
    result["cache_read_tokens"] = llm_response.cache_read_tokens

    # Print results
    for check in result["checks"]:
        status = "✅" if check["passed"] else "❌"
        print(f"  {status} {check['name']}: {check['detail']}")

    print(f"\n  Score: {result['score']}/{result['total']} ({result['percentage']}%)")
    print(f"  Tokens: {llm_response.input_tokens} in, {llm_response.output_tokens} out"
          + (f", {llm_response.cache_read_tokens} cached" if llm_response.cache_read_tokens else ""))

    return result


async def run_all_evals(
    provider: str | None = None,
    model: str | None = None,
    profile_id: str | None = None,
):
    """Run evaluations for all or a specific test profile."""
    with open(PROFILES_PATH) as f:
        profiles = json.load(f)

    if profile_id:
        profiles = [p for p in profiles if p["id"] == profile_id]
        if not profiles:
            print(f"Profile '{profile_id}' not found")
            return

    results = []
    for profile in profiles:
        result = await run_eval(profile, provider, model)
        results.append(result)

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    total_score = sum(r["score"] for r in results)
    total_checks = sum(r["total"] for r in results)
    overall_pct = round(total_score / total_checks * 100) if total_checks else 0
    total_in = sum(r["input_tokens"] for r in results)
    total_out = sum(r["output_tokens"] for r in results)

    for r in results:
        status = "✅" if r["percentage"] >= 80 else "⚠️" if r["percentage"] >= 60 else "❌"
        print(f"  {status} {r['profile_id']}: {r['score']}/{r['total']} ({r['percentage']}%)")

    print(f"\n  Overall: {total_score}/{total_checks} ({overall_pct}%)")
    print(f"  Model: {results[0]['model']} via {results[0]['provider']}")
    print(f"  Total tokens: {total_in} in, {total_out} out")

    # Save results
    RESULTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_name = (model or settings.ai_model).replace("/", "_")
    result_file = RESULTS_DIR / f"eval_{model_name}_{timestamp}.json"
    with open(result_file, "w") as f:
        json.dump({
            "timestamp": timestamp,
            "model": model or settings.ai_model,
            "provider": provider or settings.ai_provider,
            "overall_score": total_score,
            "overall_total": total_checks,
            "overall_percentage": overall_pct,
            "profiles": results,
        }, f, indent=2)

    print(f"\n  Results saved to: {result_file}")
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="FlexLoop AI Prompt Evaluation")
    parser.add_argument("--profile", help="Run a specific profile by ID")
    parser.add_argument("--provider", help="LLM provider override")
    parser.add_argument("--model", help="Model name override")
    args = parser.parse_args()

    asyncio.run(run_all_evals(
        provider=args.provider,
        model=args.model,
        profile_id=args.profile,
    ))
