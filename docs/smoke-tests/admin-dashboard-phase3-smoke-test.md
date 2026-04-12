# Phase 3 (Plans editor) smoke test

> **Automated Playwright smoke executed 2026-04-08 — all checks ✅.** Script at
> `/tmp/smoke_phase3.py` (headless chromium) covers: login, plans list, create/edit/delete
> plan, navigate to detail page, add day via dialog, add exercise group, add exercise,
> "Use per-set targets", save day, persistence across reload, **cross-day draft fix**
> (open two days, edit both, save Day 1, verify Day 2's unsaved edits survive), delete
> day, cascade delete of plan, and iOS-facing `GET /api/plans?user_id=1` regression check.
> The manual checklist below remains the definitive acceptance spec; the automated run
> covers the critical path but leaves visual/JSON-escape-hatch items to manual verification
> if needed.

Manual checklist. Each item is either ✅ or ❌ — do not mark anything "partial".
Re-run from the top after fixing any failure.

## Environment

- [ ] Backend running: `uv run uvicorn flexloop.main:app --port 8000`
- [ ] Admin UI built and served from the backend: `cd admin-ui && npm run build`
- [ ] Logged in as an admin user at http://localhost:8000/admin
- [ ] There's at least one `User` row in the DB and at least two `Exercise` rows with known IDs (needed for the day-editor test).

## Plans list page

- [ ] Navigate to /admin/plans — sidebar entry is enabled and the page loads
- [ ] Empty state: DataTable says "No plans" when the table is empty
- [ ] Click "New plan" — EditSheet opens with the PlanForm
- [ ] Fill in user_id, name, split type, cycle length, status=active, submit — toast says "Plan created" and the row appears in the table
- [ ] Click the "Edit" button on the new row — EditSheet opens pre-populated
- [ ] Change the name, submit — toast says "Plan updated" and the row updates
- [ ] Filter by status=archived — table is empty
- [ ] Filter by user_id=1 — only plans owned by user 1 show
- [ ] Search for part of a name — only matching plans show
- [ ] Sort by name asc/desc — order changes
- [ ] Open the EditSheet, switch to the "JSON" tab, verify the plan JSON is shown; edit a metadata field (e.g. `"name": "JSON-edited"`), Save — toast success, list refreshes
- [ ] In the JSON tab, try adding a `"days": []` field and saving — should get a 422 error toast (`extra forbidden` for the `days` field)

## Plan detail page — day editor

- [ ] From the list, click "Open" on a plan — navigates to /admin/plans/:id
- [ ] Empty plan: shows "No days yet. Add one to start building the plan."
- [ ] Click "+ Add day" — dialog opens
- [ ] Enter day_number=1, label="Upper A", submit — toast "Day added", an accordion row appears
- [ ] Click the accordion header — expands to show the editor
- [ ] Edit the day's label and focus fields — no API call yet (draft)
- [ ] Click "+ Add exercise group" — a GroupEditor appears
- [ ] In the group, edit group_type, order, rest_after_group_sec
- [ ] Click "+ Add exercise to group" — an ExerciseEditor appears
- [ ] Fill in exercise_id (use a real Exercise id), order, sets=4, reps=8, weight=100, rpe=7.5
- [ ] Click "Use per-set targets" in the set targets grid — 4 rows appear
- [ ] Edit one of the set rows' weight
- [ ] Click "Save day" — toast "Day saved", the accordion re-renders with the fetched data, new set row values are present

## Atomic replacement semantics

- [ ] With the same day expanded, delete the exercise, click Save day — the exercise is gone server-side
- [ ] Add a different exercise, Save — only the new one is present (the old one was not orphaned)
- [ ] Verify via the API: `curl -b cookies.txt http://localhost:8000/api/admin/plans/1` shows one exercise under the day

## Duplicate day + conflict handling

- [ ] Try to add another day with the SAME day_number as an existing one — toast shows 409 error from the backend
- [ ] Add a second day with a different day_number — succeeds

## Delete day + cascade

- [ ] Delete a day (click "Delete day", confirm the browser prompt) — toast, accordion removes the day
- [ ] Verify via API that the day's groups and exercises are also gone (no orphans)

## Delete plan + cascade

- [ ] Back on the list, delete a plan with at least 2 days — confirm dialog warns about cascade, confirm
- [ ] Verify via API that the plan, its days, groups, and exercises are all gone (SELECT COUNT from each table)

## Regression — existing routes still work

- [ ] /admin/ dashboard still loads
- [ ] /admin/workouts list still loads
- [ ] /admin/users list still loads
- [ ] iOS-facing `GET /api/plans?user_id=1` still works (returns the same shape as before)

## Test suite

- [ ] `uv run pytest -q` — full suite green (expected +~30 tests over phase 2's baseline)
- [ ] `cd admin-ui && npm run build` — succeeds with no TS errors
