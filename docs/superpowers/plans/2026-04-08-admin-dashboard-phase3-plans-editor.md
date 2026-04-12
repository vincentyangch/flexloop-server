# Admin Dashboard — Phase 3 (Plans Editor) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the admin Plans editor — the one resource that breaks generic CRUD. End state: an operator can list all Plans in the database, create a new empty Plan, edit Plan metadata (name, split type, cycle length, status, block dates), and **hand-edit any AI-generated plan's day/group/exercise/set structure** via a dedicated detail page with per-day accordions and inline editing.

**Architecture:** Two layers of endpoints:
1. **Standard 5-endpoint CRUD** for Plan metadata (`list`, `detail`, `create`, `update`, `delete`) — reuses phase-2's `flexloop.admin.crud` helpers and `flexloop.admin.schemas.common`. Mirrors the workouts/users/etc. router shape exactly.
2. **Three day-level endpoints** for the nested Plan → PlanDay → ExerciseGroup → PlanExercise → sets_json structure (`POST/PUT/DELETE /plans/{id}/days[/{day_number}]`). A day is the atomic save unit per spec §9.3: PUT replaces an entire day's groups + exercises + sets in one transaction; no "save the whole plan" button.

Frontend has two pages: a list page that reuses the shared `<DataTable>` + `<EditSheet>` shape from phase 2, and a **plan detail page** (`/plans/:id`) with per-day collapsible sections, inline group/exercise/set forms, and a per-day "Save day" button. The detail page's `useMutation` calls the day endpoints directly — no shared `useCrud` hook is sufficient for this one.

**Tech Stack (new to phase 3):** No new backend dependencies. Frontend adds one shadcn/ui component: `accordion`. Everything else reuses phase 2 infrastructure (`react-hook-form`, `zod`, `@tanstack/react-query`, `sonner`, generated `api.types.ts`).

**Spec reference:** `docs/superpowers/specs/2026-04-06-admin-dashboard-design.md`. Read §9.1 (CRUD UX baseline), §9.2 (Plans filter list — user, status), §9.3 (Plan editor special case — this is the authoritative UI spec), §9.4 (JSON escape hatch), §14 phase 3 bullet, §17 acceptance criterion 3.

**Phase 1 and Phase 2 already delivered** (do not redo or rework): admin auth, CSRF middleware, Vite+React shell, 7 resource pages + 7 admin routers, shared `<DataTable>/<EditSheet>/<DeleteDialog>/<JsonEditor>`, `useCrud.ts` hooks, `openapi-typescript` codegen. See `docs/superpowers/plans/2026-04-07-admin-dashboard-phase2-crud.md`. The sidebar already has a disabled "Plans" entry at `/plans` — this phase only flips `disabled: true` → removes the flag.

**Phase 4 (AI tools) and Phase 5 (Operations) are out of scope.** The `app_settings` DB-backed config migration, prompt editor, AI playground, backup/logs/triggers — none of it touches phase 3.

---

## Decisions locked in for this phase

These choices are fixed before implementation starts. Do not re-litigate them mid-execution — if a decision turns out to be wrong, stop and ask the user.

1. **Resource scope:** only `Plan`. Everything else (Users, Workouts, etc.) already ships in phase 2. The `PlanDay`, `ExerciseGroup`, `PlanExercise` tables are edited **through** the Plan resource, not as top-level admin resources. No `/api/admin/plan-days` or `/api/admin/exercise-groups` routers — they would proliferate without adding value.

2. **Endpoint surface (8 total):**
   ```
   GET    /api/admin/plans                                  list
   GET    /api/admin/plans/{plan_id}                        detail (nested days embedded)
   POST   /api/admin/plans                                  create (metadata only — no days)
   PUT    /api/admin/plans/{plan_id}                        update (metadata only — no days)
   DELETE /api/admin/plans/{plan_id}                        delete (cascade deletes days/groups/exercises)
   POST   /api/admin/plans/{plan_id}/days                   add a new day (full nested payload)
   PUT    /api/admin/plans/{plan_id}/days/{day_number}      replace entire day (groups + exercises + sets)
   DELETE /api/admin/plans/{plan_id}/days/{day_number}      delete a day
   ```

3. **`POST /plans` creates an empty plan** (metadata only — no `days` field in the payload). Rationale: the spec §9.3 shows days being added via `[+ Add day]` inside the Plan detail page, and the `POST /plans/{id}/days` endpoint exists for exactly that. Having `POST /plans` accept nested days AND `POST /plans/{id}/days` both work would create two ways to do the same thing. Keep it one way: metadata first, then days. This also matches how the AI-generation path in `flexloop.routers.plans` works (the iOS-facing router is separate and unaffected).

4. **`PUT /plans/{id}` touches metadata only.** It does NOT accept a `days` field. To edit day contents, use the day endpoints. The iOS-facing `PUT /api/plans/{id}` router accepts nested days; the admin router deliberately diverges. This is the simplification that makes the JSON escape hatch safe — if an admin pastes a full Plan JSON and submits it via `PUT /plans/{id}`, the `extra="forbid"` config rejects the `days` field with a clear 422, not a silent partial update. (The detail page uses the day endpoints for day edits, so the JSON hatch is still usable for metadata.)

5. **`PUT /plans/{id}/days/{day_number}` replaces the entire day atomically.** The payload carries the full nested structure: `{label, focus, exercise_groups: [...]}`. The handler clears the day's `exercise_groups` and `exercises` collections (relying on `cascade="all, delete-orphan"` already set on the model), then recreates them from the payload. `day_number` cannot be changed via this endpoint — it is the stable identifier in the URL. Reordering days is not in scope for phase 3; the spec's §9.3 layout doesn't show drag-handles for days, and `day_number` can be manually changed via the JSON escape hatch if someone really needs it.

6. **`POST /plans/{id}/days` rejects duplicate `day_number`.** If a day with the same `day_number` already exists on the plan, respond 409 with `{detail: "day_number N already exists on this plan"}`. No auto-renumbering; the admin must delete the old day first. This keeps the semantics transparent.

7. **Filters (per spec §9.2):** `filter[user_id]=N`, `filter[status]=active|inactive|archived`. Sort columns whitelist: `id`, `name`, `created_at`, `updated_at`, `user_id`, `status`. Default sort: `created_at desc` (most recent plans first). Search: ILIKE on `plan.name`.

8. **Cascade-delete on `DELETE /plans/{id}`.** No "x days will be deleted" preview — the confirm dialog just shows "Delete plan `{name}`? This will also delete all days, groups, exercises, and set targets. This cannot be undone." Since `PlanDay → ExerciseGroup → PlanExercise` all have `cascade="all, delete-orphan"`, a single `db.delete(plan)` removes the whole tree. Verify this in a test.

9. **No drag-and-drop.** Group and exercise reordering happens by editing the `order` field directly on the inline form. Adding drag-and-drop reordering is explicitly punted to a post-v1 enhancement. The spec §9.3 does not mandate drag-and-drop; the `[edit] [del]` buttons per row are sufficient.

10. **Strict schemas.** Every `*AdminCreate`, `*AdminUpdate`, and day-payload schema MUST include `model_config = ConfigDict(extra="forbid")`. Response schemas use `ConfigDict(from_attributes=True)`. This is the phase-2 convention — do not relax it.

11. **Audit-log writes are still DEFERRED to phase 4.** Phase 3 does not write to `admin_audit_log`. Matches phase 2.

12. **Frontend test coverage: none added in phase 3.** Backend gets rigorous pytest coverage; frontend gets a manual smoke checklist. Matches phase 1 and phase 2.

13. **Detail page route:** `/plans/:id` (under the `/admin` basename, so the full URL is `/admin/plans/:id`). Clicking a row in the list page navigates to the detail page via `useNavigate()`. An "Open" button on each row provides the same navigation — this is clearer than "Edit" (which other resources use to open an EditSheet). The list page's EditSheet is still used for creating a new empty plan and for editing plan metadata inline without leaving the list.

14. **JSON escape hatch scope:** enabled at the **plan-metadata level** (via the list page's EditSheet "JSON" tab, which already exists in phase 2). Editing a full `PlanResponse` JSON blob with nested days through the escape hatch is NOT supported because `PUT /plans/{id}` rejects `days`. If an admin needs that, they can call the day endpoints directly or edit via the detail page. Documented in the smoke test.

15. **Worktree + feature branch (per branch-strategy memory):**
    - Worktree path: `/Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase3`
    - Branch: `feat/admin-dashboard-phase3`
    - Merge strategy at the end: fast-forward into `main`, then delete branch + worktree, then bump the parent submodule pointer in `FlexLoop`.

---

## File Structure

All paths relative to `flexloop-server/` unless stated otherwise.

**Backend — new:**
```
src/flexloop/admin/
├── schemas/
│   └── plans.py                  NEW — Plan/Day/Group/Exercise admin schemas
└── routers/
    └── plans.py                  NEW — 8-endpoint admin plans router
```

**Backend — modified:**
```
src/flexloop/main.py              add `admin_plans_router` import + include_router
```

**Backend — tests:**
```
tests/
├── test_admin_plans.py           NEW — standard CRUD tests (list/detail/create/update/delete)
└── test_admin_plans_days.py      NEW — day endpoint tests (POST/PUT/DELETE /days[/{day_number}])
```

> Two test files rather than one because the day endpoints have very different fixtures (they need pre-seeded exercises) and the CRUD-vs-day split makes the test files each stay under ~400 lines. Matches the phase-2 convention of one `test_admin_<resource>.py` per router; the day endpoints get their own file since they're a second endpoint group on the same router.

**Frontend — new:**
```
admin-ui/src/
├── pages/
│   ├── PlansPage.tsx             NEW — list page (DataTable + EditSheet, matches phase 2 pattern)
│   └── PlanDetailPage.tsx        NEW — per-day accordion editor (unique to phase 3)
├── components/
│   ├── forms/
│   │   └── PlanForm.tsx          NEW — hand-written rhf+zod form for plan metadata
│   └── plan-editor/              NEW — sub-components used only by PlanDetailPage
│       ├── DayAccordion.tsx      NEW — single-day collapsible with Save button
│       ├── GroupEditor.tsx       NEW — one ExerciseGroup row inside a day
│       ├── ExerciseEditor.tsx    NEW — one PlanExercise row inside a group
│       └── SetTargetsGrid.tsx    NEW — editable weight/reps/rpe grid for sets_json
└── components/ui/
    └── accordion.tsx             NEW — shadcn add
```

> `plan-editor/` is its own folder because none of the sub-components are reusable outside the Plan editor. Bundling them together keeps the top-level `components/` directory from becoming a dumping ground.

**Frontend — modified:**
```
admin-ui/src/
├── App.tsx                       add `/plans` and `/plans/:id` routes
├── components/AppSidebar.tsx     remove `disabled: true` from the Plans item
└── lib/api.types.ts              regenerated from the updated OpenAPI schema
```

**Docs:**
```
docs/admin-dashboard-phase3-smoke-test.md    NEW — manual smoke checklist
```

---

## Execution setup

Run these commands once before starting Chunk 1. All subsequent file paths are relative to the worktree.

```bash
cd /Users/flyingchickens/Projects/FlexLoop/flexloop-server
git worktree add /Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase3 -b feat/admin-dashboard-phase3
cd /Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase3
uv sync
cd admin-ui && npm install && cd ..
```

Verify baseline before touching anything:

```bash
uv run pytest -q
```

Expected: all tests pass (300+ passing — 195 from phase 1 + 105 added in phase 2). If anything is red on `main`, stop and ask the user.

```bash
cd admin-ui && npm run build && cd ..
```

Expected: Vite build succeeds, bundle written to `src/flexloop/static/admin/`.

---

## Chunk 1: Backend — Plans CRUD schemas and standard router

This chunk delivers the 5-endpoint standard CRUD (list/detail/create/update/delete) for Plans. The day endpoints come in Chunk 2. At the end of this chunk, you can `curl` `GET /api/admin/plans`, create an empty plan via `POST`, and verify the JSON shape matches the nested response structure. Tests cover the happy paths plus auth, validation, filtering, and the cascade delete.

### Task 1: Create `flexloop.admin.schemas.plans`

**Files:**
- Create: `src/flexloop/admin/schemas/plans.py`

This file defines the Pydantic schemas for the admin Plans resource. Four response schemas (one per nesting level) + two plan-level write schemas + three day-level write schemas (used by Chunk 2, but defined here so they live with their siblings).

- [ ] **Step 1: Create the file with the plan-level schemas**

```python
"""Admin CRUD schemas for Plan and its nested relations.

The Plan resource is nested four levels deep (Plan → PlanDay → ExerciseGroup
→ PlanExercise, with an optional sets_json blob inside each exercise). This
file defines:

- Response schemas — one per level, from leaf to root, so Pydantic's
  forward-refs are satisfied naturally.
- PlanAdminCreate / PlanAdminUpdate — metadata-only write schemas. The admin
  router deliberately refuses nested days on these endpoints; day edits go
  through POST/PUT/DELETE /api/admin/plans/{id}/days endpoints.
- PlanDayAdminCreate (and its nested ExerciseGroupAdminCreate,
  PlanExerciseAdminCreate, SetTargetAdmin) — used by the day endpoints in
  Chunk 2. They are defined here to keep all plan-shaped schemas in one
  file.

All write schemas use ``extra="forbid"`` to reject typos at validation time.
All response schemas use ``from_attributes=True`` so they read directly off
SQLAlchemy ORM rows.
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


# --- Response schemas (leaf → root) -----------------------------------------


class PlanExerciseAdminResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    exercise_id: int
    exercise_group_id: int
    order: int
    sets: int
    reps: int
    weight: float | None
    rpe_target: float | None
    sets_json: list[dict] | None
    notes: str | None


class ExerciseGroupAdminResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    group_type: str
    order: int
    rest_after_group_sec: int
    exercises: list[PlanExerciseAdminResponse] = Field(default_factory=list)


class PlanDayAdminResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    day_number: int
    label: str
    focus: str
    exercise_groups: list[ExerciseGroupAdminResponse] = Field(default_factory=list)


class PlanAdminResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    split_type: str
    cycle_length: int
    block_start: date | None
    block_end: date | None
    status: str
    ai_generated: bool
    created_at: datetime
    updated_at: datetime | None
    days: list[PlanDayAdminResponse] = Field(default_factory=list)


# --- Plan-level write schemas -----------------------------------------------


class PlanAdminCreate(BaseModel):
    """POST /api/admin/plans — metadata only. Days are added via
    POST /api/admin/plans/{id}/days after the plan exists.
    """
    model_config = ConfigDict(extra="forbid")

    user_id: int
    name: str
    split_type: str = "custom"
    cycle_length: int = 3
    block_start: date | None = None
    block_end: date | None = None
    status: str = "active"
    ai_generated: bool = False


class PlanAdminUpdate(BaseModel):
    """PUT /api/admin/plans/{id} — metadata only. ``days`` is deliberately
    NOT a field here, so submitting a payload that includes a ``days`` key
    returns 422 (thanks to ``extra="forbid"``). Day edits go through the
    dedicated day endpoints.
    """
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    split_type: str | None = None
    cycle_length: int | None = None
    block_start: date | None = None
    block_end: date | None = None
    status: str | None = None
    ai_generated: bool | None = None


# --- Day-level write schemas (used by Chunk 2) -------------------------------


class SetTargetAdmin(BaseModel):
    """One row inside PlanExercise.sets_json. Stored as a JSON blob on the
    PlanExercise row; not its own table.
    """
    model_config = ConfigDict(extra="forbid")

    set_number: int
    target_weight: float | None = None
    target_reps: int = 10
    target_rpe: float | None = None


class PlanExerciseAdminCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exercise_id: int
    order: int = 1
    sets: int = 3
    reps: int = 10
    weight: float | None = None
    rpe_target: float | None = None
    sets_json: list[SetTargetAdmin] | None = None
    notes: str | None = None


class ExerciseGroupAdminCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_type: str = "straight"
    order: int = 1
    rest_after_group_sec: int = 90
    exercises: list[PlanExerciseAdminCreate] = Field(default_factory=list)


class PlanDayAdminCreate(BaseModel):
    """POST /api/admin/plans/{plan_id}/days — full nested day payload."""
    model_config = ConfigDict(extra="forbid")

    day_number: int
    label: str
    focus: str = ""
    exercise_groups: list[ExerciseGroupAdminCreate] = Field(default_factory=list)


class PlanDayAdminUpdate(BaseModel):
    """PUT /api/admin/plans/{plan_id}/days/{day_number} — replace entire day.

    ``day_number`` is NOT a field — it's fixed by the URL path. Only label,
    focus, and the nested groups/exercises are mutable.
    """
    model_config = ConfigDict(extra="forbid")

    label: str | None = None
    focus: str | None = None
    exercise_groups: list[ExerciseGroupAdminCreate] = Field(default_factory=list)
```

- [ ] **Step 2: Verify the file imports cleanly**

```bash
uv run python -c "from flexloop.admin.schemas.plans import PlanAdminResponse, PlanAdminCreate, PlanAdminUpdate, PlanDayAdminCreate, PlanDayAdminUpdate, ExerciseGroupAdminCreate, PlanExerciseAdminCreate, SetTargetAdmin; print('ok')"
```

Expected: `ok`. If there's an ImportError or Pydantic validation error at class-definition time, fix before moving on.

- [ ] **Step 3: Commit**

```bash
git add src/flexloop/admin/schemas/plans.py
git commit -m "feat(admin): add plan admin schemas (response + write + day payloads)"
```

---

### Task 2: Write failing tests for `GET /api/admin/plans` (list + auth + empty)

**Files:**
- Create: `tests/test_admin_plans.py`

Mirror the structure of `tests/test_admin_workouts.py`. Start with the auth + empty-list smoke before adding the happy paths — this way we know the router is mounted before writing richer assertions.

- [ ] **Step 1: Write the failing tests**

```python
"""Integration tests for /api/admin/plans (standard CRUD endpoints).

Day-level endpoints (POST/PUT/DELETE /days[/{day_number}]) are covered in
test_admin_plans_days.py to keep this file focused on the CRUD surface.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import SESSION_COOKIE_NAME, create_session, hash_password
from flexloop.models.admin_user import AdminUser
from flexloop.models.plan import ExerciseGroup, Plan, PlanDay, PlanExercise
from flexloop.models.user import User


async def _make_admin_and_cookie(db: AsyncSession) -> dict[str, str]:
    admin = AdminUser(username="tester", password_hash=hash_password("password123"))
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    token, _ = await create_session(db, admin_user_id=admin.id)
    return {SESSION_COOKIE_NAME: token}


async def _make_user(db: AsyncSession) -> User:
    user = User(
        name="Plan Owner", gender="other", age=30, height=180, weight=80,
        weight_unit="kg", height_unit="cm", experience_level="intermediate",
        goals="", available_equipment=[],
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _make_plan(
    db: AsyncSession,
    *,
    user_id: int,
    name: str = "Test Plan",
    status: str = "active",
) -> Plan:
    plan = Plan(
        user_id=user_id,
        name=name,
        split_type="upper_lower",
        cycle_length=4,
        status=status,
        ai_generated=False,
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return plan


class TestListPlans:
    async def test_requires_auth(self, client: AsyncClient) -> None:
        assert (await client.get("/api/admin/plans")).status_code == 401

    async def test_empty_list(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.get("/api/admin/plans", cookies=cookies)
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 0
        assert body["items"] == []
        assert body["page"] == 1

    async def test_lists_plans_with_embedded_days(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        user = await _make_user(db_session)
        plan = await _make_plan(db_session, user_id=user.id, name="Upper / Lower")
        # Add a day with an empty group so the eager-load path is exercised.
        day = PlanDay(plan_id=plan.id, day_number=1, label="Upper A", focus="chest, back")
        db_session.add(day)
        await db_session.commit()

        res = await client.get("/api/admin/plans", cookies=cookies)
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 1
        item = body["items"][0]
        assert item["id"] == plan.id
        assert item["user_id"] == user.id
        assert item["name"] == "Upper / Lower"
        assert len(item["days"]) == 1
        assert item["days"][0]["day_number"] == 1
        assert item["days"][0]["label"] == "Upper A"
        assert item["days"][0]["exercise_groups"] == []

    async def test_filter_by_user_id(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        u1 = await _make_user(db_session)
        u2 = User(
            name="Other", gender="other", age=25, height=170, weight=70,
            weight_unit="kg", height_unit="cm", experience_level="beginner",
            goals="", available_equipment=[],
        )
        db_session.add(u2)
        await db_session.commit()
        await db_session.refresh(u2)
        await _make_plan(db_session, user_id=u1.id, name="P1")
        await _make_plan(db_session, user_id=u2.id, name="P2")

        res = await client.get(
            f"/api/admin/plans?filter[user_id]={u1.id}", cookies=cookies
        )
        assert res.status_code == 200
        assert res.json()["total"] == 1
        assert res.json()["items"][0]["name"] == "P1"

    async def test_filter_by_status(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        user = await _make_user(db_session)
        await _make_plan(db_session, user_id=user.id, name="Active one", status="active")
        await _make_plan(db_session, user_id=user.id, name="Archived one", status="archived")

        res = await client.get(
            "/api/admin/plans?filter[status]=archived", cookies=cookies
        )
        assert res.status_code == 200
        assert res.json()["total"] == 1
        assert res.json()["items"][0]["name"] == "Archived one"

    async def test_rejects_unknown_filter(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.get(
            "/api/admin/plans?filter[nonexistent]=x", cookies=cookies
        )
        assert res.status_code == 400

    async def test_search_on_name(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        user = await _make_user(db_session)
        await _make_plan(db_session, user_id=user.id, name="Hypertrophy Block")
        await _make_plan(db_session, user_id=user.id, name="Strength Block")

        res = await client.get(
            "/api/admin/plans?search=hypertrophy", cookies=cookies
        )
        assert res.status_code == 200
        assert res.json()["total"] == 1
        assert res.json()["items"][0]["name"] == "Hypertrophy Block"
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
uv run pytest tests/test_admin_plans.py -v
```

Expected: all tests fail with `404 Not Found` (router isn't mounted yet). If any test errors at collection time (syntax/import), fix first.

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_admin_plans.py
git commit -m "test(admin): failing list tests for /api/admin/plans"
```

---

### Task 3: Implement `list_plans` — just enough to make the list tests pass

**Files:**
- Create: `src/flexloop/admin/routers/plans.py`
- Modify: `src/flexloop/main.py`

Model this router on `tests/test_admin_workouts.py` → `src/flexloop/admin/routers/workouts.py`. The notable differences: three levels of `selectinload` nesting (days → groups → exercises), and the filter whitelist includes `user_id` + `status` only.

- [ ] **Step 1: Write the minimal router file**

```python
"""Admin CRUD endpoints for ``Plan`` plus nested day endpoints.

This router has two endpoint groups on the same prefix:

1. Standard 5-endpoint CRUD (list, detail, create, update, delete) that
   reuses ``flexloop.admin.crud`` helpers, matching every other admin
   resource router.
2. Three day-level endpoints (POST/PUT/DELETE /plans/{id}/days[/{N}]) that
   treat a single ``PlanDay`` as the atomic save unit per spec §9.3.

Day endpoints are added in a later task — this commit only wires up the
standard CRUD surface.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from flexloop.admin.auth import require_admin
from flexloop.admin.crud import (
    paginated_response,
    parse_filter_params,
    parse_sort_spec,
)
from flexloop.admin.schemas.common import ListQueryParams, PaginatedResponse
from flexloop.admin.schemas.plans import (
    PlanAdminCreate,
    PlanAdminResponse,
    PlanAdminUpdate,
)
from flexloop.db.engine import get_session
from flexloop.models.plan import ExerciseGroup, Plan, PlanDay

router = APIRouter(prefix="/api/admin/plans", tags=["admin:plans"])

ALLOWED_SORT_COLUMNS = {"id", "name", "created_at", "updated_at", "user_id", "status"}
ALLOWED_FILTER_COLUMNS = {"user_id", "status"}


def _plan_query():
    """Base SELECT with the full nested eager-load chain.

    Three levels deep: Plan → PlanDay.exercise_groups → ExerciseGroup.exercises.
    Every endpoint that returns a PlanAdminResponse must go through this so
    the Pydantic serializer never triggers lazy IO inside the async request.
    """
    return select(Plan).options(
        selectinload(Plan.days)
        .selectinload(PlanDay.exercise_groups)
        .selectinload(ExerciseGroup.exercises)
    )


@router.get("", response_model=PaginatedResponse[PlanAdminResponse])
async def list_plans(
    request: Request,
    params: ListQueryParams = Depends(ListQueryParams.as_dependency),
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> dict:
    query = _plan_query()

    # Filters — plain equality on whitelisted columns.
    filters = parse_filter_params(request.query_params, allowed=ALLOWED_FILTER_COLUMNS)
    for key, value in filters.items():
        query = query.where(getattr(Plan, key) == value)

    # Search — single-column ILIKE on name.
    if params.search:
        like = f"%{params.search}%"
        query = query.where(Plan.name.ilike(like))

    # Sort — default to newest first.
    sort_clauses = parse_sort_spec(
        params.sort, model=Plan, allowed=ALLOWED_SORT_COLUMNS
    )
    if sort_clauses:
        query = query.order_by(*sort_clauses)
    else:
        query = query.order_by(Plan.created_at.desc())

    return await paginated_response(
        db,
        query=query,
        item_schema=PlanAdminResponse,
        page=params.page,
        per_page=params.per_page,
    )
```

- [ ] **Step 2: Mount the router in `main.py`**

Open `src/flexloop/main.py`. Find the block of admin imports (around line 19-27) and add an alphabetically-placed import:

```python
from flexloop.admin.routers.plans import router as admin_plans_router
```

Then find the block of `include_router` calls (around line 81-89) and add:

```python
app.include_router(admin_plans_router)
```

Place it next to the other admin `include_router` lines — alphabetical ordering matches the existing style.

- [ ] **Step 3: Run the list tests to verify they pass**

```bash
uv run pytest tests/test_admin_plans.py::TestListPlans -v
```

Expected: all 7 list tests pass. If any fail, read the actual vs expected and fix the router before committing. Do NOT skip a failing assertion.

- [ ] **Step 4: Verify nothing else regressed**

```bash
uv run pytest -q
```

Expected: full test suite green. If any unrelated test fails, stop and investigate.

- [ ] **Step 5: Commit**

```bash
git add src/flexloop/admin/routers/plans.py src/flexloop/main.py
git commit -m "feat(admin): implement GET /api/admin/plans list endpoint"
```

---

### Task 4: Detail endpoint — `GET /api/admin/plans/{plan_id}`

**Files:**
- Modify: `src/flexloop/admin/routers/plans.py`
- Modify: `tests/test_admin_plans.py`

- [ ] **Step 1: Write the failing detail tests**

Append to `tests/test_admin_plans.py` (after `TestListPlans`):

```python
class TestGetPlan:
    async def test_requires_auth(self, client: AsyncClient) -> None:
        assert (await client.get("/api/admin/plans/1")).status_code == 401

    async def test_returns_404_for_missing(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.get("/api/admin/plans/9999", cookies=cookies)
        assert res.status_code == 404

    async def test_returns_plan_with_nested_days(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        user = await _make_user(db_session)
        plan = await _make_plan(db_session, user_id=user.id)
        day = PlanDay(plan_id=plan.id, day_number=1, label="Day 1", focus="full body")
        db_session.add(day)
        await db_session.commit()
        await db_session.refresh(day)

        res = await client.get(f"/api/admin/plans/{plan.id}", cookies=cookies)
        assert res.status_code == 200
        body = res.json()
        assert body["id"] == plan.id
        assert body["name"] == "Test Plan"
        assert len(body["days"]) == 1
        assert body["days"][0]["day_number"] == 1
```

- [ ] **Step 2: Run them to verify they fail**

```bash
uv run pytest tests/test_admin_plans.py::TestGetPlan -v
```

Expected: 2 pass (auth + missing), but `test_returns_plan_with_nested_days` fails — no `get_plan` endpoint exists. Actually all three may 404 depending on routing. Any test that fails with "plan not found on get" means we need to add the endpoint.

Wait — the auth and 404 tests SHOULD both fail, because neither endpoint exists yet. The auth test specifically expects 401, but an unmounted route returns 404 ( which is wrong status code ).

Re-read the expected: `assert ... == 401` for auth, `== 404` for missing. FastAPI routes that don't exist return 404, not 401. The `test_requires_auth` test will FAIL (it gets 404 but expects 401) until the endpoint exists.

Expected: all 3 tests fail until the detail endpoint is added.

- [ ] **Step 3: Implement the detail endpoint**

Append to `src/flexloop/admin/routers/plans.py`:

```python
@router.get("/{plan_id}", response_model=PlanAdminResponse)
async def get_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> Plan:
    result = await db.execute(_plan_query().where(Plan.id == plan_id))
    plan = result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="plan not found",
        )
    return plan
```

- [ ] **Step 4: Run the tests**

```bash
uv run pytest tests/test_admin_plans.py::TestGetPlan -v
```

Expected: all 3 pass.

- [ ] **Step 5: Commit**

```bash
git add src/flexloop/admin/routers/plans.py tests/test_admin_plans.py
git commit -m "feat(admin): GET /api/admin/plans/{id} detail endpoint"
```

---

### Task 5: Create endpoint — `POST /api/admin/plans`

**Files:**
- Modify: `src/flexloop/admin/routers/plans.py`
- Modify: `tests/test_admin_plans.py`

- [ ] **Step 1: Write the failing create tests**

Append to `tests/test_admin_plans.py`:

```python
class TestCreatePlan:
    async def test_requires_auth(self, client: AsyncClient) -> None:
        res = await client.post("/api/admin/plans", json={"user_id": 1, "name": "x"})
        assert res.status_code == 401

    async def test_creates_empty_plan(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        user = await _make_user(db_session)
        res = await client.post(
            "/api/admin/plans",
            json={
                "user_id": user.id,
                "name": "New Plan",
                "split_type": "upper_lower",
                "cycle_length": 4,
            },
            cookies=cookies,
        )
        assert res.status_code == 201
        body = res.json()
        assert body["name"] == "New Plan"
        assert body["split_type"] == "upper_lower"
        assert body["cycle_length"] == 4
        assert body["status"] == "active"
        assert body["days"] == []

    async def test_rejects_unknown_field(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        user = await _make_user(db_session)
        res = await client.post(
            "/api/admin/plans",
            json={
                "user_id": user.id,
                "name": "New Plan",
                "days": [],  # not allowed on create — use day endpoints instead
            },
            cookies=cookies,
        )
        assert res.status_code == 422

    async def test_rejects_missing_required_fields(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        # name is required
        res = await client.post(
            "/api/admin/plans", json={"user_id": 1}, cookies=cookies
        )
        assert res.status_code == 422
```

- [ ] **Step 2: Run them to verify they fail**

```bash
uv run pytest tests/test_admin_plans.py::TestCreatePlan -v
```

Expected: `test_requires_auth` and `test_creates_empty_plan` fail with 405/404 (no POST yet). The 422 tests might pass accidentally — that's fine, keep them.

- [ ] **Step 3: Implement the create endpoint**

Append to `src/flexloop/admin/routers/plans.py`:

```python
@router.post(
    "",
    response_model=PlanAdminResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_plan(
    payload: PlanAdminCreate,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> Plan:
    plan = Plan(**payload.model_dump())
    db.add(plan)
    await db.commit()
    # Refresh with the full eager-load so the response matches the detail
    # endpoint's shape (empty days list populated, timestamps filled in).
    result = await db.execute(_plan_query().where(Plan.id == plan.id))
    return result.scalar_one()
```

- [ ] **Step 4: Run the tests**

```bash
uv run pytest tests/test_admin_plans.py::TestCreatePlan -v
```

Expected: all 4 pass.

- [ ] **Step 5: Commit**

```bash
git add src/flexloop/admin/routers/plans.py tests/test_admin_plans.py
git commit -m "feat(admin): POST /api/admin/plans create endpoint"
```

---

### Task 6: Update endpoint — `PUT /api/admin/plans/{plan_id}`

**Files:**
- Modify: `src/flexloop/admin/routers/plans.py`
- Modify: `tests/test_admin_plans.py`

- [ ] **Step 1: Write the failing update tests**

Append to `tests/test_admin_plans.py`:

```python
class TestUpdatePlan:
    async def test_requires_auth(self, client: AsyncClient) -> None:
        res = await client.put("/api/admin/plans/1", json={"name": "x"})
        assert res.status_code == 401

    async def test_404_for_missing(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.put(
            "/api/admin/plans/9999", json={"name": "x"}, cookies=cookies
        )
        assert res.status_code == 404

    async def test_partial_update(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        user = await _make_user(db_session)
        plan = await _make_plan(db_session, user_id=user.id, name="Old Name")
        res = await client.put(
            f"/api/admin/plans/{plan.id}",
            json={"name": "New Name", "status": "archived"},
            cookies=cookies,
        )
        assert res.status_code == 200
        body = res.json()
        assert body["name"] == "New Name"
        assert body["status"] == "archived"
        # Unrelated fields untouched.
        assert body["split_type"] == "upper_lower"
        assert body["cycle_length"] == 4

    async def test_rejects_days_field(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """The admin update schema deliberately doesn't accept ``days`` —
        day edits go through the dedicated day endpoints. A typo like
        passing a nested plan JSON should 422, not silently drop the field.
        """
        cookies = await _make_admin_and_cookie(db_session)
        user = await _make_user(db_session)
        plan = await _make_plan(db_session, user_id=user.id)
        res = await client.put(
            f"/api/admin/plans/{plan.id}",
            json={"name": "x", "days": []},
            cookies=cookies,
        )
        assert res.status_code == 422
```

- [ ] **Step 2: Run them to verify they fail**

```bash
uv run pytest tests/test_admin_plans.py::TestUpdatePlan -v
```

Expected: all 4 fail.

- [ ] **Step 3: Implement the update endpoint**

Append to `src/flexloop/admin/routers/plans.py`:

```python
@router.put("/{plan_id}", response_model=PlanAdminResponse)
async def update_plan(
    plan_id: int,
    payload: PlanAdminUpdate,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> Plan:
    result = await db.execute(select(Plan).where(Plan.id == plan_id))
    plan = result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="plan not found",
        )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(plan, field, value)

    await db.commit()
    result = await db.execute(_plan_query().where(Plan.id == plan.id))
    return result.scalar_one()
```

- [ ] **Step 4: Run the tests**

```bash
uv run pytest tests/test_admin_plans.py::TestUpdatePlan -v
```

Expected: all 4 pass.

- [ ] **Step 5: Commit**

```bash
git add src/flexloop/admin/routers/plans.py tests/test_admin_plans.py
git commit -m "feat(admin): PUT /api/admin/plans/{id} update endpoint (metadata only)"
```

---

### Task 7: Delete endpoint — `DELETE /api/admin/plans/{plan_id}` (cascade-verified)

**Files:**
- Modify: `src/flexloop/admin/routers/plans.py`
- Modify: `tests/test_admin_plans.py`

- [ ] **Step 1: Write the failing delete tests**

Append to `tests/test_admin_plans.py`:

```python
class TestDeletePlan:
    async def test_requires_auth(self, client: AsyncClient) -> None:
        assert (await client.delete("/api/admin/plans/1")).status_code == 401

    async def test_404_for_missing(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.delete("/api/admin/plans/9999", cookies=cookies)
        assert res.status_code == 404

    async def test_delete_cascades_to_days_groups_exercises(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Deleting a plan must delete its days, groups, and exercises.

        This is the full cascade verified end-to-end — the spec's "delete
        plan also removes 24 sets" guarantee depends on it.
        """
        from flexloop.models.exercise import Exercise

        cookies = await _make_admin_and_cookie(db_session)
        user = await _make_user(db_session)
        exercise = Exercise(
            name="Bench Press",
            muscle_group="chest",
            equipment="barbell",
        )
        db_session.add(exercise)
        await db_session.commit()
        await db_session.refresh(exercise)

        plan = await _make_plan(db_session, user_id=user.id)
        day = PlanDay(plan_id=plan.id, day_number=1, label="Upper", focus="chest")
        db_session.add(day)
        await db_session.flush()
        group = ExerciseGroup(
            plan_day_id=day.id, group_type="straight", order=1, rest_after_group_sec=120
        )
        db_session.add(group)
        await db_session.flush()
        plan_ex = PlanExercise(
            plan_day_id=day.id,
            exercise_group_id=group.id,
            exercise_id=exercise.id,
            order=1,
            sets=4,
            reps=8,
            weight=100.0,
        )
        db_session.add(plan_ex)
        await db_session.commit()

        plan_id = plan.id
        day_id = day.id
        group_id = group.id
        plan_ex_id = plan_ex.id

        res = await client.delete(f"/api/admin/plans/{plan_id}", cookies=cookies)
        assert res.status_code == 204

        # All four rows should be gone.
        from sqlalchemy import select as _select
        assert (
            await db_session.execute(_select(Plan).where(Plan.id == plan_id))
        ).scalar_one_or_none() is None
        assert (
            await db_session.execute(_select(PlanDay).where(PlanDay.id == day_id))
        ).scalar_one_or_none() is None
        assert (
            await db_session.execute(
                _select(ExerciseGroup).where(ExerciseGroup.id == group_id)
            )
        ).scalar_one_or_none() is None
        assert (
            await db_session.execute(
                _select(PlanExercise).where(PlanExercise.id == plan_ex_id)
            )
        ).scalar_one_or_none() is None
```

- [ ] **Step 2: Run them to verify they fail**

```bash
uv run pytest tests/test_admin_plans.py::TestDeletePlan -v
```

Expected: all 3 fail until the DELETE endpoint is added.

- [ ] **Step 3: Implement the delete endpoint**

Append to `src/flexloop/admin/routers/plans.py`:

```python
@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> None:
    # Eager-load everything so cascade="all, delete-orphan" can walk the tree
    # without issuing lazy lookups during flush.
    result = await db.execute(_plan_query().where(Plan.id == plan_id))
    plan = result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="plan not found",
        )
    await db.delete(plan)
    await db.commit()
```

- [ ] **Step 4: Run the tests**

```bash
uv run pytest tests/test_admin_plans.py::TestDeletePlan -v
```

Expected: all 3 pass. If the cascade test fails with orphaned `PlanExercise` rows, it means the `PlanDay.exercises` cascade isn't firing — investigate the model's `cascade` arguments before moving on. **Do not** work around it with explicit deletes in the router; the cascade is set at the model level for a reason and fixing it at the handler layer would mask a bug the iOS router might also have.

- [ ] **Step 5: Run the full suite**

```bash
uv run pytest -q
```

Expected: green.

- [ ] **Step 6: Commit**

```bash
git add src/flexloop/admin/routers/plans.py tests/test_admin_plans.py
git commit -m "feat(admin): DELETE /api/admin/plans/{id} with cascade verification"
```

---

**End of Chunk 1.** The standard 5-endpoint CRUD for Plans is wired up, mounted, tested, and passing the full suite. Next chunk adds the three day-level endpoints that make this a "Plan editor" and not just another CRUD page.

---

## Chunk 2: Backend — Plan day endpoints

Three new endpoints on the same router:

```
POST   /api/admin/plans/{plan_id}/days                   add a new day (full nested payload)
PUT    /api/admin/plans/{plan_id}/days/{day_number}      replace entire day
DELETE /api/admin/plans/{plan_id}/days/{day_number}      delete a day
```

All three have their own test file (`tests/test_admin_plans_days.py`) because the fixtures are heavier — every test needs pre-seeded `Exercise` rows.

### Task 8: Test fixtures + failing `POST /days` tests

**Files:**
- Create: `tests/test_admin_plans_days.py`

- [ ] **Step 1: Write the file with shared helpers and the POST tests**

```python
"""Integration tests for the admin Plan day endpoints.

These endpoints let an operator hand-edit a plan's day/group/exercise/set
structure without round-tripping through the full plan JSON. A day is the
atomic save unit per spec §9.3 — PUT replaces an entire day's contents.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from flexloop.admin.auth import SESSION_COOKIE_NAME, create_session, hash_password
from flexloop.models.admin_user import AdminUser
from flexloop.models.exercise import Exercise
from flexloop.models.plan import ExerciseGroup, Plan, PlanDay, PlanExercise
from flexloop.models.user import User


async def _make_admin_and_cookie(db: AsyncSession) -> dict[str, str]:
    admin = AdminUser(username="tester", password_hash=hash_password("password123"))
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    token, _ = await create_session(db, admin_user_id=admin.id)
    return {SESSION_COOKIE_NAME: token}


async def _setup_plan_with_exercises(db: AsyncSession) -> tuple[Plan, list[Exercise]]:
    """Create a user, an empty plan, and two exercises for the tests to use."""
    user = User(
        name="Plan Owner", gender="other", age=30, height=180, weight=80,
        weight_unit="kg", height_unit="cm", experience_level="intermediate",
        goals="", available_equipment=[],
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    plan = Plan(
        user_id=user.id, name="Test Plan", split_type="upper_lower",
        cycle_length=4, status="active", ai_generated=False,
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)

    e1 = Exercise(name="Bench Press", muscle_group="chest", equipment="barbell")
    e2 = Exercise(name="Overhead Press", muscle_group="shoulders", equipment="barbell")
    db.add_all([e1, e2])
    await db.commit()
    await db.refresh(e1)
    await db.refresh(e2)

    return plan, [e1, e2]


async def _reload_day(db: AsyncSession, plan_id: int, day_number: int) -> PlanDay | None:
    result = await db.execute(
        select(PlanDay)
        .options(
            selectinload(PlanDay.exercise_groups).selectinload(ExerciseGroup.exercises)
        )
        .where(PlanDay.plan_id == plan_id, PlanDay.day_number == day_number)
    )
    return result.scalar_one_or_none()


class TestAddDay:
    async def test_requires_auth(self, client: AsyncClient) -> None:
        res = await client.post(
            "/api/admin/plans/1/days", json={"day_number": 1, "label": "x", "focus": ""}
        )
        assert res.status_code == 401

    async def test_404_when_plan_missing(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.post(
            "/api/admin/plans/9999/days",
            json={"day_number": 1, "label": "Day 1", "focus": "full body"},
            cookies=cookies,
        )
        assert res.status_code == 404

    async def test_adds_empty_day(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        plan, _ = await _setup_plan_with_exercises(db_session)

        res = await client.post(
            f"/api/admin/plans/{plan.id}/days",
            json={"day_number": 1, "label": "Upper A", "focus": "chest, back"},
            cookies=cookies,
        )
        assert res.status_code == 201
        body = res.json()
        assert body["day_number"] == 1
        assert body["label"] == "Upper A"
        assert body["focus"] == "chest, back"
        assert body["exercise_groups"] == []

    async def test_adds_day_with_full_nested_payload(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        plan, [e1, e2] = await _setup_plan_with_exercises(db_session)

        payload = {
            "day_number": 1,
            "label": "Upper A",
            "focus": "chest, shoulders",
            "exercise_groups": [
                {
                    "group_type": "straight",
                    "order": 1,
                    "rest_after_group_sec": 120,
                    "exercises": [
                        {
                            "exercise_id": e1.id,
                            "order": 1,
                            "sets": 4,
                            "reps": 8,
                            "weight": 100.0,
                            "rpe_target": 7.5,
                            "sets_json": [
                                {"set_number": 1, "target_weight": 100, "target_reps": 8, "target_rpe": 7},
                                {"set_number": 2, "target_weight": 100, "target_reps": 8, "target_rpe": 7.5},
                            ],
                        },
                        {
                            "exercise_id": e2.id,
                            "order": 2,
                            "sets": 3,
                            "reps": 6,
                        },
                    ],
                }
            ],
        }
        res = await client.post(
            f"/api/admin/plans/{plan.id}/days", json=payload, cookies=cookies
        )
        assert res.status_code == 201
        body = res.json()
        assert len(body["exercise_groups"]) == 1
        group = body["exercise_groups"][0]
        assert group["group_type"] == "straight"
        assert len(group["exercises"]) == 2
        assert group["exercises"][0]["exercise_id"] == e1.id
        assert group["exercises"][0]["sets"] == 4
        assert group["exercises"][0]["sets_json"][0]["target_weight"] == 100
        assert group["exercises"][1]["exercise_id"] == e2.id

        # Verify DB state reflects the nested shape.
        day = await _reload_day(db_session, plan.id, 1)
        assert day is not None
        assert len(day.exercise_groups) == 1
        assert len(day.exercise_groups[0].exercises) == 2

    async def test_rejects_duplicate_day_number(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        plan, _ = await _setup_plan_with_exercises(db_session)

        # First add
        res1 = await client.post(
            f"/api/admin/plans/{plan.id}/days",
            json={"day_number": 1, "label": "A", "focus": ""},
            cookies=cookies,
        )
        assert res1.status_code == 201

        # Second add with same day_number
        res2 = await client.post(
            f"/api/admin/plans/{plan.id}/days",
            json={"day_number": 1, "label": "B", "focus": ""},
            cookies=cookies,
        )
        assert res2.status_code == 409
        assert "day_number" in res2.json()["detail"].lower()

    async def test_rejects_unknown_field_on_day(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        plan, _ = await _setup_plan_with_exercises(db_session)
        res = await client.post(
            f"/api/admin/plans/{plan.id}/days",
            json={"day_number": 1, "label": "x", "focus": "", "totally_wrong": True},
            cookies=cookies,
        )
        assert res.status_code == 422
```

- [ ] **Step 2: Run them to verify they fail**

```bash
uv run pytest tests/test_admin_plans_days.py::TestAddDay -v
```

Expected: all 6 fail (no endpoint yet).

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_admin_plans_days.py
git commit -m "test(admin): failing tests for POST /api/admin/plans/{id}/days"
```

---

### Task 9: Implement `POST /api/admin/plans/{plan_id}/days`

**Files:**
- Modify: `src/flexloop/admin/routers/plans.py`

- [ ] **Step 1: Add helper + POST handler**

Append to `src/flexloop/admin/routers/plans.py`. First add the new imports near the top of the file:

```python
from flexloop.admin.schemas.plans import (
    PlanAdminCreate,
    PlanAdminResponse,
    PlanAdminUpdate,
    PlanDayAdminCreate,
    PlanDayAdminResponse,
    PlanDayAdminUpdate,
)
from flexloop.models.plan import ExerciseGroup, Plan, PlanDay, PlanExercise
```

(Update the existing import block — don't duplicate.)

Then add a helper at module scope, below `_plan_query`:

```python
def _day_query(plan_id: int, day_number: int):
    """Eager-loaded SELECT for a single day on a specific plan."""
    return (
        select(PlanDay)
        .options(
            selectinload(PlanDay.exercise_groups).selectinload(ExerciseGroup.exercises)
        )
        .where(PlanDay.plan_id == plan_id, PlanDay.day_number == day_number)
    )


def _apply_groups_to_day(
    day: PlanDay, groups_payload: list
) -> None:
    """Append a list of ExerciseGroupAdminCreate payloads onto a clean day.

    Caller is responsible for clearing the day's existing groups/exercises
    first (for PUT) — this helper only adds.
    """
    for group_payload in groups_payload:
        group = ExerciseGroup(
            plan_day_id=day.id,
            group_type=group_payload.group_type,
            order=group_payload.order,
            rest_after_group_sec=group_payload.rest_after_group_sec,
        )
        day.exercise_groups.append(group)
        for ex_payload in group_payload.exercises:
            plan_ex = PlanExercise(
                plan_day_id=day.id,
                exercise_group_id=None,  # set after group flush
                exercise_id=ex_payload.exercise_id,
                order=ex_payload.order,
                sets=ex_payload.sets,
                reps=ex_payload.reps,
                weight=ex_payload.weight,
                rpe_target=ex_payload.rpe_target,
                sets_json=(
                    [s.model_dump() for s in ex_payload.sets_json]
                    if ex_payload.sets_json
                    else None
                ),
                notes=ex_payload.notes,
            )
            # Temporarily attach to both collections; the exercise_group_id
            # is resolved at commit time via relationship binding.
            group.exercises.append(plan_ex)
            day.exercises.append(plan_ex)
```

Then add the POST handler:

```python
@router.post(
    "/{plan_id}/days",
    response_model=PlanDayAdminResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_plan_day(
    plan_id: int,
    payload: PlanDayAdminCreate,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> PlanDay:
    # Verify the plan exists (we don't need the eager-load here).
    plan_result = await db.execute(select(Plan).where(Plan.id == plan_id))
    plan = plan_result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="plan not found",
        )

    # Reject duplicate day_number — no auto-renumbering.
    existing = await db.execute(
        select(PlanDay).where(
            PlanDay.plan_id == plan_id, PlanDay.day_number == payload.day_number
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"day_number {payload.day_number} already exists on this plan",
        )

    day = PlanDay(
        plan_id=plan_id,
        day_number=payload.day_number,
        label=payload.label,
        focus=payload.focus,
    )
    db.add(day)
    await db.flush()  # gives us day.id for the nested appends

    _apply_groups_to_day(day, payload.exercise_groups)

    await db.commit()

    # Re-query with the full eager-load for a clean response payload.
    result = await db.execute(_day_query(plan_id, payload.day_number))
    return result.scalar_one()
```

- [ ] **Step 2: Run the tests**

```bash
uv run pytest tests/test_admin_plans_days.py::TestAddDay -v
```

Expected: all 6 pass. If the nested-payload test fails with "PlanExercise.exercise_group_id cannot be NULL", the problem is that the `ExerciseGroup` primary key isn't populated at the time of the `PlanExercise` creation. Fix by adding an explicit `await db.flush()` between appending the group and appending the exercises — SQLAlchemy will flush the pending group row and populate its `id`, which the relationship then uses. Update `_apply_groups_to_day` like this:

```python
def _apply_groups_to_day(day: PlanDay, groups_payload: list) -> None:
    """..."""
    # NOTE: we rely on SQLAlchemy's relationship bookkeeping to propagate
    # exercise_group_id at commit time, NOT on manually reading group.id.
    # Appending the PlanExercise to group.exercises is what creates the FK.
```

Then assign via the relationship rather than the raw id:

```python
plan_ex = PlanExercise(
    plan_day_id=day.id,
    exercise_id=ex_payload.exercise_id,
    order=ex_payload.order,
    sets=ex_payload.sets,
    reps=ex_payload.reps,
    weight=ex_payload.weight,
    rpe_target=ex_payload.rpe_target,
    sets_json=(
        [s.model_dump() for s in ex_payload.sets_json]
        if ex_payload.sets_json
        else None
    ),
    notes=ex_payload.notes,
)
group.exercises.append(plan_ex)
```

(Do NOT append to `day.exercises` in addition — it leads to double-insert attempts. The `back_populates="exercise_group"` + `back_populates="plan_day"` relationships handle collection membership on both sides automatically once the FK is resolved at flush time. Since `PlanDay.exercises` has `back_populates="plan_day"` from the model, setting `plan_day_id=day.id` is enough; the collection picks it up after flush.)

Re-run the tests after the fix.

- [ ] **Step 3: Run the full suite**

```bash
uv run pytest -q
```

Expected: green.

- [ ] **Step 4: Commit**

```bash
git add src/flexloop/admin/routers/plans.py
git commit -m "feat(admin): POST /api/admin/plans/{id}/days — add a day"
```

---

### Task 10: Failing tests for `PUT /api/admin/plans/{plan_id}/days/{day_number}`

**Files:**
- Modify: `tests/test_admin_plans_days.py`

- [ ] **Step 1: Append the PUT day tests**

```python
class TestReplaceDay:
    async def test_requires_auth(self, client: AsyncClient) -> None:
        res = await client.put(
            "/api/admin/plans/1/days/1", json={"label": "x", "exercise_groups": []}
        )
        assert res.status_code == 401

    async def test_404_when_plan_missing(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.put(
            "/api/admin/plans/9999/days/1",
            json={"label": "x", "exercise_groups": []},
            cookies=cookies,
        )
        assert res.status_code == 404

    async def test_404_when_day_missing(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        plan, _ = await _setup_plan_with_exercises(db_session)
        res = await client.put(
            f"/api/admin/plans/{plan.id}/days/7",
            json={"label": "x", "exercise_groups": []},
            cookies=cookies,
        )
        assert res.status_code == 404

    async def test_replaces_entire_day_contents(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """The PUT endpoint clears the day's existing groups/exercises and
        replaces them from the payload atomically.
        """
        cookies = await _make_admin_and_cookie(db_session)
        plan, [e1, e2] = await _setup_plan_with_exercises(db_session)

        # Seed: create a day with 1 group, 1 exercise via POST.
        await client.post(
            f"/api/admin/plans/{plan.id}/days",
            json={
                "day_number": 1,
                "label": "Old label",
                "focus": "old focus",
                "exercise_groups": [
                    {
                        "group_type": "straight",
                        "order": 1,
                        "rest_after_group_sec": 90,
                        "exercises": [
                            {"exercise_id": e1.id, "order": 1, "sets": 3, "reps": 10}
                        ],
                    }
                ],
            },
            cookies=cookies,
        )

        # Replace with a completely different structure.
        res = await client.put(
            f"/api/admin/plans/{plan.id}/days/1",
            json={
                "label": "New label",
                "focus": "new focus",
                "exercise_groups": [
                    {
                        "group_type": "superset",
                        "order": 1,
                        "rest_after_group_sec": 60,
                        "exercises": [
                            {"exercise_id": e2.id, "order": 1, "sets": 5, "reps": 5}
                        ],
                    },
                    {
                        "group_type": "straight",
                        "order": 2,
                        "rest_after_group_sec": 120,
                        "exercises": [],
                    },
                ],
            },
            cookies=cookies,
        )
        assert res.status_code == 200
        body = res.json()
        assert body["label"] == "New label"
        assert body["focus"] == "new focus"
        assert len(body["exercise_groups"]) == 2
        assert body["exercise_groups"][0]["group_type"] == "superset"
        assert body["exercise_groups"][0]["exercises"][0]["exercise_id"] == e2.id
        assert body["exercise_groups"][0]["exercises"][0]["sets"] == 5
        assert body["exercise_groups"][1]["exercises"] == []

        # Verify the old exercise row was deleted — not orphaned.
        from sqlalchemy import select as _select
        orphans = await db_session.execute(
            _select(PlanExercise).where(PlanExercise.exercise_id == e1.id)
        )
        assert orphans.scalar_one_or_none() is None

    async def test_replaces_with_empty_groups(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Submitting an empty exercise_groups list clears the day — this
        is how an admin "empties" a day without deleting it.
        """
        cookies = await _make_admin_and_cookie(db_session)
        plan, [e1, _] = await _setup_plan_with_exercises(db_session)
        await client.post(
            f"/api/admin/plans/{plan.id}/days",
            json={
                "day_number": 1,
                "label": "Day 1",
                "focus": "chest",
                "exercise_groups": [
                    {
                        "group_type": "straight",
                        "order": 1,
                        "rest_after_group_sec": 90,
                        "exercises": [
                            {"exercise_id": e1.id, "order": 1, "sets": 3, "reps": 10}
                        ],
                    }
                ],
            },
            cookies=cookies,
        )

        res = await client.put(
            f"/api/admin/plans/{plan.id}/days/1",
            json={"label": "Day 1", "exercise_groups": []},
            cookies=cookies,
        )
        assert res.status_code == 200
        assert res.json()["exercise_groups"] == []
```

- [ ] **Step 2: Run them to verify they fail**

```bash
uv run pytest tests/test_admin_plans_days.py::TestReplaceDay -v
```

Expected: all 5 fail.

- [ ] **Step 3: Commit failing tests**

```bash
git add tests/test_admin_plans_days.py
git commit -m "test(admin): failing tests for PUT /api/admin/plans/{id}/days/{n}"
```

---

### Task 11: Implement `PUT /api/admin/plans/{plan_id}/days/{day_number}`

**Files:**
- Modify: `src/flexloop/admin/routers/plans.py`

- [ ] **Step 1: Append the PUT handler**

```python
@router.put(
    "/{plan_id}/days/{day_number}",
    response_model=PlanDayAdminResponse,
)
async def replace_plan_day(
    plan_id: int,
    day_number: int,
    payload: PlanDayAdminUpdate,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> PlanDay:
    # Verify the plan exists separately from the day so we can return
    # "plan not found" vs "day not found" accurately.
    plan_result = await db.execute(select(Plan).where(Plan.id == plan_id))
    plan = plan_result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="plan not found",
        )

    day_result = await db.execute(_day_query(plan_id, day_number))
    day = day_result.scalar_one_or_none()
    if day is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"day_number {day_number} not found on plan {plan_id}",
        )

    # Apply optional metadata updates.
    if payload.label is not None:
        day.label = payload.label
    if payload.focus is not None:
        day.focus = payload.focus

    # Clear existing nested structure. Relying on cascade="all, delete-orphan"
    # on PlanDay.exercise_groups AND PlanDay.exercises, so clearing both
    # collections triggers the deletes at flush time.
    day.exercise_groups.clear()
    day.exercises.clear()
    await db.flush()

    # Append new groups/exercises from the payload.
    _apply_groups_to_day(day, payload.exercise_groups)

    await db.commit()

    result = await db.execute(_day_query(plan_id, day_number))
    return result.scalar_one()
```

- [ ] **Step 2: Run the tests**

```bash
uv run pytest tests/test_admin_plans_days.py::TestReplaceDay -v
```

Expected: all 5 pass. If `test_replaces_entire_day_contents` fails with the old `PlanExercise` still present, it means the cascade isn't catching the clear — see the Task 9 "expected troubleshooting" note and apply the same fix here (the cascade config on `PlanDay.exercises` is what matters).

- [ ] **Step 3: Run the full suite**

```bash
uv run pytest -q
```

Expected: green.

- [ ] **Step 4: Commit**

```bash
git add src/flexloop/admin/routers/plans.py
git commit -m "feat(admin): PUT /api/admin/plans/{id}/days/{n} — atomic day replace"
```

---

### Task 12: Failing tests for `DELETE /api/admin/plans/{plan_id}/days/{day_number}`

**Files:**
- Modify: `tests/test_admin_plans_days.py`

- [ ] **Step 1: Append the DELETE day tests**

```python
class TestDeleteDay:
    async def test_requires_auth(self, client: AsyncClient) -> None:
        assert (await client.delete("/api/admin/plans/1/days/1")).status_code == 401

    async def test_404_when_plan_missing(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.delete("/api/admin/plans/9999/days/1", cookies=cookies)
        assert res.status_code == 404

    async def test_404_when_day_missing(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        plan, _ = await _setup_plan_with_exercises(db_session)
        res = await client.delete(
            f"/api/admin/plans/{plan.id}/days/7", cookies=cookies
        )
        assert res.status_code == 404

    async def test_delete_cascades_to_groups_and_exercises(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        plan, [e1, _] = await _setup_plan_with_exercises(db_session)
        res = await client.post(
            f"/api/admin/plans/{plan.id}/days",
            json={
                "day_number": 1,
                "label": "Day 1",
                "focus": "chest",
                "exercise_groups": [
                    {
                        "group_type": "straight",
                        "order": 1,
                        "rest_after_group_sec": 90,
                        "exercises": [
                            {"exercise_id": e1.id, "order": 1, "sets": 3, "reps": 10}
                        ],
                    }
                ],
            },
            cookies=cookies,
        )
        assert res.status_code == 201
        day_body = res.json()
        day_id = day_body["id"]
        group_id = day_body["exercise_groups"][0]["id"]
        plan_ex_id = day_body["exercise_groups"][0]["exercises"][0]["id"]

        res = await client.delete(
            f"/api/admin/plans/{plan.id}/days/1", cookies=cookies
        )
        assert res.status_code == 204

        from sqlalchemy import select as _select
        assert (
            await db_session.execute(_select(PlanDay).where(PlanDay.id == day_id))
        ).scalar_one_or_none() is None
        assert (
            await db_session.execute(
                _select(ExerciseGroup).where(ExerciseGroup.id == group_id)
            )
        ).scalar_one_or_none() is None
        assert (
            await db_session.execute(
                _select(PlanExercise).where(PlanExercise.id == plan_ex_id)
            )
        ).scalar_one_or_none() is None

        # Plan itself still exists.
        assert (
            await db_session.execute(_select(Plan).where(Plan.id == plan.id))
        ).scalar_one_or_none() is not None
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/test_admin_plans_days.py::TestDeleteDay -v
```

Expected: 4 fail (no endpoint).

- [ ] **Step 3: Commit failing tests**

```bash
git add tests/test_admin_plans_days.py
git commit -m "test(admin): failing tests for DELETE /api/admin/plans/{id}/days/{n}"
```

---

### Task 13: Implement `DELETE /api/admin/plans/{plan_id}/days/{day_number}`

**Files:**
- Modify: `src/flexloop/admin/routers/plans.py`

- [ ] **Step 1: Append the DELETE handler**

```python
@router.delete(
    "/{plan_id}/days/{day_number}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_plan_day(
    plan_id: int,
    day_number: int,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> None:
    plan_result = await db.execute(select(Plan).where(Plan.id == plan_id))
    if plan_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="plan not found",
        )

    day_result = await db.execute(_day_query(plan_id, day_number))
    day = day_result.scalar_one_or_none()
    if day is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"day_number {day_number} not found on plan {plan_id}",
        )

    await db.delete(day)
    await db.commit()
```

- [ ] **Step 2: Run the tests**

```bash
uv run pytest tests/test_admin_plans_days.py::TestDeleteDay -v
```

Expected: all 4 pass.

- [ ] **Step 3: Run the full suite**

```bash
uv run pytest -q
```

Expected: green. All backend work for phase 3 is now done.

- [ ] **Step 4: Commit**

```bash
git add src/flexloop/admin/routers/plans.py
git commit -m "feat(admin): DELETE /api/admin/plans/{id}/days/{n}"
```

---

**End of Chunk 2.** Backend has 8 endpoints total, all tested, all passing. Next chunk moves to the frontend Plans list page.

---

## Chunk 3: Frontend — Plans list page

This chunk adds a standard list page at `/plans` using the phase-2 shared components. It is the smaller of the two frontend chunks — the heavy lifting (the per-day editor) is Chunk 4. The list page delivers: browse, search, filter by user + status, pagination, create (empty plan), edit metadata (EditSheet with JSON tab), delete.

### Task 14: Regenerate TypeScript types from the updated OpenAPI schema

**Files:**
- Modify: `admin-ui/src/lib/api.types.ts`

- [ ] **Step 1: Start the backend in one terminal**

```bash
uv run uvicorn flexloop.main:app --port 8000
```

Leave it running.

- [ ] **Step 2: In a second terminal, regenerate types**

```bash
cd admin-ui
npm run codegen
```

Expected: `src/lib/api.types.ts` is rewritten. `git diff` should show new entries for `PlanAdminResponse`, `PlanAdminCreate`, `PlanAdminUpdate`, `PlanDayAdminCreate`, `PlanDayAdminUpdate`, `PlanDayAdminResponse`, `ExerciseGroupAdminCreate`, `ExerciseGroupAdminResponse`, `PlanExerciseAdminCreate`, `PlanExerciseAdminResponse`, `SetTargetAdmin`.

- [ ] **Step 3: Stop the backend**

Ctrl-C the uvicorn terminal.

- [ ] **Step 4: Commit**

```bash
git add admin-ui/src/lib/api.types.ts
git commit -m "chore(admin-ui): regenerate api.types.ts for plans schemas"
```

---

### Task 15: Install the `accordion` shadcn component

**Files:**
- Create: `admin-ui/src/components/ui/accordion.tsx`

- [ ] **Step 1: Run the shadcn add command**

```bash
cd admin-ui
npx shadcn@latest add accordion
```

Expected: prompts to confirm, then creates `src/components/ui/accordion.tsx`. If it prompts about overwriting or dependencies, accept defaults.

- [ ] **Step 2: Verify the file exists**

```bash
ls src/components/ui/accordion.tsx
```

Expected: file exists, ~60 lines, exports `Accordion`, `AccordionItem`, `AccordionTrigger`, `AccordionContent`.

- [ ] **Step 3: Commit**

```bash
cd ..
git add admin-ui/src/components/ui/accordion.tsx admin-ui/package.json admin-ui/package-lock.json
git commit -m "chore(admin-ui): add shadcn accordion component"
```

---

### Task 16: Create `PlanForm` (metadata form used by the list page's EditSheet)

**Files:**
- Create: `admin-ui/src/components/forms/PlanForm.tsx`

Match the structure of `WorkoutForm.tsx`. Metadata only — no days. The list page's EditSheet uses this form inside its "Form" tab, and the existing `<JsonEditor>` handles the "JSON" tab.

- [ ] **Step 1: Create the form**

```tsx
/**
 * Hand-written react-hook-form + zod form for Plan metadata.
 *
 * This form ONLY edits plan metadata (name, split type, cycle length,
 * status, block dates). Day contents are edited on the Plan detail page
 * via the day endpoints — the admin update schema enforces this at the
 * API layer too.
 */
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { components } from "@/lib/api.types";

type Plan = components["schemas"]["PlanAdminResponse"];

const schema = z.object({
  user_id: z.coerce.number().int().positive(),
  name: z.string().min(1, "name is required"),
  split_type: z.string().default("custom"),
  cycle_length: z.coerce.number().int().min(1).max(14),
  block_start: z.string().nullable().optional(),
  block_end: z.string().nullable().optional(),
  status: z.enum(["active", "inactive", "archived"]),
  ai_generated: z.boolean().default(false),
});

export type PlanFormInput = z.input<typeof schema>;
export type PlanFormValues = z.output<typeof schema>;

type Props = {
  defaultValues?: Plan | null;
  onSubmit: (values: PlanFormValues) => void | Promise<void>;
  isSaving?: boolean;
};

export function PlanForm({ defaultValues, onSubmit, isSaving = false }: Props) {
  const { register, handleSubmit, setValue, watch, formState: { errors } } =
    useForm<PlanFormInput, unknown, PlanFormValues>({
      resolver: zodResolver(schema),
      defaultValues: defaultValues
        ? {
            user_id: defaultValues.user_id,
            name: defaultValues.name,
            split_type: defaultValues.split_type,
            cycle_length: defaultValues.cycle_length,
            block_start: defaultValues.block_start ?? "",
            block_end: defaultValues.block_end ?? "",
            status: defaultValues.status as "active" | "inactive" | "archived",
            ai_generated: defaultValues.ai_generated,
          }
        : {
            user_id: 1,
            name: "",
            split_type: "custom",
            cycle_length: 3,
            block_start: "",
            block_end: "",
            status: "active",
            ai_generated: false,
          },
    });

  const status = watch("status");

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      className="space-y-4"
    >
      <div className="space-y-1.5">
        <Label htmlFor="user_id">User ID</Label>
        <Input id="user_id" type="number" {...register("user_id")} />
        {errors.user_id && (
          <p className="text-sm text-red-600">{errors.user_id.message}</p>
        )}
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="name">Name</Label>
        <Input id="name" {...register("name")} />
        {errors.name && (
          <p className="text-sm text-red-600">{errors.name.message}</p>
        )}
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="split_type">Split type</Label>
          <Input id="split_type" {...register("split_type")} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="cycle_length">Cycle length (days)</Label>
          <Input id="cycle_length" type="number" {...register("cycle_length")} />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="block_start">Block start</Label>
          <Input id="block_start" type="date" {...register("block_start")} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="block_end">Block end</Label>
          <Input id="block_end" type="date" {...register("block_end")} />
        </div>
      </div>
      <div className="space-y-1.5">
        <Label>Status</Label>
        <Select
          value={status}
          onValueChange={(v) =>
            setValue("status", v as "active" | "inactive" | "archived")
          }
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="active">Active</SelectItem>
            <SelectItem value="inactive">Inactive</SelectItem>
            <SelectItem value="archived">Archived</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="flex justify-end pt-2">
        <Button type="submit" disabled={isSaving}>
          {isSaving ? "Saving…" : "Save"}
        </Button>
      </div>
    </form>
  );
}
```

- [ ] **Step 2: Verify it compiles**

```bash
cd admin-ui
npx tsc --noEmit
```

Expected: no errors. If there are errors, fix before committing. Common issue: `block_start`/`block_end` string vs `date | null` mismatch — the form accepts strings and normalizes to null at submit time in the page layer.

- [ ] **Step 3: Commit**

```bash
cd ..
git add admin-ui/src/components/forms/PlanForm.tsx
git commit -m "feat(admin-ui): add PlanForm for metadata editing"
```

---

### Task 17: Create `PlansPage` — list + create + edit metadata + delete

**Files:**
- Create: `admin-ui/src/pages/PlansPage.tsx`

Model this on `WorkoutsPage.tsx`. Add a status filter (any/active/inactive/archived), a user_id filter input, and an "Open" button per row that navigates to the detail page.

- [ ] **Step 1: Create the page**

```tsx
/**
 * Plans admin list page.
 *
 * Supports list, filter by status + user_id, search, pagination, create
 * (empty plan via POST with metadata only), inline metadata edit via
 * EditSheet, hard-delete with cascade confirmation.
 *
 * Row click / "Open" button navigates to /plans/:id (the detail page
 * delivered in Chunk 4) where day-level edits happen.
 */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { DataTable } from "@/components/DataTable";
import type { Column, SortState } from "@/components/DataTable";
import { DeleteDialog } from "@/components/DeleteDialog";
import { EditSheet } from "@/components/EditSheet";
import { PlanForm } from "@/components/forms/PlanForm";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useCreate, useDelete, useList, useUpdate } from "@/hooks/useCrud";
import type { components } from "@/lib/api.types";

type Plan = components["schemas"]["PlanAdminResponse"];
type PlanCreate = components["schemas"]["PlanAdminCreate"];
type PlanUpdate = components["schemas"]["PlanAdminUpdate"];

const RESOURCE = "plans";

type StatusFilter = "any" | "active" | "inactive" | "archived";

export function PlansPage() {
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [perPage] = useState(50);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortState>(null);
  const [status, setStatus] = useState<StatusFilter>("any");
  const [userFilter, setUserFilter] = useState<string>("");
  const [editTarget, setEditTarget] = useState<Plan | "new" | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Plan | null>(null);

  const list = useList<Plan>(RESOURCE, {
    page,
    per_page: perPage,
    search: search || undefined,
    sort: sort ? `${sort.column}:${sort.direction}` : undefined,
    filters: {
      status: status === "any" ? undefined : status,
      user_id: userFilter || undefined,
    },
  });
  const create = useCreate<Plan, PlanCreate>(RESOURCE);
  const update = useUpdate<Plan, PlanUpdate>(RESOURCE);
  const del = useDelete(RESOURCE);

  const editRow: Plan | null =
    editTarget && editTarget !== "new" ? editTarget : null;

  const columns: Column<Plan>[] = [
    { key: "id", header: "ID", sortable: true, className: "w-16 tabular-nums" },
    { key: "name", header: "Name", sortable: true },
    {
      key: "user_id",
      header: "User",
      sortable: true,
      className: "w-20 tabular-nums",
    },
    { key: "split_type", header: "Split" },
    {
      key: "cycle_length",
      header: "Cycle",
      className: "w-20 tabular-nums text-right",
    },
    {
      key: "days",
      header: "Days",
      render: (p) => (
        <span className="tabular-nums">{p.days?.length ?? 0}</span>
      ),
      className: "text-right w-16",
    },
    {
      key: "status",
      header: "Status",
      render: (p) => (
        <Badge variant={p.status === "active" ? "default" : "secondary"}>
          {p.status}
        </Badge>
      ),
    },
    {
      key: "_actions",
      header: "",
      className: "w-48 text-right",
      render: (p) => (
        <div className="flex justify-end gap-1">
          <Button
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              navigate(`/plans/${p.id}`);
            }}
          >
            Open
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={(e) => {
              e.stopPropagation();
              setEditTarget(p);
            }}
          >
            Edit
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={(e) => {
              e.stopPropagation();
              setDeleteTarget(p);
            }}
          >
            Delete
          </Button>
        </div>
      ),
    },
  ];

  const toolbar = (
    <div className="flex items-center gap-2">
      <Input
        className="w-28"
        placeholder="user id"
        value={userFilter}
        onChange={(e) => {
          setUserFilter(e.target.value);
          setPage(1);
        }}
      />
      <Select
        value={status}
        onValueChange={(v) => {
          setStatus(v as StatusFilter);
          setPage(1);
        }}
      >
        <SelectTrigger className="w-36">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="any">All statuses</SelectItem>
          <SelectItem value="active">Active</SelectItem>
          <SelectItem value="inactive">Inactive</SelectItem>
          <SelectItem value="archived">Archived</SelectItem>
        </SelectContent>
      </Select>
      <Button onClick={() => setEditTarget("new")}>New plan</Button>
    </div>
  );

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Plans</h1>
      <DataTable<Plan>
        columns={columns}
        rows={list.data?.items ?? []}
        isLoading={list.isLoading}
        isError={list.isError}
        total={list.data?.total ?? 0}
        page={page}
        perPage={perPage}
        search={search}
        onSearchChange={(s) => {
          setSearch(s);
          setPage(1);
        }}
        onPageChange={setPage}
        sort={sort}
        onSortChange={setSort}
        rowKey={(p) => p.id}
        onRowClick={(p) => navigate(`/plans/${p.id}`)}
        resourceLabel="plans"
        toolbar={toolbar}
      />
      <EditSheet<Plan>
        open={editTarget !== null}
        onOpenChange={(o) => !o && setEditTarget(null)}
        title={
          editTarget === "new"
            ? "New plan"
            : `Edit plan #${editRow ? editRow.id : ""}`
        }
        row={editRow}
        form={
          <PlanForm
            defaultValues={editRow}
            isSaving={create.isPending || update.isPending}
            onSubmit={async (v) => {
              try {
                // Normalize empty date strings to null for the API.
                const payload = {
                  ...v,
                  block_start: v.block_start || null,
                  block_end: v.block_end || null,
                };
                if (editTarget === "new") {
                  await create.mutateAsync(payload as PlanCreate);
                  toast.success("Plan created");
                } else if (editRow) {
                  // Update payload shouldn't include user_id (not in update schema).
                  const { user_id: _user_id, ...updatePayload } = payload;
                  await update.mutateAsync({
                    id: editRow.id,
                    input: updatePayload as PlanUpdate,
                  });
                  toast.success("Plan updated");
                }
                setEditTarget(null);
              } catch (e) {
                toast.error((e as Error).message);
              }
            }}
          />
        }
        jsonPutEndpoint={
          editRow ? `/api/admin/plans/${editRow.id}` : undefined
        }
        jsonValue={editRow}
        onJsonSaved={() => setEditTarget(null)}
      />
      <DeleteDialog
        open={deleteTarget !== null}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
        title="Delete plan?"
        description={
          deleteTarget
            ? `Delete "${deleteTarget.name}"? This will also delete all days, groups, exercises, and set targets. This cannot be undone.`
            : ""
        }
        onConfirm={async () => {
          if (!deleteTarget) return;
          try {
            await del.mutateAsync(deleteTarget.id);
            toast.success("Plan deleted");
            setDeleteTarget(null);
          } catch (e) {
            toast.error((e as Error).message);
          }
        }}
      />
    </div>
  );
}
```

- [ ] **Step 2: Verify the file compiles**

```bash
cd admin-ui
npx tsc --noEmit
```

Expected: no errors. If any, the most likely causes are (a) the `EditSheet` prop names don't match — open `src/components/EditSheet.tsx` and see what props exist, then match them, or (b) `DataTable` doesn't have `onRowClick` — check its prop type and either add support or remove the prop from `PlansPage`.

> **If** `onRowClick` isn't a prop on `DataTable`, just drop that line — the Open button already covers navigation. Don't modify shared components in this task; note it as a follow-up.

- [ ] **Step 3: Commit**

```bash
cd ..
git add admin-ui/src/pages/PlansPage.tsx
git commit -m "feat(admin-ui): Plans list page (list/create/edit/delete)"
```

---

### Task 18: Wire up the Plans route and enable the sidebar item

**Files:**
- Modify: `admin-ui/src/App.tsx`
- Modify: `admin-ui/src/components/AppSidebar.tsx`

- [ ] **Step 1: Add the Plans route in App.tsx**

Open `admin-ui/src/App.tsx`. Add the import near the other page imports:

```tsx
import { PlansPage } from "@/pages/PlansPage";
```

Add the route inside the existing `<Route path="/" ...>` block, next to the other resource routes (keep alphabetical-ish grouping under "User Data"):

```tsx
<Route path="plans" element={<PlansPage />} />
```

(Do NOT add `/plans/:id` yet — Chunk 4 adds the detail page route.)

- [ ] **Step 2: Enable the Plans sidebar item**

Open `admin-ui/src/components/AppSidebar.tsx`. Find this line (in the "User Data" group):

```tsx
{ label: "Plans", to: "/plans", icon: ClipboardList, disabled: true },
```

Remove `disabled: true`:

```tsx
{ label: "Plans", to: "/plans", icon: ClipboardList },
```

- [ ] **Step 3: Verify the frontend builds**

```bash
cd admin-ui
npm run build
```

Expected: Vite build succeeds, output written to `../src/flexloop/static/admin/`. If there's a TS error, fix it.

- [ ] **Step 4: Smoke-check in the dev server**

Start the backend (`uv run uvicorn flexloop.main:app --port 8000`) in one terminal, and `cd admin-ui && npm run dev` in another. Open http://localhost:5173/admin/plans and verify:
- The sidebar Plans entry is enabled (not grey)
- The list page loads with an empty table
- Clicking "New plan" opens the EditSheet with the form
- Filling in name + user_id + submitting creates a plan and the table refreshes
- Edit opens the sheet with pre-filled values
- Delete opens the confirm dialog, confirming removes the row
- The "Open" button logs a browser 404 for `/admin/plans/1` (detail page doesn't exist yet — that's Chunk 4)

Stop both dev servers when done.

- [ ] **Step 5: Commit**

```bash
cd ..
git add admin-ui/src/App.tsx admin-ui/src/components/AppSidebar.tsx
git commit -m "feat(admin-ui): enable Plans sidebar item and /plans route"
```

---

**End of Chunk 3.** Plans list, create, edit metadata, and delete are all working in the UI. The heavy chunk — the per-day editor on the detail page — is next.

---

## Chunk 4: Frontend — Plan detail page (per-day editor)

This chunk delivers the unique UI for phase 3: a page at `/plans/:id` with per-day collapsible accordions, inline group/exercise/set editing, and per-day atomic saves via the day endpoints. The sub-components live under `components/plan-editor/` because none of them are reusable outside this page.

Design note: the sub-components are **uncontrolled at the tree level and controlled at the page level**. The detail page holds the source of truth (the fetched plan) in TanStack Query cache. Each `DayAccordion` holds its own draft state (a local copy of the day's groups/exercises that the user can mutate freely). Clicking "Save day" POSTs the draft to the day endpoint; on success, the page invalidates the detail query, which re-renders the accordion with the freshly-returned day. No optimistic updates — the endpoint is slow enough (one transaction per save) that showing the loading state is honest.

### Task 19: `SetTargetsGrid` — editable weight/reps/rpe grid

**Files:**
- Create: `admin-ui/src/components/plan-editor/SetTargetsGrid.tsx`

This is the innermost table from the spec §9.3 layout: one row per set with editable weight/reps/rpe fields. It does NOT talk to the API directly — it receives a `sets_json` array and an `onChange` callback, and the parent `ExerciseEditor` bubbles changes up to the `DayAccordion`'s draft state.

- [ ] **Step 1: Create the component**

```tsx
/**
 * Editable grid of set targets for a single PlanExercise.
 *
 * Receives a sets_json array (may be null — meaning "use the top-level
 * sets/reps/weight defaults") and calls onChange with the new array on
 * every edit. Parent components decide when to persist.
 *
 * If sets_json is null, the grid shows a button to "initialize per-set
 * targets" which populates the array from the top-level sets count.
 */
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { components } from "@/lib/api.types";

type SetTarget = components["schemas"]["SetTargetAdmin"];

type Props = {
  setsJson: SetTarget[] | null;
  fallbackSets: number;
  fallbackReps: number;
  fallbackWeight: number | null;
  onChange: (next: SetTarget[] | null) => void;
};

export function SetTargetsGrid({
  setsJson,
  fallbackSets,
  fallbackReps,
  fallbackWeight,
  onChange,
}: Props) {
  if (setsJson === null || setsJson === undefined) {
    return (
      <div className="text-sm text-muted-foreground py-2">
        <span className="mr-2">
          Using top-level defaults ({fallbackSets}×{fallbackReps}
          {fallbackWeight !== null ? ` @ ${fallbackWeight}` : ""}).
        </span>
        <Button
          size="sm"
          variant="outline"
          type="button"
          onClick={() => {
            const rows: SetTarget[] = Array.from(
              { length: fallbackSets },
              (_, i) => ({
                set_number: i + 1,
                target_weight: fallbackWeight,
                target_reps: fallbackReps,
                target_rpe: null,
              }),
            );
            onChange(rows);
          }}
        >
          Use per-set targets
        </Button>
      </div>
    );
  }

  const updateRow = (index: number, patch: Partial<SetTarget>) => {
    const next = setsJson.map((row, i) =>
      i === index ? { ...row, ...patch } : row,
    );
    onChange(next);
  };

  return (
    <div className="space-y-1 pt-2">
      <div className="grid grid-cols-[3rem_1fr_1fr_1fr_2rem] gap-2 text-xs text-muted-foreground">
        <span>#</span>
        <span>Weight</span>
        <span>Reps</span>
        <span>RPE</span>
        <span />
      </div>
      {setsJson.map((row, i) => (
        <div
          key={i}
          className="grid grid-cols-[3rem_1fr_1fr_1fr_2rem] gap-2 items-center"
        >
          <span className="tabular-nums text-sm">{row.set_number}</span>
          <Input
            type="number"
            step="0.5"
            value={row.target_weight ?? ""}
            onChange={(e) =>
              updateRow(i, {
                target_weight:
                  e.target.value === "" ? null : Number(e.target.value),
              })
            }
          />
          <Input
            type="number"
            value={row.target_reps}
            onChange={(e) =>
              updateRow(i, { target_reps: Number(e.target.value) })
            }
          />
          <Input
            type="number"
            step="0.5"
            value={row.target_rpe ?? ""}
            onChange={(e) =>
              updateRow(i, {
                target_rpe:
                  e.target.value === "" ? null : Number(e.target.value),
              })
            }
          />
          <Button
            type="button"
            size="icon"
            variant="ghost"
            onClick={() => {
              const next = setsJson
                .filter((_, j) => j !== i)
                .map((r, j) => ({ ...r, set_number: j + 1 }));
              onChange(next.length === 0 ? null : next);
            }}
          >
            ×
          </Button>
        </div>
      ))}
      <Button
        type="button"
        size="sm"
        variant="ghost"
        onClick={() => {
          const lastNumber = setsJson.length;
          const last = setsJson[setsJson.length - 1];
          onChange([
            ...setsJson,
            {
              set_number: lastNumber + 1,
              target_weight: last?.target_weight ?? null,
              target_reps: last?.target_reps ?? fallbackReps,
              target_rpe: last?.target_rpe ?? null,
            },
          ]);
        }}
      >
        + Add set
      </Button>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
cd admin-ui && npx tsc --noEmit && cd ..
git add admin-ui/src/components/plan-editor/SetTargetsGrid.tsx
git commit -m "feat(admin-ui): SetTargetsGrid for editable set targets"
```

---

### Task 20: `ExerciseEditor` — one PlanExercise row

**Files:**
- Create: `admin-ui/src/components/plan-editor/ExerciseEditor.tsx`

- [ ] **Step 1: Create the component**

```tsx
/**
 * Editor for a single PlanExercise inside a group.
 *
 * Mirrors the inline layout from spec §9.3: top row with exercise_id,
 * order, sets, reps, weight, rpe_target; optional SetTargetsGrid below.
 *
 * The parent GroupEditor controls draft state — this component never
 * talks to the API directly.
 */
import { SetTargetsGrid } from "./SetTargetsGrid";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { components } from "@/lib/api.types";

type ExerciseDraft = components["schemas"]["PlanExerciseAdminCreate"];

type Props = {
  value: ExerciseDraft;
  onChange: (next: ExerciseDraft) => void;
  onDelete: () => void;
};

export function ExerciseEditor({ value, onChange, onDelete }: Props) {
  const patch = (p: Partial<ExerciseDraft>) => onChange({ ...value, ...p });

  return (
    <div className="rounded-md border p-3 space-y-2">
      <div className="grid grid-cols-[5rem_4rem_4rem_4rem_5rem_4rem_auto] gap-2 items-end">
        <div className="space-y-1">
          <Label className="text-xs">Exercise ID</Label>
          <Input
            type="number"
            value={value.exercise_id}
            onChange={(e) => patch({ exercise_id: Number(e.target.value) })}
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Order</Label>
          <Input
            type="number"
            value={value.order}
            onChange={(e) => patch({ order: Number(e.target.value) })}
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Sets</Label>
          <Input
            type="number"
            value={value.sets}
            onChange={(e) => patch({ sets: Number(e.target.value) })}
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Reps</Label>
          <Input
            type="number"
            value={value.reps}
            onChange={(e) => patch({ reps: Number(e.target.value) })}
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Weight</Label>
          <Input
            type="number"
            step="0.5"
            value={value.weight ?? ""}
            onChange={(e) =>
              patch({
                weight: e.target.value === "" ? null : Number(e.target.value),
              })
            }
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">RPE</Label>
          <Input
            type="number"
            step="0.5"
            value={value.rpe_target ?? ""}
            onChange={(e) =>
              patch({
                rpe_target:
                  e.target.value === "" ? null : Number(e.target.value),
              })
            }
          />
        </div>
        <Button type="button" size="sm" variant="ghost" onClick={onDelete}>
          Delete
        </Button>
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Notes</Label>
        <Textarea
          rows={2}
          value={value.notes ?? ""}
          onChange={(e) => patch({ notes: e.target.value || null })}
        />
      </div>
      <SetTargetsGrid
        setsJson={value.sets_json ?? null}
        fallbackSets={value.sets}
        fallbackReps={value.reps}
        fallbackWeight={value.weight ?? null}
        onChange={(next) => patch({ sets_json: next })}
      />
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
cd admin-ui && npx tsc --noEmit && cd ..
git add admin-ui/src/components/plan-editor/ExerciseEditor.tsx
git commit -m "feat(admin-ui): ExerciseEditor for inline PlanExercise editing"
```

---

### Task 21: `GroupEditor` — one ExerciseGroup with its exercises

**Files:**
- Create: `admin-ui/src/components/plan-editor/GroupEditor.tsx`

- [ ] **Step 1: Create the component**

```tsx
/**
 * Editor for a single ExerciseGroup inside a day.
 *
 * Shows group_type/order/rest controls on top, then one ExerciseEditor
 * per exercise plus an "Add exercise" button at the bottom.
 */
import { ExerciseEditor } from "./ExerciseEditor";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { components } from "@/lib/api.types";

type GroupDraft = components["schemas"]["ExerciseGroupAdminCreate"];
type ExerciseDraft = components["schemas"]["PlanExerciseAdminCreate"];

type Props = {
  value: GroupDraft;
  onChange: (next: GroupDraft) => void;
  onDelete: () => void;
};

const EMPTY_EXERCISE: ExerciseDraft = {
  exercise_id: 1,
  order: 1,
  sets: 3,
  reps: 10,
  weight: null,
  rpe_target: null,
  sets_json: null,
  notes: null,
};

export function GroupEditor({ value, onChange, onDelete }: Props) {
  const patch = (p: Partial<GroupDraft>) => onChange({ ...value, ...p });

  const updateExercise = (index: number, next: ExerciseDraft) => {
    patch({
      exercises: value.exercises.map((ex, i) => (i === index ? next : ex)),
    });
  };

  const deleteExercise = (index: number) => {
    patch({ exercises: value.exercises.filter((_, i) => i !== index) });
  };

  const addExercise = () => {
    const nextOrder = (value.exercises.at(-1)?.order ?? 0) + 1;
    patch({
      exercises: [
        ...value.exercises,
        { ...EMPTY_EXERCISE, order: nextOrder },
      ],
    });
  };

  return (
    <div className="rounded-md border bg-muted/30 p-3 space-y-3">
      <div className="grid grid-cols-[1fr_6rem_6rem_auto] gap-2 items-end">
        <div className="space-y-1">
          <Label className="text-xs">Group type</Label>
          <Input
            value={value.group_type}
            onChange={(e) => patch({ group_type: e.target.value })}
            placeholder="straight / superset / circuit"
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Order</Label>
          <Input
            type="number"
            value={value.order}
            onChange={(e) => patch({ order: Number(e.target.value) })}
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Rest (sec)</Label>
          <Input
            type="number"
            value={value.rest_after_group_sec}
            onChange={(e) =>
              patch({ rest_after_group_sec: Number(e.target.value) })
            }
          />
        </div>
        <Button type="button" size="sm" variant="ghost" onClick={onDelete}>
          Delete group
        </Button>
      </div>
      <div className="space-y-2">
        {value.exercises.map((ex, i) => (
          <ExerciseEditor
            key={i}
            value={ex}
            onChange={(next) => updateExercise(i, next)}
            onDelete={() => deleteExercise(i)}
          />
        ))}
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={addExercise}
        >
          + Add exercise to group
        </Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
cd admin-ui && npx tsc --noEmit && cd ..
git add admin-ui/src/components/plan-editor/GroupEditor.tsx
git commit -m "feat(admin-ui): GroupEditor for inline ExerciseGroup editing"
```

---

### Task 22: `DayAccordion` — one day with its own draft state + Save button

**Files:**
- Create: `admin-ui/src/components/plan-editor/DayAccordion.tsx`

This is where the draft-vs-saved distinction lives. The component takes the saved PlanDay as a prop, initializes a draft from it on mount, and calls a `onSaveDay(draft)` callback that the parent implements with the day endpoint.

- [ ] **Step 1: Create the component**

```tsx
/**
 * One day's editor — keeps a local draft of the day's nested contents
 * and bubbles "Save day" / "Delete day" up to the parent PlanDetailPage.
 *
 * The draft resets whenever the underlying server-fetched day changes
 * (via the useEffect below), so after a successful save the query
 * invalidation flows the fresh data back in.
 */
import { useEffect, useState } from "react";

import { GroupEditor } from "./GroupEditor";
import {
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { components } from "@/lib/api.types";

type PlanDay = components["schemas"]["PlanDayAdminResponse"];
type PlanDayUpdate = components["schemas"]["PlanDayAdminUpdate"];
type GroupDraft = components["schemas"]["ExerciseGroupAdminCreate"];

function dayToDraft(day: PlanDay): PlanDayUpdate {
  return {
    label: day.label,
    focus: day.focus,
    exercise_groups: day.exercise_groups.map((g) => ({
      group_type: g.group_type,
      order: g.order,
      rest_after_group_sec: g.rest_after_group_sec,
      exercises: g.exercises.map((ex) => ({
        exercise_id: ex.exercise_id,
        order: ex.order,
        sets: ex.sets,
        reps: ex.reps,
        weight: ex.weight,
        rpe_target: ex.rpe_target,
        sets_json: ex.sets_json as PlanDayUpdate["exercise_groups"][0]["exercises"][0]["sets_json"],
        notes: ex.notes,
      })),
    })),
  };
}

const EMPTY_GROUP: GroupDraft = {
  group_type: "straight",
  order: 1,
  rest_after_group_sec: 90,
  exercises: [],
};

type Props = {
  day: PlanDay;
  isSaving: boolean;
  onSave: (draft: PlanDayUpdate) => Promise<void>;
  onDelete: () => Promise<void>;
};

export function DayAccordion({ day, isSaving, onSave, onDelete }: Props) {
  const [draft, setDraft] = useState<PlanDayUpdate>(() => dayToDraft(day));

  useEffect(() => {
    setDraft(dayToDraft(day));
  }, [day]);

  const patch = (p: Partial<PlanDayUpdate>) =>
    setDraft((d) => ({ ...d, ...p }));

  const updateGroup = (index: number, next: GroupDraft) => {
    patch({
      exercise_groups: draft.exercise_groups.map((g, i) =>
        i === index ? next : g,
      ),
    });
  };

  const deleteGroup = (index: number) => {
    patch({
      exercise_groups: draft.exercise_groups.filter((_, i) => i !== index),
    });
  };

  const addGroup = () => {
    const nextOrder = (draft.exercise_groups.at(-1)?.order ?? 0) + 1;
    patch({
      exercise_groups: [
        ...draft.exercise_groups,
        { ...EMPTY_GROUP, order: nextOrder },
      ],
    });
  };

  return (
    <AccordionItem value={String(day.day_number)}>
      <AccordionTrigger className="px-3">
        <div className="flex-1 text-left">
          <span className="font-medium">Day {day.day_number}</span>
          <span className="text-muted-foreground"> — {day.label}</span>
          {day.focus && (
            <span className="text-muted-foreground"> — {day.focus}</span>
          )}
        </div>
      </AccordionTrigger>
      <AccordionContent className="px-3 space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <Label className="text-xs">Label</Label>
            <Input
              value={draft.label ?? ""}
              onChange={(e) => patch({ label: e.target.value })}
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Focus</Label>
            <Input
              value={draft.focus ?? ""}
              onChange={(e) => patch({ focus: e.target.value })}
            />
          </div>
        </div>
        <div className="space-y-3">
          {draft.exercise_groups.map((group, i) => (
            <GroupEditor
              key={i}
              value={group}
              onChange={(next) => updateGroup(i, next)}
              onDelete={() => deleteGroup(i)}
            />
          ))}
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={addGroup}
          >
            + Add exercise group
          </Button>
        </div>
        <div className="flex justify-end gap-2 pt-2 border-t">
          <Button
            type="button"
            variant="ghost"
            onClick={onDelete}
            disabled={isSaving}
          >
            Delete day
          </Button>
          <Button
            type="button"
            onClick={() => onSave(draft)}
            disabled={isSaving}
          >
            {isSaving ? "Saving…" : "Save day"}
          </Button>
        </div>
      </AccordionContent>
    </AccordionItem>
  );
}
```

- [ ] **Step 2: Commit**

```bash
cd admin-ui && npx tsc --noEmit && cd ..
git add admin-ui/src/components/plan-editor/DayAccordion.tsx
git commit -m "feat(admin-ui): DayAccordion with per-day draft state"
```

---

### Task 23: `PlanDetailPage` — route `/plans/:id`

**Files:**
- Create: `admin-ui/src/pages/PlanDetailPage.tsx`

- [ ] **Step 1: Create the page**

```tsx
/**
 * Plan detail page — the plans editor from spec §9.3.
 *
 * Top section: plan metadata (read-only summary with a link back to the
 * list for edits via EditSheet).
 * Middle section: per-day accordions with inline group/exercise/set
 * editing. Each day has its own Save button calling PUT /days/{n}.
 * Bottom: "Add day" button that opens a minimal prompt for the new
 * day_number/label and calls POST /days.
 */
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { DayAccordion } from "@/components/plan-editor/DayAccordion";
import { Accordion } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import type { components } from "@/lib/api.types";

type Plan = components["schemas"]["PlanAdminResponse"];
type PlanDayCreate = components["schemas"]["PlanDayAdminCreate"];
type PlanDayUpdate = components["schemas"]["PlanDayAdminUpdate"];
type PlanDayResponse = components["schemas"]["PlanDayAdminResponse"];

function planKey(id: number): (string | number)[] {
  return ["admin", "crud", "plans", "detail", id];
}

export function PlanDetailPage() {
  const params = useParams<{ id: string }>();
  const navigate = useNavigate();
  const planId = Number(params.id);
  const qc = useQueryClient();
  const [addDayOpen, setAddDayOpen] = useState(false);
  const [newDayNumber, setNewDayNumber] = useState("");
  const [newDayLabel, setNewDayLabel] = useState("");
  const [savingDayNumber, setSavingDayNumber] = useState<number | null>(null);

  const planQuery = useQuery({
    queryKey: planKey(planId),
    queryFn: () => api.get<Plan>(`/api/admin/plans/${planId}`),
    enabled: !Number.isNaN(planId),
  });

  const invalidatePlan = () => {
    qc.invalidateQueries({ queryKey: ["admin", "crud", "plans"] });
  };

  const saveDay = useMutation({
    mutationFn: async ({
      day_number,
      input,
    }: {
      day_number: number;
      input: PlanDayUpdate;
    }) =>
      api.put<PlanDayResponse>(
        `/api/admin/plans/${planId}/days/${day_number}`,
        input,
      ),
    onSuccess: () => {
      toast.success("Day saved");
      invalidatePlan();
      setSavingDayNumber(null);
    },
    onError: (e) => {
      toast.error((e as Error).message);
      setSavingDayNumber(null);
    },
  });

  const deleteDay = useMutation({
    mutationFn: async (day_number: number) =>
      api.delete(`/api/admin/plans/${planId}/days/${day_number}`),
    onSuccess: () => {
      toast.success("Day deleted");
      invalidatePlan();
    },
    onError: (e) => toast.error((e as Error).message),
  });

  const addDay = useMutation({
    mutationFn: async (input: PlanDayCreate) =>
      api.post<PlanDayResponse>(`/api/admin/plans/${planId}/days`, input),
    onSuccess: () => {
      toast.success("Day added");
      invalidatePlan();
      setAddDayOpen(false);
      setNewDayNumber("");
      setNewDayLabel("");
    },
    onError: (e) => toast.error((e as Error).message),
  });

  if (Number.isNaN(planId)) {
    return <div className="p-6">Invalid plan id.</div>;
  }

  if (planQuery.isLoading) {
    return <div className="p-6">Loading…</div>;
  }

  if (planQuery.isError || !planQuery.data) {
    return (
      <div className="p-6 space-y-2">
        <p>Failed to load plan.</p>
        <Button onClick={() => navigate("/plans")}>Back to list</Button>
      </div>
    );
  }

  const plan = planQuery.data;

  return (
    <div className="space-y-6 pb-12">
      <div className="flex items-start justify-between gap-4">
        <div>
          <button
            onClick={() => navigate("/plans")}
            className="text-sm text-muted-foreground hover:underline"
          >
            ← Back to plans
          </button>
          <h1 className="text-2xl font-semibold mt-1">
            {plan.name}{" "}
            <Badge variant={plan.status === "active" ? "default" : "secondary"}>
              {plan.status}
            </Badge>
          </h1>
          <p className="text-sm text-muted-foreground">
            User {plan.user_id} · {plan.split_type} · cycle length{" "}
            {plan.cycle_length}
            {plan.ai_generated ? " · AI-generated" : ""}
          </p>
        </div>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Days</h2>
          <Button size="sm" onClick={() => setAddDayOpen(true)}>
            + Add day
          </Button>
        </div>
        {plan.days.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No days yet. Add one to start building the plan.
          </p>
        ) : (
          <Accordion type="multiple" className="space-y-1">
            {[...plan.days]
              .sort((a, b) => a.day_number - b.day_number)
              .map((day) => (
                <DayAccordion
                  key={day.id}
                  day={day}
                  isSaving={
                    saveDay.isPending && savingDayNumber === day.day_number
                  }
                  onSave={async (draft) => {
                    setSavingDayNumber(day.day_number);
                    await saveDay.mutateAsync({
                      day_number: day.day_number,
                      input: draft,
                    });
                  }}
                  onDelete={async () => {
                    if (!confirm(`Delete Day ${day.day_number}?`)) return;
                    await deleteDay.mutateAsync(day.day_number);
                  }}
                />
              ))}
          </Accordion>
        )}
      </div>

      <Dialog open={addDayOpen} onOpenChange={setAddDayOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add day</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1">
              <Label>Day number</Label>
              <Input
                type="number"
                value={newDayNumber}
                onChange={(e) => setNewDayNumber(e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label>Label</Label>
              <Input
                value={newDayLabel}
                onChange={(e) => setNewDayLabel(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="ghost"
              onClick={() => setAddDayOpen(false)}
              disabled={addDay.isPending}
            >
              Cancel
            </Button>
            <Button
              onClick={() =>
                addDay.mutate({
                  day_number: Number(newDayNumber),
                  label: newDayLabel,
                  focus: "",
                  exercise_groups: [],
                })
              }
              disabled={
                addDay.isPending ||
                !newDayNumber ||
                !newDayLabel
              }
            >
              {addDay.isPending ? "Adding…" : "Add"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
```

- [ ] **Step 2: Verify it compiles**

```bash
cd admin-ui
npx tsc --noEmit
```

Expected: no errors. If there's a missing `Dialog` / `DialogContent` / `DialogFooter` / `DialogTitle` / `DialogHeader` export, check `src/components/ui/dialog.tsx` for the exact export names (should already exist from phase 2's shadcn installs).

- [ ] **Step 3: Commit**

```bash
cd ..
git add admin-ui/src/pages/PlanDetailPage.tsx
git commit -m "feat(admin-ui): PlanDetailPage with per-day editor"
```

---

### Task 24: Wire up the `/plans/:id` route

**Files:**
- Modify: `admin-ui/src/App.tsx`

- [ ] **Step 1: Add the detail route**

Open `admin-ui/src/App.tsx`. Add the import:

```tsx
import { PlanDetailPage } from "@/pages/PlanDetailPage";
```

Add the route right after the `<Route path="plans" ...>` line:

```tsx
<Route path="plans/:id" element={<PlanDetailPage />} />
```

- [ ] **Step 2: Build and verify no regressions**

```bash
cd admin-ui
npm run build
```

Expected: Vite build succeeds.

- [ ] **Step 3: Commit**

```bash
cd ..
git add admin-ui/src/App.tsx
git commit -m "feat(admin-ui): wire /plans/:id route to PlanDetailPage"
```

---

**End of Chunk 4.** The detail page is in place. All UI work is complete; the last chunk covers smoke testing and merging.

---

## Chunk 5: Smoke test and merge

### Task 25: Write the smoke test checklist

**Files:**
- Create: `docs/admin-dashboard-phase3-smoke-test.md`

- [ ] **Step 1: Create the checklist**

```markdown
# Phase 3 (Plans editor) smoke test

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
```

- [ ] **Step 2: Commit the checklist**

```bash
git add docs/admin-dashboard-phase3-smoke-test.md
git commit -m "docs(admin): phase 3 smoke test checklist"
```

---

### Task 26: Execute the smoke test

- [ ] **Step 1: Run through the checklist**

Open `docs/admin-dashboard-phase3-smoke-test.md` and tick every box. Any ❌ means stop, reopen the relevant task, fix, re-run the checklist from the top.

- [ ] **Step 2: Run the full backend suite one more time**

```bash
uv run pytest -q
```

Expected: green. If anything red, fix before merging.

- [ ] **Step 3: Mark the checklist as executed**

Append a line at the very top of `docs/admin-dashboard-phase3-smoke-test.md`:

```markdown
> Executed 2026-MM-DD — all checks ✅
```

(Replace the date with today's.)

- [ ] **Step 4: Commit**

```bash
git add docs/admin-dashboard-phase3-smoke-test.md
git commit -m "docs: phase 3 smoke test executed — all checks green"
```

---

### Task 27: Merge `feat/admin-dashboard-phase3` to main

- [ ] **Step 1: Verify the branch is clean**

```bash
git status
git log --oneline main..HEAD | wc -l
```

Expected: clean tree, ~25 commits ahead of main.

- [ ] **Step 2: Fast-forward merge into main (from the flexloop-server root, NOT the worktree)**

```bash
cd /Users/flyingchickens/Projects/FlexLoop/flexloop-server
git fetch
git checkout main
git merge --ff-only feat/admin-dashboard-phase3
```

Expected: fast-forward succeeds.

- [ ] **Step 3: Run the full test suite on main**

```bash
uv run pytest -q
```

Expected: green.

- [ ] **Step 4: Push main**

```bash
git push origin main
```

- [ ] **Step 5: Bump the parent FlexLoop submodule pointer**

```bash
cd /Users/flyingchickens/Projects/FlexLoop
git add flexloop-server
git commit -m "chore: bump flexloop-server to admin dashboard phase 3"
```

> Per memory: the parent FlexLoop repo has no remote, so no push needed.

- [ ] **Step 6: Clean up worktree and feature branch**

```bash
cd /Users/flyingchickens/Projects/FlexLoop/flexloop-server
git worktree remove /Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase3
git branch -d feat/admin-dashboard-phase3
```

- [ ] **Step 7: Update the auto-memory status file**

Edit `/Users/flyingchickens/.claude/projects/-Users-flyingchickens-Projects-FlexLoop/memory/project_admin_dashboard_status.md`:
- Mark Phase 3 as COMPLETE with today's date, pointer at this plan file.
- Move Phase 4 (AI tools) into the "next up" slot.
- Note: phase 4 still needs a plan file before execution.

---

**End of Chunk 5.** Phase 3 shipped. The admin dashboard now has a full Plans editor including the per-day atomic save workflow. Phase 4 (AI tools — config editor, prompt editor, playground) is next and will need its own plan file.

---

## Summary

**Backend deliverables:**
- `src/flexloop/admin/schemas/plans.py` — 9 schema classes (4 response + 2 plan-level write + 3 day-level write)
- `src/flexloop/admin/routers/plans.py` — 8 endpoints (standard CRUD + 3 day endpoints)
- `tests/test_admin_plans.py` — standard CRUD tests (auth, list, filter, search, detail, create, update, delete + cascade)
- `tests/test_admin_plans_days.py` — day endpoint tests (add/replace/delete with cascade verification)

**Frontend deliverables:**
- `admin-ui/src/components/ui/accordion.tsx` — new shadcn component
- `admin-ui/src/components/forms/PlanForm.tsx` — metadata-only rhf+zod form
- `admin-ui/src/components/plan-editor/` — 4 sub-components: `SetTargetsGrid`, `ExerciseEditor`, `GroupEditor`, `DayAccordion`
- `admin-ui/src/pages/PlansPage.tsx` — list page (create/edit metadata/delete)
- `admin-ui/src/pages/PlanDetailPage.tsx` — per-day accordion editor with atomic day saves
- `admin-ui/src/App.tsx` — two new routes (`/plans`, `/plans/:id`)
- `admin-ui/src/components/AppSidebar.tsx` — Plans sidebar item enabled
- `admin-ui/src/lib/api.types.ts` — regenerated

**Docs:** `docs/admin-dashboard-phase3-smoke-test.md`

**End state:** an operator can browse all plans, create a new empty plan, edit metadata (including via JSON escape hatch), and hand-edit any AI-generated plan's day/group/exercise/set structure via the detail page. The spec §17 acceptance criterion "navigate to every sidebar page including Plans" is now satisfied for phase 3 scope.
