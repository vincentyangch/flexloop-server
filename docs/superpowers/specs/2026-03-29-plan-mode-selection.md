# Plan Mode Selection for Plan Generation

## Problem

Currently, plan generation is a one-tap action where the AI decides everything (split type, cycle length, day structure) based on the user profile. The user has no control over what kind of program they get. Additionally, the prompt sends unnecessary information (name, height, equipment list) and assumes equipment might be limited.

## Goals

1. Let users choose from 7 predefined plan modes before generation
2. Simplify the AI prompt to focus on exercise selection, not program design
3. Remove irrelevant fields from the user profile sent to AI
4. Remove equipment selection from onboarding (gym-first assumption)

## Plan Modes

| Key | Display Name | Days/Cycle | split_type | Structure | Suited For |
|-----|-------------|-----------|------------|-----------|------------|
| `full_body_3` | Full Body | 3 | `full_body` | All muscle groups each session | Beginners |
| `upper_lower_4` | Upper / Lower | 4 | `upper_lower` | Upper A / Lower A / Upper B / Lower B | Intermediates |
| `ppl_6` | Push / Pull / Legs | 6 | `ppl` | Push / Pull / Legs, repeated 2x | Intermediate-Advanced |
| `arnold_6` | Arnold Split | 6 | `arnold` | Chest+Back / Shoulders+Arms / Legs, repeated 2x | Intermediate-Advanced |
| `body_part_5` | Body Part Split | 5 | `bro_split` | Chest / Back / Shoulders / Legs / Arms | Intermediate-Advanced |
| `ppl_3` | PPL (3-Day) | 3 | `ppl` | Push / Pull / Legs, once through | Intermediates |
| `phul_4` | PHUL | 4 | `upper_lower` | Upper Power / Lower Power / Upper Hypertrophy / Lower Hypertrophy | Intermediates |

### Plan Mode Lookup (Server)

A `PLAN_MODES` dict maps each key to its metadata. The server uses this to:
- Inject `split_type`, `cycle_length`, and a default `plan_name` onto the saved Plan (instead of reading these from AI output)
- Render the `{{plan_mode_description}}` block for the prompt

```python
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
```

## Architecture

### iOS Changes

#### 1. New PlanModePickerView (full screen)

- Presented when user taps "Generate" in PlanListView (replaces direct generation)
- Displays 7 cards/tiles, each showing:
  - Mode name (localized)
  - Days per cycle (e.g. "6 days/cycle")
  - Brief description (e.g. "Push / Pull / Legs, repeated twice")
  - Suited experience level subtitle
- Single-select behavior — tap to select, tap again to deselect
- "Generate Plan" button at bottom, enabled only when a mode is selected
- Loading overlay with progress indicator while generating
- On error: stay on picker, show alert with retry option
- On success: navigate to plan detail view
- If user already has an active plan, show a confirmation alert before generating ("This will replace your current plan")

#### 2. Updated API call

- `APIPlanGenerateRequest` gains a `planMode: String` field
- `APIClient.generatePlan(userId:planMode:)` updated signature

#### 3. Remove equipment from onboarding

- Remove EquipmentPickerView (tag 1) from OnboardingView's TabView
- Update step flow: ProfileSetupView (tag 0, onNext -> step 1) -> GoalPickerView (tag 1)
- Page indicator updates automatically (2 pages instead of 3)
- Keep `available_equipment` column in the User model (no migration needed)

### Server Changes

#### 1. Updated PlanGenerateRequest schema

```python
from typing import Literal

class PlanGenerateRequest(BaseModel):
    user_id: int
    plan_mode: Literal[
        "full_body_3", "upper_lower_4", "ppl_6", "arnold_6",
        "body_part_5", "ppl_3", "phul_4"
    ]
```

Invalid `plan_mode` returns 422 via Pydantic validation.

#### 2. New format_plan_profile() function

Create a **separate** function for plan generation profiles to avoid affecting chat and review endpoints:

```python
def format_plan_profile(user: User) -> str:
    return (
        f"Gender: {user.gender}, Age: {user.age}\n"
        f"Weight: {user.weight}{user.weight_unit}\n"
        f"Weight unit: {user.weight_unit}\n"
        f"Experience: {user.experience_level}\n"
        f"Goals: {user.goals}"
    )
```

The existing `format_user_profile()` remains unchanged for chat and review endpoints.

#### 3. Updated generate_plan endpoint

- Read `plan_mode` from request
- Look up mode metadata from `PLAN_MODES` dict
- Pass `plan_mode_description` to prompt rendering
- After AI returns, inject `split_type`, `cycle_length`, and `plan_name` from the lookup (do NOT read these from AI output)

#### 4. Updated validator for plan generation

The v2 validator only requires the AI to return `days` with `exercise_groups`. The server injects `plan_name`, `split_type`, and `cycle_length` from the mode lookup:

```python
def validate_plan_v2_output(data: dict) -> ValidationResult:
    errors = []
    if "days" not in data:
        errors.append("Missing required field: days")
    elif not isinstance(data["days"], list) or len(data["days"]) == 0:
        errors.append("'days' must be a non-empty list")
    else:
        for i, day in enumerate(data["days"]):
            if "exercise_groups" not in day:
                errors.append(f"Day {i + 1} missing 'exercise_groups'")
            elif not isinstance(day["exercise_groups"], list):
                errors.append(f"Day {i + 1} 'exercise_groups' must be a list")
    return ValidationResult(is_valid=len(errors) == 0, errors=errors)
```

Keep existing `validate_plan_output()` unchanged (for backwards compatibility if needed).

#### 5. New prompt v2 (plan_generation/v2.md)

The prompt template:

```
You are an expert fitness coach selecting exercises for a training program.

## User Profile
{{user_profile}}

## Plan Structure
{{plan_mode_description}}

## Instructions
The plan structure above is fixed. Your job is to select appropriate exercises and set targets for each day. Consider:
- Experience level and appropriate volume (sets per muscle group)
- Goal-appropriate rep ranges and intensity
- Per-set targets with weight, reps, and RPE
- Exercise variety between A/B days (if applicable)

## Unit System
ALL weights MUST use {{weight_unit}}. Use round numbers (5lb increments for lbs, 2.5kg increments for kg).

## Output Format
Respond with a JSON object:
{
  "days": [
    {
      "day_number": 1,
      "label": "Push A",
      "focus": "chest,shoulders,triceps",
      "exercise_groups": [
        {
          "group_type": "straight|superset|triset|circuit",
          "rest_after_group_sec": 90,
          "order": 1,
          "exercises": [
            {
              "exercise_name": "Barbell Bench Press",
              "sets": 4,
              "reps": 8,
              "rpe_target": 8.0,
              "sets_json": [
                {"set_number": 1, "target_weight": 60, "target_reps": 8, "target_rpe": 7},
                ...
              ],
              "notes": "optional coaching note"
            }
          ]
        }
      ]
    }
  ]
}

- Each day MUST match the plan structure above (same day count and muscle focus)
- Each exercise MUST include `sets_json` with per-set targets
- Be conservative with starting weights and volume for beginners
```

#### 6. Update manifest.json

Change plan_generation default from v1 to v2:

```json
{
  "plan_generation": { "default": "v2" },
  ...
}
```

### Localization

All user-facing strings (mode names, descriptions, subtitles) must support English and Simplified Chinese per project requirements.

## What Does NOT Change

- Plan storage model (Plan, PlanDay, PlanExercise, ExerciseGroup)
- Workout flow, cycle tracker, session recording
- AI provider setup, token tracking, chat, block review
- The existing `format_user_profile()` function (used by chat/review)
- The existing `validate_plan_output()` function (kept for reference)
- The `available_equipment` database column (kept, just unused)

## Data Flow

```
User taps Generate
    → PlanModePickerView (select mode)
        → [If active plan exists: confirm replacement]
        → POST /api/ai/plan/generate { user_id, plan_mode }
            → format_plan_profile() (slim: gender, age, weight, experience, goals)
            → look up PLAN_MODES[plan_mode] for description + metadata
            → render prompt v2 with plan_mode_description + user_profile
            → AI returns days with exercises/sets/reps/weights only
            → validate with validate_plan_v2_output (days + exercise_groups only)
            → inject split_type, cycle_length, plan_name from PLAN_MODES
            → store plan, return response
        → iOS receives plan, navigates to plan detail
```
