# Guided Workout Redesign Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the workout flow from freeform logging to a guided, plan-based system where all workouts follow a repeatable cycle plan.

**Architecture:** Unify plans and templates into a single "Plan" concept with cycle-based progression. Replace the freeform ActiveWorkoutView with a GuidedWorkoutView that walks users through exercises set-by-set. Add cycle tracking to automatically suggest the next workout day.

**Tech Stack:** Python/FastAPI + SQLAlchemy (server), Swift/SwiftUI + SwiftData (iOS)

**Spec:** `docs/superpowers/specs/2026-03-24-guided-workout-redesign.md`

---

## Chunk 1: Server — Data Model & Plan CRUD

### Task 1: Update Plan model for cycle-based plans

**Files:**
- Modify: `flexloop-server/src/flexloop/models/plan.py`
- Create: `flexloop-server/alembic/versions/XXXX_plan_cycle_columns.py`

- [ ] **Step 1: Add cycle_length and updated_at to Plan model**

Add `cycle_length` (Integer, default 3) and `updated_at` (DateTime) columns to the Plan model. Change `status` to default to `"active"`.

- [ ] **Step 2: Create Alembic migration**

Generate migration: `alembic revision -m "add cycle columns to plan"`
Add cycle_length (default 3), updated_at columns. Idempotent (check before adding).

- [ ] **Step 3: Update PlanExercise to use sets_json**

Replace scalar `sets`, `reps`, `weight`, `rpe_target` with `sets_json` (JSON column) storing per-set targets:
```json
[{"set_number": 1, "target_weight_kg": 80, "target_reps": 5, "target_rpe": 7},
 {"set_number": 2, "target_weight_kg": 80, "target_reps": 5, "target_rpe": 8}]
```
Keep old columns for backward compat but read from sets_json when available.

- [ ] **Step 4: Create CycleTracker model**

New model in `flexloop-server/src/flexloop/models/cycle_tracker.py`:
```python
class CycleTracker(Base):
    __tablename__ = "cycle_tracker"
    id, user_id (unique), plan_id, next_day_number (default 1), last_completed_at
```

- [ ] **Step 5: Register new model and run migration**
- [ ] **Step 6: Run tests, commit**

### Task 2: Plan CRUD endpoints

**Files:**
- Modify: `flexloop-server/src/flexloop/routers/ai.py` (plan generation)
- Create: `flexloop-server/src/flexloop/routers/plans.py` (plan CRUD)
- Modify: `flexloop-server/src/flexloop/schemas/plan.py`
- Modify: `flexloop-server/src/flexloop/main.py` (register router)
- Create: `flexloop-server/tests/test_plans.py`

- [ ] **Step 1: Write tests for plan CRUD**

Test: create plan, get plan, list plans, update plan, activate/archive, delete.

- [ ] **Step 2: Create plan schemas**

PlanCreate (name, cycle_length, days with exercises and sets_json), PlanUpdate, PlanDetailResponse.

- [ ] **Step 3: Implement plan CRUD router**

```
POST   /api/plans               — create plan manually
GET    /api/plans?user_id=X     — list plans (filter by status)
GET    /api/plans/{id}          — get with days/exercises/sets_json
PUT    /api/plans/{id}          — update (full replacement of days/exercises)
PUT    /api/plans/{id}/activate — activate (deactivate others for user)
PUT    /api/plans/{id}/archive  — set status to inactive
DELETE /api/plans/{id}          — delete
```

- [ ] **Step 4: Run tests, commit**

### Task 3: Cycle tracking endpoints

**Files:**
- Create: `flexloop-server/src/flexloop/routers/cycle.py`
- Create: `flexloop-server/tests/test_cycle.py`

- [ ] **Step 1: Write tests for cycle tracking**

Test: get next workout (returns day details), complete workout (advances cycle, wraps around).

- [ ] **Step 2: Implement cycle endpoints**

```
GET  /api/users/{id}/next-workout   — returns next_day_number + plan day with exercises
POST /api/users/{id}/complete-workout — advances to next day (wraps at cycle_length)
```

- [ ] **Step 3: Run tests, commit**

### Task 4: Update AI plan generation for cycles

**Files:**
- Modify: `flexloop-server/prompts/plan_generation/v1.md`
- Modify: `flexloop-server/src/flexloop/routers/ai.py` (generate_plan endpoint)

- [ ] **Step 1: Update plan generation prompt**

Change from "Generate a 6-week training block" to "Generate a repeating training cycle of N days". Output cycle_length instead of block_weeks/block_start/block_end. Each exercise outputs sets_json with per-set targets.

- [ ] **Step 2: Update generate_plan endpoint**

Save plan with cycle_length, sets_json per exercise. Set status="active" and deactivate other plans. Create/update CycleTracker for user.

- [ ] **Step 3: Run all server tests, commit**

### Task 5: Remove template endpoints

**Files:**
- Delete: `flexloop-server/src/flexloop/routers/templates.py`
- Modify: `flexloop-server/src/flexloop/main.py` (remove router)
- Modify: `flexloop-server/tests/` (remove template tests)

- [ ] **Step 1: Remove template router and tests**
- [ ] **Step 2: Run tests, commit**

### Task 6: Update workout endpoints

**Files:**
- Modify: `flexloop-server/src/flexloop/routers/workouts.py`
- Modify: `flexloop-server/src/flexloop/schemas/workout.py`

- [ ] **Step 1: Add set edit endpoint**

`PUT /api/workouts/{id}/sets/{set_id}` — update weight_kg, reps, rpe on existing set.

- [ ] **Step 2: Remove template_id from workout creation**

WorkoutSessionCreate no longer accepts template_id. Source is always "plan".

- [ ] **Step 3: Run tests, commit**

---

## Chunk 2: iOS — Plan Management & Editing

### Task 7: Update iOS data models

**Files:**
- Modify: `flexloop-ios/FlexLoop/FlexLoop/Models/CachedPlan.swift`
- Modify: `flexloop-ios/FlexLoop/FlexLoop/Services/APIModels.swift`
- Modify: `flexloop-ios/FlexLoop/FlexLoop/Services/APIClient.swift`

- [ ] **Step 1: Update CachedPlan for cycle model**

Add cycleLength, remove blockStart/blockEnd. Add status field.

- [ ] **Step 2: Update API models**

New plan CRUD request/response models. Update APIPlanExercise to include setsJson array. Add cycle tracker models. Remove template models.

- [ ] **Step 3: Add plan CRUD methods to APIClient**

fetchPlans, createPlan, updatePlan, activatePlan, archivePlan, deletePlan, fetchNextWorkout, completeWorkout.

- [ ] **Step 4: Build, commit**

### Task 8: Plan list & management view

**Files:**
- Rewrite: `flexloop-ios/FlexLoop/FlexLoop/Views/Plan/PlanView.swift`
- Create: `flexloop-ios/FlexLoop/FlexLoop/Views/Plan/PlanListView.swift`
- Create: `flexloop-ios/FlexLoop/FlexLoop/ViewModels/PlanListViewModel.swift`

- [ ] **Step 1: Create PlanListViewModel**

Loads all plans, supports activate/archive/delete. Tracks active plan.

- [ ] **Step 2: Create PlanListView**

Shows active plan prominently, archived plans below. Activate/archive/delete actions.

- [ ] **Step 3: Rewrite PlanView as plan detail + editor**

Shows plan days with exercises. Full editing: tap exercise to edit weight/RPE/sets. Add/remove exercises. Add/remove days. Reorder via drag. "Generate with AI" button creates new active plan.

- [ ] **Step 4: Build, commit**

### Task 9: Plan editor views

**Files:**
- Create: `flexloop-ios/FlexLoop/FlexLoop/Views/Plan/PlanDayEditView.swift`
- Create: `flexloop-ios/FlexLoop/FlexLoop/Views/Plan/PlanExerciseEditView.swift`

- [ ] **Step 1: PlanDayEditView**

Edit day label, focus. List exercises with inline editing. Add exercise from library. Reorder. Delete.

- [ ] **Step 2: PlanExerciseEditView**

Edit per-set targets (weight, reps, RPE). Add/remove sets. Notes field.

- [ ] **Step 3: Build, commit**

---

## Chunk 3: iOS — Guided Workout View

### Task 10: GuidedWorkoutView — core structure

**Files:**
- Create: `flexloop-ios/FlexLoop/FlexLoop/Views/Workout/GuidedWorkoutView.swift`
- Create: `flexloop-ios/FlexLoop/FlexLoop/ViewModels/GuidedWorkoutViewModel.swift`

- [ ] **Step 1: GuidedWorkoutViewModel**

State: current exercise index, planned exercises list, completed sets per exercise, rest timer. Methods: completeSet, skipExercise, reorderExercise, editCompletedSet, finishWorkout.

- [ ] **Step 2: GuidedWorkoutView layout**

Top: exercise name + progress (e.g. "Exercise 2 of 5"). Middle: planned sets for current exercise — each row shows target weight/reps/RPE with "Done" button or editable fields. Bottom: "Next Exercise" / "Finish Workout" buttons. Support skip and reorder via menu.

- [ ] **Step 3: Build, commit**

### Task 11: Per-set completion flow

**Files:**
- Modify: `flexloop-ios/FlexLoop/FlexLoop/Views/Workout/GuidedWorkoutView.swift`

- [ ] **Step 1: Set row UI**

Each planned set shows: target weight (editable), target reps (editable), target RPE. User can adjust, then tap checkmark to mark done. Completed sets show actual values with green checkmark. Tap completed set to edit.

- [ ] **Step 2: Rest timer integration**

Auto-start rest timer after completing a set. Show timer between sets.

- [ ] **Step 3: Warm-up integration**

"Generate Warm-Up" button before first working set. Warm-up sets appear above working sets.

- [ ] **Step 4: Build, commit**

### Task 12: Exercise navigation & reorder

**Files:**
- Modify: `flexloop-ios/FlexLoop/FlexLoop/Views/Workout/GuidedWorkoutView.swift`

- [ ] **Step 1: Next/Previous exercise**

"Next Exercise" advances to next planned exercise. "Previous" goes back. Progress indicator updates.

- [ ] **Step 2: Skip exercise**

Menu action to skip current exercise (marks as skipped in record).

- [ ] **Step 3: Exercise list sidebar**

Swipe or tap to see all exercises for the day. Tap to jump to any. Drag to reorder.

- [ ] **Step 4: Build, commit**

### Task 13: Workout completion & recording

**Files:**
- Modify: `flexloop-ios/FlexLoop/FlexLoop/ViewModels/GuidedWorkoutViewModel.swift`

- [ ] **Step 1: Save workout record**

On finish: save all completed sets to SwiftData + sync to server. Link to plan_day_id. Advance cycle tracker via API.

- [ ] **Step 2: PR detection**

Check PRs after each completed set (existing logic).

- [ ] **Step 3: Post-workout summary**

Show summary: exercises completed, total sets, any PRs. Then dismiss.

- [ ] **Step 4: Build, commit**

---

## Chunk 4: iOS — Home Tab & Cleanup

### Task 14: Redesign Home tab

**Files:**
- Rewrite: `flexloop-ios/FlexLoop/FlexLoop/Views/Home/HomeView.swift`
- Create: `flexloop-ios/FlexLoop/FlexLoop/Views/Home/CalendarView.swift`
- Modify: `flexloop-ios/FlexLoop/FlexLoop/ViewModels/HomeViewModel.swift`

- [ ] **Step 1: HomeViewModel updates**

Load next workout day from cycle tracker API. Load workout history for calendar.

- [ ] **Step 2: Home tab — next workout card**

Shows: "Next: Day 2 — Upper B" with exercise preview and prominent "Start Workout" button. Tapping launches GuidedWorkoutView with that day's plan.

- [ ] **Step 3: CalendarView**

Monthly calendar grid. Days with workouts highlighted. Tap for detail. Shows gap awareness.

- [ ] **Step 4: Build, commit**

### Task 15: Update tab bar & remove dead code

**Files:**
- Modify: `flexloop-ios/FlexLoop/FlexLoop/ContentView.swift`
- Delete: `flexloop-ios/FlexLoop/FlexLoop/Views/Templates/TemplatesListView.swift`
- Delete: `flexloop-ios/FlexLoop/FlexLoop/Views/Templates/CreateTemplateView.swift`
- Delete: `flexloop-ios/FlexLoop/FlexLoop/Views/Workout/WorkoutTabView.swift`
- Delete: `flexloop-ios/FlexLoop/FlexLoop/Views/Workout/ActiveWorkoutView.swift`
- Delete: `flexloop-ios/FlexLoop/FlexLoop/ViewModels/TemplatesViewModel.swift`
- Delete: `flexloop-ios/FlexLoop/FlexLoop/ViewModels/ActiveWorkoutViewModel.swift`

- [ ] **Step 1: Update ContentView tab bar**

```
[Home]  [Plan]  [Progress]  [AI Coach]  [Settings]
```

Remove Workout tab. Remove templates from navigation.

- [ ] **Step 2: Delete template files**

Remove TemplatesListView, CreateTemplateView, TemplatesViewModel.

- [ ] **Step 3: Delete old workout files**

Remove ActiveWorkoutView, WorkoutTabView, ActiveWorkoutViewModel (replaced by GuidedWorkout*).

- [ ] **Step 4: Update Home "My Templates" button to removed**

HomeView no longer has templates shortcut.

- [ ] **Step 5: Build, fix any remaining references, commit**

### Task 16: Update localization

**Files:**
- Modify: `flexloop-ios/FlexLoop/FlexLoop/Resources/Localizable.xcstrings`

- [ ] **Step 1: Add new localization keys**

Add English + Chinese keys for: guided workout UI, plan editor, calendar, cycle tracking.

- [ ] **Step 2: Remove unused keys**

Remove template-related and ad-hoc workout keys.

- [ ] **Step 3: Build, commit**

### Task 17: Update smoke test checklist

**Files:**
- Modify: `docs/smoke-test-checklist.md`

- [ ] **Step 1: Rewrite smoke test for new flow**

Update all workout sections to reflect guided flow. Remove template tests. Add plan CRUD tests, cycle tracking tests, calendar tests.

- [ ] **Step 2: Commit**
