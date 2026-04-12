# FlexLoop Smoke Test Checklist

**Date:** ___________
**Tester:** ___________
**Backend version:** flexloop-server (105 tests)
**iOS version:** flexloop-ios
**Device:** iPhone _________ / Watch _________
**iOS version:** ___________

---

## Pre-Test Setup

- [ ] Backend server running: `cd flexloop-server && source .venv/bin/activate && uvicorn flexloop.main:app --host 0.0.0.0 --port 8000`
- [ ] Exercise library seeded: `python scripts/seed_exercises.py`
- [ ] Exercise details seeded: `python scripts/seed_exercise_details.py`
- [ ] `.env` configured with LLM provider credentials
- [ ] iOS app installed on device/simulator
- [ ] Backend health check passes: `curl http://localhost:8000/api/health` → `{"status":"ok"}`
- [ ] API docs accessible: `http://localhost:8000/docs` loads Swagger UI

---

## 1. Backend API (curl or Swagger UI)

### 1.1 Health & Infrastructure
- [ ] `GET /api/health` returns `{"status":"ok","version":"1.0.0"}`
- [ ] `GET /docs` shows Swagger UI with all endpoints listed

### 1.2 Profiles
- [ ] `POST /api/profiles` — create a user with all fields (name, gender, age, height, weight, experience, goals, equipment)
- [ ] `GET /api/profiles/{id}` — returns the created user
- [ ] `PUT /api/profiles/{id}` — update weight → verify new value returned, other fields preserved
- [ ] `GET /api/profiles/999` — returns 404

### 1.3 Exercise Library
- [ ] `GET /api/exercises` — returns 81 exercises with total count
- [ ] `GET /api/exercises?muscle_group=chest` — returns only chest exercises
- [ ] `GET /api/exercises?equipment=bodyweight` — returns only bodyweight exercises
- [ ] `GET /api/exercises?q=squat` — search by name returns matching exercises
- [ ] `GET /api/exercises/{id}` — returns single exercise with metadata_json
- [ ] `GET /api/exercises/999` — returns 404

### 1.4 Plan CRUD
- [ ] `POST /api/plans` — create plan with name, split_type, cycle_length, days with exercises and sets_json
- [ ] `GET /api/plans?user_id={id}` — returns plan list with total count
- [ ] `GET /api/plans?user_id={id}&status=active` — filters by status
- [ ] `GET /api/plans/{id}` — returns plan with days, exercise groups, exercises, sets_json
- [ ] `PUT /api/plans/{id}` — update name → verify changed
- [ ] `PUT /api/plans/{id}` — update days (full replacement) → verify new days returned
- [ ] `PUT /api/plans/{id}/activate` — activates plan, deactivates others for user
- [ ] `PUT /api/plans/{id}/archive` — sets status to inactive
- [ ] `DELETE /api/plans/{id}` — delete → `GET` returns 404

### 1.5 Cycle Tracking
- [ ] `GET /api/users/{id}/next-workout` — returns next day number, plan day with exercises
- [ ] `POST /api/users/{id}/complete-workout` — advances to next day
- [ ] Complete all days in cycle → wraps back to day 1
- [ ] `GET /api/users/{id}/next-workout` with no tracker → returns 404

### 1.6 Workout Sessions
- [ ] `POST /api/workouts` — create session with `user_id`, `plan_day_id`, `source: "plan"`
- [ ] `PUT /api/workouts/{id}` — add 3 sets with weight/reps/RPE → verify sets in response
- [ ] `PUT /api/workouts/{id}` — set `completed_at` → verify timestamp saved
- [ ] `PUT /api/workouts/{id}/sets/{set_id}` — edit set weight/reps/rpe → verify updated
- [ ] `GET /api/workouts/{id}` — returns session with all sets and feedback
- [ ] `GET /api/users/{id}/workouts` — returns list of user's sessions
- [ ] `POST /api/workouts/{id}/feedback` — submit sleep_quality, energy_level → verify saved

### 1.7 PR Detection
- [ ] `POST /api/workouts/{id}/check-pr` — first set for an exercise → creates initial PR records
- [ ] `POST /api/workouts/{id}/check-pr` — heavier set → returns `new_prs` with estimated_1rm type
- [ ] `POST /api/workouts/{id}/check-pr` — lighter set → returns empty `new_prs`
- [ ] `GET /api/users/{id}/prs` — returns all PRs for user
- [ ] `GET /api/exercises/{id}/prs` — returns PRs for specific exercise

### 1.8 Measurements
- [ ] `POST /api/measurements` — create waist measurement with date, value_cm, notes
- [ ] `GET /api/users/{id}/measurements` — returns list
- [ ] `GET /api/users/{id}/measurements?type=waist` — filtered by type

### 1.9 Data Export
- [ ] `GET /api/export?user_id={id}&format=json` — returns full export
- [ ] `GET /api/export/session/{id}` — returns single session with sets
- [ ] `GET /api/export/session/999` — returns 404

### 1.10 Sync
- [ ] `POST /api/sync` — push 2 workouts with sets → returns `workouts_synced: 2`
- [ ] Verify synced workouts appear in `GET /api/users/{id}/workouts`

### 1.11 Backup & Restore
- [ ] `POST /api/backup` — creates backup → returns filename and size
- [ ] `GET /api/backups` — returns list of backups
- [ ] `POST /api/restore/{filename}` — restore from backup

### 1.12 AI Plan Generation
- [ ] `POST /api/ai/plan/generate` with `user_id` → returns `status: "success"` with cycle_length
- [ ] Verify plan has days with exercises and sets_json per exercise
- [ ] Verify cycle tracker created (next-workout endpoint works after generation)
- [ ] Verify previous plans deactivated

### 1.13 AI Chat
- [ ] `POST /api/ai/chat` with `user_id` and `message` → returns reply
- [ ] Verify reply references user's actual training data

### 1.14 AI Review
- [ ] `POST /api/ai/review` with `user_id` (must have logged workouts) → returns review with suggestions

### 1.15 AI Usage
- [ ] `GET /api/ai/usage?user_id={id}` — returns monthly usage with token counts

### 1.16 Warm-Up Generator
- [ ] `GET /api/warmup/{exercise_id}?working_weight=100` → returns ascending warm-up sets
- [ ] `GET /api/warmup/{exercise_id}?working_weight=15` (isolation) → returns empty list

### 1.17 Deload Detection
- [ ] `GET /api/deload/{user_id}/check` — returns fatigue report with signals and recommendation

### 1.18 Progress
- [ ] `GET /api/progress/{user_id}/estimated-1rm` — returns 1RM data points per exercise
- [ ] `GET /api/progress/{user_id}/volume` — returns weekly sets per muscle group

---

## 2. iOS App — Onboarding

### 2.1 Fresh Install
- [ ] App launches to onboarding (not main tab view)
- [ ] Step 1 (Profile): name, gender, age, height, weight, experience, days per week
- [ ] Step 2 (Equipment): all options visible, tap toggles selection
- [ ] Step 3 (Goals): goal picker, "Create Profile & Generate Plan" button
- [ ] Tapping create submits to backend → transitions to main tab view

### 2.2 Returning User
- [ ] App launches directly to main tab view (skips onboarding)

---

## 3. iOS App — Home Tab

- [ ] Weekly session count shows correctly with flame icon
- [ ] **Next workout card** shows when active plan exists:
  - [ ] Day number and label (e.g. "Day 2: Upper B")
  - [ ] Plan name and cycle position (e.g. "2/3")
  - [ ] Exercise preview (up to 4 exercises with sets/reps)
  - [ ] "+N more" text when more than 4 exercises
  - [ ] "Start Workout" button launches GuidedWorkoutView
- [ ] **No plan card** shows when no active plan ("Go to Plan tab...")
- [ ] Recent sessions list shows up to 5 recent workouts
- [ ] Deload alert banner appears when backend recommends deload
- [ ] After completing a guided workout, next workout card updates to next day

---

## 4. iOS App — Guided Workout

### 4.1 Starting a Workout
- [ ] Launched from Home "Start Workout" button
- [ ] Shows plan day label as navigation title
- [ ] Progress bar and "Exercise X of Y" shown at top

### 4.2 Per-Set Completion
- [ ] Each exercise shows target sets with weight/reps/RPE columns
- [ ] Values pre-filled from plan's sets_json targets
- [ ] Weight and reps fields are editable before completing
- [ ] Tapping circle checkmark marks set as done (turns green)
- [ ] Haptic feedback on set completion
- [ ] Completed set row has green tint
- [ ] Tapping green checkmark enables editing of completed set
- [ ] After completing a set, edit weight/reps/RPE → tap checkmark again to save

### 4.3 Rest Timer
- [ ] Auto-starts after completing a set (120s default)
- [ ] Displays countdown in mm:ss format
- [ ] "Skip" button stops timer
- [ ] Text turns red when <= 10 seconds
- [ ] Haptic notification when timer completes

### 4.4 Exercise Navigation
- [ ] "Next Exercise" button advances to next exercise
- [ ] "Finish Workout" shows on last exercise (green button)
- [ ] Left/right chevron buttons navigate between exercises
- [ ] Previous button disabled on first exercise, next on last
- [ ] Menu → "Skip Exercise" skips current and advances
- [ ] Menu → "Exercise List" opens sidebar sheet

### 4.5 Exercise List Sidebar
- [ ] Shows all exercises with status icons (circle, checkmark, forward)
- [ ] Current exercise has "CURRENT" badge
- [ ] Shows completion count per exercise (e.g. "2/3")
- [ ] Tapping an exercise jumps to it
- [ ] Edit mode enables drag to reorder
- [ ] Skipped exercises show strikethrough

### 4.6 PR Detection
- [ ] PR alert appears when new PR detected
- [ ] Success haptic fires
- [ ] PR check doesn't block workout if backend unreachable

### 4.7 Completing Workout
- [ ] "Finish Workout" saves all completed sets to SwiftData
- [ ] Post-workout summary shows:
  - [ ] Trophy icon
  - [ ] "Workout Complete!" title
  - [ ] Exercises completed count
  - [ ] Total sets count
  - [ ] Duration
  - [ ] Skipped count (if any)
  - [ ] New PRs count (if any)
- [ ] "Done" dismisses summary and returns to Home
- [ ] Cycle tracker advances (next-workout shows next day)

---

## 5. iOS App — Plan Tab

### 5.1 Plan List
- [ ] Active plan shown prominently in "Active Plan" section
- [ ] Archived plans in separate "Archived" section
- [ ] Swipe right on archived plan → "Activate" action
- [ ] Swipe left on active plan → "Archive" action
- [ ] Swipe left on archived plan → "Delete" action
- [ ] Tapping a plan navigates to plan detail

### 5.2 Plan Detail
- [ ] Shows plan name, split type, cycle length
- [ ] AI Generated badge for AI-generated plans
- [ ] Day cards with exercises, sets/reps, RPE targets
- [ ] Coaching notes visible per exercise

### 5.3 Generating Plan
- [ ] Toolbar sparkles button triggers AI generation
- [ ] Loading overlay with "AI is generating your plan..."
- [ ] Generated plan appears in list as active
- [ ] Previous active plan automatically archived

### 5.4 Empty State
- [ ] "No Plans" with "Generate Plan" button

---

## 6. iOS App — Progress Tab

### 6.1 Segmented Control
- [ ] Three segments: Strength, Volume, History
- [ ] Tapping each switches content

### 6.2 Strength Charts
- [ ] Line chart per exercise showing estimated 1RM over time
- [ ] Empty state when no data

### 6.3 Volume Chart
- [ ] Weekly sets per muscle group
- [ ] Empty state when no data

### 6.4 History
- [ ] Sessions grouped by month with date, source, set count
- [ ] Sync status indicator
- [ ] Tapping session opens detail view
- [ ] Empty state: "No Workouts Yet"

---

## 7. iOS App — AI Coach Tab

- [ ] Chat input with send button
- [ ] User messages (blue, right), AI responses (gray, left)
- [ ] "Thinking..." spinner while waiting
- [ ] Auto-scrolls to latest message
- [ ] Error message if backend unreachable

---

## 8. iOS App — Settings Tab

### 8.1 Server Configuration
- [ ] Server URL editable
- [ ] "Test Connection" with spinner, green/red result

### 8.2 Units
- [ ] Weight Unit picker: Metric (kg) / Imperial (lbs)
- [ ] Changing unit applies to all weight displays

### 8.3 Toggles
- [ ] Post-session feedback toggle (default: off)
- [ ] Measurement reminders toggle (default: off)

### 8.4 About
- [ ] Version shows "1.0.0"

---

## 9. iOS App — Sync

- [ ] Auto-sync triggers on app foreground
- [ ] Unsynced sessions show indicator in history
- [ ] After sync, indicator disappears
- [ ] Sync failure doesn't crash the app

---

## 10. Apple Watch App

### 10.1 Home Screen
- [ ] Shows today's workout label
- [ ] Green "Start" button
- [ ] Fallback message when no plan synced

### 10.2 Workout & Rest Timer
- [ ] Exercise name, set counter, weight via digital crown
- [ ] Rest timer after each set with haptic on completion

---

## 11. Localization (Chinese)

**Change device language to 简体中文, then verify:**

- [ ] Tab labels: 首页, 计划, 进度, AI教练, 设置
- [ ] Home: 本周, X 次训练, 下次训练, 开始训练, 最近训练
- [ ] Guided Workout: 下一个动作, 完成训练, 跳过动作, 动作列表, 训练完成！, 训练总结
- [ ] Plan: 我的计划, 当前计划, 已归档, 启用, 归档, AI生成, 暂无计划
- [ ] Plan Editor: 训练日信息, 动作, 添加动作, 每组目标, 备注
- [ ] Progress: 力量, 容量, 历史
- [ ] AI Coach: AI教练, 问问你的训练..., 思考中...
- [ ] Settings: 设置, 后端服务器, 重量单位, 公制 (kg), 英制 (lbs)

---

## 12. Unit Conversion (lbs mode)

**Set weight unit to Imperial (lbs) in Settings, then verify:**

- [ ] Guided workout: weight targets and inputs in lbs
- [ ] Plan day cards: weights in lbs
- [ ] Progress charts: 1RM values in lbs

---

## 13. Edge Cases & Error Handling

- [ ] Backend offline: workout logging still works (offline mode)
- [ ] Backend offline: AI Coach shows error message, doesn't crash
- [ ] Backend offline: Plan tab shows error, doesn't crash
- [ ] Backend offline: sync queues data for later
- [ ] Zero weight set: logging works (bodyweight exercises)
- [ ] Rapid set logging: no duplicate sets
- [ ] Kill and restart app: data persists, onboarding not shown again

---

## Test Results Summary

| Area | Pass | Fail | Notes |
|------|------|------|-------|
| Backend API | /19 | | |
| Onboarding | /2 | | |
| Home | /8 | | |
| Guided Workout | /22 | | |
| Plan | /8 | | |
| Progress | /6 | | |
| AI Coach | /5 | | |
| Settings | /5 | | |
| Sync | /4 | | |
| Watch | /4 | | |
| Localization | /7 | | |
| Unit Conversion | /3 | | |
| Edge Cases | /7 | | |
| **Total** | **/100** | | |
