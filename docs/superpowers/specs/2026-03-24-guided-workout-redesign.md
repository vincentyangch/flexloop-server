# Guided Workout Redesign — Design Spec

## Problem

The current app has three disconnected concepts (plan, template, ad-hoc workout) and a freeform workout logger. This doesn't serve FlexLoop's core thesis: **Plan → Record → Feedback → Plan**. Users generate a plan but can't easily follow it. The workout flow is unstructured and doesn't guide users through their planned exercises.

## Design Decisions (from user discussion)

1. **No ad-hoc workouts.** All workouts follow a plan.
2. **No templates.** Plans are the only concept. Users can save/archive plans.
3. **Plan = repeatable cycle** of 1-6 days, not a fixed date range.
4. **One active plan** at a time, with archived inactive plans.
5. **Guided workout** — exercise-by-exercise, set-by-set, with pre-filled targets.
6. **No auto-progression** — weights stay fixed until user or AI updates the plan.
7. **Plan is fully editable** before starting a workout.
8. **Completed sets are editable** during workout (correct mistakes).
9. **Exercises are reorderable/skippable** during workout.
10. **Cycle tracking** — app suggests next day, user trains when ready.
11. **Calendar view** — shows workout history for self-awareness, not enforcement.

## Data Model

### Plan (server: `plans` table)

```
Plan
  id, user_id, name, split_type
  cycle_length: int (1-6)
  status: "active" | "inactive"
  ai_generated: bool
  created_at, updated_at
```

**Remove:** `block_start`, `block_end`, `block_weeks` — no fixed date ranges.
**Add:** `cycle_length`, `updated_at`.
**Change:** `status` from free text to enum `active`/`inactive`.

### PlanDay (server: `plan_days` table)

No changes. `day_number` (1..N) represents position in cycle.

### PlanExercise (server: `plan_exercises` table)

```
PlanExercise
  id, plan_day_id, exercise_group_id, exercise_id, order
  sets_json: [{ set_number, target_weight_kg, target_reps, target_rpe }]
  notes
```

**Change:** Replace scalar `sets`/`reps`/`weight`/`rpe_target` with `sets_json` array. Each set can have different target weight and RPE, matching how real programs work (e.g., pyramid sets, drop sets).

### WorkoutSession (server: `workout_sessions` table)

```
WorkoutSession
  id, user_id, plan_day_id
  started_at, completed_at, notes
```

**Remove:** `template_id`, `source` (always "plan" now).

### WorkoutSet (server: `workout_sets` table)

No structural changes. Each logged set has `exercise_id`, `set_number`, `weight_kg`, `reps`, `rpe`, `set_type`.

### CycleTracker (server: `cycle_tracker` table — new)

```
CycleTracker
  id, user_id, plan_id
  next_day_number: int (1..cycle_length)
  last_completed_at: datetime
```

One row per user. Updated after each workout completion.

## API Changes

### New/Modified Endpoints

```
# Plan CRUD (replaces template endpoints)
GET    /api/plans?user_id=X              — list all plans (active + inactive)
GET    /api/plans/{id}                   — get plan with all days/exercises
POST   /api/plans                        — create plan manually
PUT    /api/plans/{id}                   — update plan (name, exercises, days)
PUT    /api/plans/{id}/activate          — set as active plan (deactivates others)
PUT    /api/plans/{id}/archive           — archive a plan
DELETE /api/plans/{id}                   — delete plan

# AI plan generation (modified)
POST   /api/ai/plan/generate             — generate cycle-based plan

# Cycle tracking
GET    /api/users/{id}/next-workout      — returns next day number + plan day details
POST   /api/users/{id}/complete-workout  — advances cycle, saves workout

# Workout (simplified)
POST   /api/workouts                     — create session (always linked to plan_day_id)
PUT    /api/workouts/{id}                — update sets, completed_at
PUT    /api/workouts/{id}/sets/{set_id}  — edit a completed set
```

### Removed Endpoints

```
DELETE  /api/templates/*                 — all template endpoints
```

## iOS Changes

### Removed Files
- `Views/Templates/TemplatesListView.swift`
- `Views/Templates/CreateTemplateView.swift`
- `Views/Workout/WorkoutTabView.swift` (merged into Home)
- `ViewModels/TemplatesViewModel.swift`

### New/Modified Views

**HomeView** — Shows next workout day from cycle, calendar view of past workouts, "Start Today's Workout" button.

**PlanView** — View/edit active plan. Create new plan manually. Generate with AI. Manage archived plans. Full editing: add/remove/reorder days, exercises, sets. Edit target weight/reps/RPE per set.

**GuidedWorkoutView** (replaces ActiveWorkoutView) — Exercise-by-exercise progression. Shows current exercise with all planned sets. Per-set completion (tap "Done" or adjust then "Done"). Next/previous exercise navigation. Skip exercise. Reorder. Edit completed sets. Rest timer between sets.

**CalendarView** — Monthly calendar showing which days had workouts. Tap date for detail.

### Tab Bar (simplified)

```
[Home]  [Plan]  [Progress]  [AI Coach]  [Settings]
```

Remove Workout tab (workout launches from Home). Remove Templates from More.

## AI Prompt Changes

Plan generation prompt changes from:
- "Generate a 6-week training block with start/end dates"

To:
- "Generate a repeating training cycle of N days for this user"
- Output: cycle_length, days array with exercises and per-set targets
- No block_start/block_end/block_weeks

## Migration Strategy

1. Existing plans get `cycle_length` set from number of days, `status` set to "active"
2. Existing templates are deleted (data loss acceptable — smoke test data only)
3. `block_start`/`block_end` columns kept but ignored (no destructive migration)
4. WorkoutSession.source defaults to "plan", template_id set to null
