# Admin Dashboard — Phase 2 Smoke Test

Run before merging `feat/admin-dashboard-phase2` to main, and after deploying to the VPS.

**Prerequisites**
- Server running: `uv run uvicorn flexloop.main:app --port 8000`
- Admin UI built: `cd admin-ui && npm run build`
- You are logged in to `/admin` as a phase 1 admin user.

## Backend (automated)
- [x] `uv run pytest -v` — all passing (phase 1 tests + ~40 new phase 2 tests)
- [x] `curl -s http://127.0.0.1:8000/openapi.json | jq '.paths | keys | map(select(startswith("/api/admin/")))' | wc -l` returns 21 (phase 1 = 7 + phase 2 = 14)

## Authentication
- [x] Visit `/admin/users` while logged out → redirected to `/admin/login`
- [x] Log in, visit `/admin/users` → page loads

## Users page
- [x] Table loads with pagination controls (if ≥1 user exists)
- [x] Click a sortable column header (Name, ID, Age) — rows reorder and arrow icon flips
- [x] Click the header again — direction flips to descending
- [x] Click a third time — sort clears, default order restored
- [x] Type in the search box — table filters after keystrokes; page resets to 1
- [x] Click "New user", submit a valid form → row appears in list, toast shows "User created"
- [x] Click "Edit" on the new row → sheet opens with pre-filled values
- [x] Change a field, save → toast shows "User updated", row reflects change
- [x] Click "Edit" again, switch to "JSON" tab → raw row visible; `goals` is editable; save → toast shows "User updated via JSON"
- [x] Click "Delete" → confirm dialog appears with "This cannot be undone."
- [x] Confirm delete → toast "User deleted", row disappears

## Workouts page
- [x] Table loads
- [x] Completed filter: switch between All / Completed / In progress → counts update
- [x] Create a new workout with no completed_at → appears as "In progress" badge
- [x] Edit the same row, set completed_at in the past → badge flips to "Completed"
- [x] Sets column shows 0 for a session with no sets
- [x] Delete a workout with ≥1 set → delete dialog shows the child-count message

## Measurements page
- [x] Create a weight measurement → appears
- [x] Filter by type=weight via query param (`?filter[type]=weight`) — direct URL visit → only weight rows
- [x] Edit → save, delete → remove

## Personal Records page
- [x] Create a PR with pr_type=max_weight → appears
- [x] Edit the value → persists
- [x] Delete → gone

## Exercises page
- [x] List loads with existing plugin-seeded exercises
- [x] Search for "squat" → filters to squat variants
- [x] Create a new exercise → appears
- [x] Edit the `metadata_json` via the JSON tab → persists

## AI Usage page
- [x] List loads (may be empty on a fresh install)
- [x] Create a row for month=2026-04 with some tokens → appears
- [x] Edit and save → persists
- [x] Delete → gone

## Admin Users page
- [x] List shows at least the current admin
- [x] Create another admin with username="test_admin2", password="testpass8" → appears
- [x] Log out, log in as `test_admin2` → succeeds, `last_login_at` visible on that row
- [x] Log back in as original admin
- [x] Edit test_admin2, set is_active=false → row reflects inactive badge
- [x] Try to delete the currently-logged-in admin → 400 error surfaces as toast, row remains
- [x] Delete `test_admin2` → succeeds

## Cross-cutting
- [x] All write requests in devtools → Network include an `Origin` header and the session cookie
- [x] Reloading any page keeps state (React Router doesn't break on refresh)
- [x] Sidebar items for Plans, AI Config/Prompts/Playground, Operations remain disabled (grayed out / non-clickable) — phase 3+ placeholders
- [x] No errors in browser console on any page
- [x] `/api/admin/health` still works and the Dashboard landing page from phase 1 still loads

## Result
- [x] **PASS** — ready to merge to main
- [ ] **FAIL** — fix issues listed below and re-run the whole checklist

## Run notes (2026-04-08)

Driven via headless Chromium (Playwright) against `http://localhost:8000` with the rebuilt `admin-ui` static bundle. **34/34 automated checks passed.** Two expected console errors observed:
- 1× `401 Unauthorized` — initial logged-out probe of `/api/admin/auth/me` from the `AuthGate` redirect test
- 1× `400 Bad Request` — backend response for the Admin Users self-delete guard

### Issues fixed during the run

One environment fix and five real bugs were caught and patched before the green pass:

0. **Stale built bundle** *(environment, not a code bug)* — `src/flexloop/static/admin/` had pre-phase-2 assets from the deleted worktree (the dir is gitignored). Rebuilding (`cd admin-ui && npm run build`) regenerated the bundle with all phase 2 routes.
1. **Measurements edit 422** — `MeasurementsPage.tsx` spread `user_id` into the PUT payload; `MeasurementAdminUpdate` uses `extra="forbid"` and rejected it. Fix: strip `user_id` in the page's edit handler.
2. **Workouts edit 422** — same `user_id` leak in `WorkoutsPage.tsx`. Fix: strip in edit handler.
3. **PRs edit 422** — same `user_id` leak in `PRsPage.tsx`. Fix: strip in edit handler.
4. **AI Usage edit 422** — `AIUsagePage.tsx` leaked both `user_id` and `month` (the latter is also create-only on the AIUsage rollup table). Fix: strip both in edit handler.
5. **PRForm session_id silent submit failure** — `z.coerce.number().int().positive().nullable().optional()` doesn't handle empty `<input type="number">` correctly: empty input → coerced to `0` → `.positive()` fails → form silently rejects submit (no toast, no network call). Fix: `z.preprocess` to coerce `""`/`null`/`undefined` to `null` before validation.

All five code fixes apply the same lesson the earlier `UserForm.available_equipment_csv` reviewer caught: **never assume the form's emit shape matches the backend Update schema**. With `extra="forbid"` everywhere, every page-level edit handler must explicitly destructure out the create-only fields.
