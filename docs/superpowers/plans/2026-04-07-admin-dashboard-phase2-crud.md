# Admin Dashboard — Phase 2 (Boring CRUD) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land all "boring CRUD" admin pages — browse, create, edit, and delete every non-plan resource through the admin UI. End state: every sidebar item under "User Data", "Catalog", and the "AI Usage" entry is functional; an operator can sit down and edit any row in the database without touching SQL or the iOS client.

**Architecture:** Reusable `flexloop.admin.crud` pagination/sort/filter helpers on the backend; one router per resource (`users`, `workouts`, `measurements`, `prs`, `exercises`, `ai_usage`, `admin_users`) each following an identical 5-endpoint pattern (list, detail, create, update, delete). Shared frontend `useList/useDetail/useCreate/useUpdate/useDelete` hooks over TanStack Query; shared `<DataTable>`, `<EditSheet>`, `<DeleteDialog>` components. Each resource page is ~120 lines of glue. OpenAPI → TypeScript types are introduced in this phase so the frontend can't drift from the backend schemas.

**Tech Stack (new to phase 2):** No new backend dependencies. Frontend adds `openapi-typescript` (dev), and these shadcn/ui components: `table`, `alert-dialog`, `select`, `textarea`, `tabs`, `checkbox`, `badge`, `pagination`, `form`.

**Spec reference:** `docs/superpowers/specs/2026-04-06-admin-dashboard-design.md`. Read §6, §7, §9, §12.6, §14 (phase 2), and §17 before starting.

**Phase 1 already delivered** (do not redo): admin auth, CSRF middleware, Vite+React shell, AuthGate, sidebar with disabled phase-2 items, health endpoint + page, own-profile change-password + sessions pages. See `docs/superpowers/plans/2026-04-06-admin-dashboard-phase1-foundation.md`.

**Phase 3 (Plans editor) is out of scope for this plan.** The spec's §9.3 "Plan editor — special case" defers the nested Plan → PlanDay → ExerciseGroup → PlanExercise → sets_json editor to phase 3 because standard CRUD doesn't fit. The "Plans" sidebar item stays disabled in phase 2.

---

## Decisions locked in for this phase

These choices are fixed before implementation starts. Do not re-litigate them mid-execution — if a decision turns out to be wrong, stop and ask the user.

1. **Resources in scope (7):** `users`, `workouts`, `measurements`, `prs` (personal records), `exercises`, `ai_usage`, `admin_users`. Plans are phase 3.
2. **Every resource gets all five CRUD endpoints** (list, detail, create, update, delete), even `ai_usage` (which is a rollup table) — matches spec §9.1 "every boring resource gets the same shape". The UI can hide Create for `ai_usage` if it feels weird, but the endpoints exist.
3. **Audit-log writes are DEFERRED to phase 4.** Phase 1 created the `admin_audit_log` table but no helper. Phase 2 does not write to it. Spec §14 lists "Audit log writes for all config changes" under phase 4 — CRUD writes can be retrofitted there. Not introducing an unused helper in phase 2 keeps the surface area small.
4. **Hard delete with a simple confirm dialog.** The dialog shows the resource type + id and warns "This cannot be undone." It does NOT compute child-row counts (the spec's "will also delete 24 sets" message). Child-count computation is a nice-to-have and can be added later without changing the shared component's API.
5. **Generated TypeScript types via `openapi-typescript`.** Added as a dev dependency and a `codegen` npm script. Generated file lives at `admin-ui/src/lib/api.types.ts`. Hooks import types from there; the existing `admin-ui/src/lib/api.ts` fetch wrapper stays untouched. Running codegen is a manual step — the server must be running on `127.0.0.1:8000`. Documented in the phase 2 smoke test.
6. **Frontend test coverage: none added in phase 2.** Phase 1 did not install vitest; phase 2 does not either. Backend gets rigorous pytest coverage; frontend gets a manual smoke checklist (mirrors phase 1's approach per `docs/admin-dashboard-phase1-smoke-test.md`). Adding vitest is a scope creep we'll revisit after phase 5.
7. **JSON escape hatch** (spec §9.4): implemented as a second tab ("JSON") inside `<EditSheet>` alongside the "Form" tab. It's a read/write `<Textarea>` over `JSON.stringify(row, null, 2)`; on Save it `JSON.parse`s and submits as the update body. No fancy JSON editor library (decision from spec §15 open question 4).
8. **Filter query param format:** `?filter[user_id]=4&filter[type]=weight` — parsed by a helper on the backend. Python's `fastapi.Request.query_params` is a multidict; the helper reads keys matching `filter[...]` and returns a dict. No custom Pydantic validator.
9. **Sort query param format:** `?sort=created_at:desc,name:asc` — comma-separated, per the spec.
10. **Branch strategy:** Per branch-strategy memory, this is a large plan-driven session. Execute from a worktree at `/Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase2` on feature branch `feat/admin-dashboard-phase2`. Merge back to `main` fast-forward when all chunks are green.
11. **Strict schemas.** Every `*AdminCreate` and `*AdminUpdate` schema MUST include `model_config = ConfigDict(extra="forbid")` to reject unknown fields at validation time. Without this, typos in partial-update payloads like `{"nmae": "x"}` silently succeed via `exclude_unset=True` and the UI reports "saved" with no change. `*AdminResponse` schemas use `from_attributes=True` instead (they read from ORM rows). If a schema needs both, use `ConfigDict(extra="forbid", from_attributes=True)`.

---

## File Structure

New files and modifications for phase 2. All paths relative to `flexloop-server/`.

**Backend — new `flexloop.admin.crud` module:**
```
src/flexloop/admin/
├── crud.py                         NEW — pagination, sort, filter helpers
└── routers/
    ├── users.py                    NEW — /api/admin/users CRUD
    ├── workouts.py                 NEW — /api/admin/workouts CRUD
    ├── measurements.py             NEW — /api/admin/measurements CRUD
    ├── prs.py                      NEW — /api/admin/prs CRUD
    ├── exercises.py                NEW — /api/admin/exercises CRUD
    ├── ai_usage.py                 NEW — /api/admin/ai/usage CRUD
    └── admin_users.py              NEW — /api/admin/admin-users CRUD
```

**Backend — new Pydantic schemas (one file per resource under `admin/`):**
```
src/flexloop/admin/schemas/
├── __init__.py                     NEW
├── common.py                       NEW — PaginatedResponse, ListQueryParams
├── users.py                        NEW — AdminUserCreate, AdminUserUpdate, AdminUserResponse (for end-user User table)
├── workouts.py                     NEW
├── measurements.py                 NEW
├── prs.py                          NEW
├── exercises.py                    NEW
├── ai_usage.py                     NEW
└── admin_users.py                  NEW — AdminAdminUserCreate etc. (for the admin_users table)
```

> Schemas live under `flexloop.admin.schemas` rather than the existing `flexloop.schemas/` to keep admin DTOs separate from iOS-facing DTOs. The iOS ones return minimal fields; the admin ones return everything. Mixing them in one file invites accidental field exposure to the iOS client.

**Backend — modified:**
```
src/flexloop/main.py                add 7 include_router() calls + imports
```

**Backend — tests:**
```
tests/
├── test_admin_crud_helpers.py      NEW — paginated_response + sort/filter parsers
├── test_admin_users.py             NEW — /api/admin/users integration
├── test_admin_workouts.py          NEW
├── test_admin_measurements.py      NEW
├── test_admin_prs.py               NEW
├── test_admin_exercises.py         NEW
├── test_admin_ai_usage.py          NEW
└── test_admin_admin_users.py       NEW
```

**Frontend — new shared infrastructure:**
```
admin-ui/
├── package.json                    add openapi-typescript dev dep + codegen script
└── src/
    ├── lib/
    │   ├── api.types.ts            NEW — generated from openapi.json (.gitignored? no — commit it)
    │   └── crud.ts                 NEW — CRUD helper types (ListResponse<T>, ListParams)
    ├── hooks/
    │   └── useCrud.ts              NEW — useList, useDetail, useCreate, useUpdate, useDelete (generic)
    └── components/
        ├── DataTable.tsx           NEW — shared table with sorting, pagination, search
        ├── EditSheet.tsx           NEW — slide-out drawer with Form + JSON tabs
        ├── DeleteDialog.tsx        NEW — confirm delete AlertDialog
        ├── JsonEditor.tsx          NEW — textarea-based JSON tab
        └── ui/                     add shadcn: table, alert-dialog, select, textarea, tabs, checkbox, badge, pagination, form
```

**Frontend — new resource pages (one file per resource):**
```
admin-ui/src/pages/
├── UsersPage.tsx                   NEW — list + edit sheet
├── WorkoutsPage.tsx                NEW
├── MeasurementsPage.tsx            NEW
├── PRsPage.tsx                     NEW
├── ExercisesPage.tsx               NEW
├── AIUsagePage.tsx                 NEW
└── AdminUsersPage.tsx              NEW
```

**Frontend — per-resource forms (hand-written react-hook-form + zod):**
```
admin-ui/src/components/forms/
├── UserForm.tsx                    NEW
├── WorkoutForm.tsx                 NEW
├── MeasurementForm.tsx             NEW
├── PRForm.tsx                      NEW
├── ExerciseForm.tsx                NEW
├── AIUsageForm.tsx                 NEW
└── AdminUserForm.tsx               NEW
```

> Forms live in their own folder, not alongside pages, because they are used by the page AND by the `<EditSheet>`'s Form tab. Keeping them separate makes the import graph obvious.

**Frontend — modified:**
```
admin-ui/src/
├── App.tsx                         add 7 routes under AppShell
└── components/AppSidebar.tsx       flip disabled:false on 6 items
```

**Docs:**
```
docs/admin-dashboard-phase2-smoke-test.md   NEW — manual smoke checklist
```

---

## Execution setup

Run these commands once before starting Chunk 1:

```bash
cd /Users/flyingchickens/Projects/FlexLoop/flexloop-server
git worktree add /Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase2 -b feat/admin-dashboard-phase2
cd /Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase2
uv sync
cd admin-ui && npm install && cd ..
```

All file paths in the tasks below are relative to `/Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase2/`.

---

## Chunk 1: Backend Foundation — CRUD Helpers and Schemas

This chunk builds the reusable `flexloop.admin.crud` module plus the shared admin schemas package. No routes get mounted yet — this is pure infrastructure. Chunk 2 uses it to stand up the first full resource router.

### Task 1: Create `flexloop.admin.crud` — sort parser

**Files:**
- Create: `src/flexloop/admin/crud.py`
- Create: `tests/test_admin_crud_helpers.py`

The sort parser takes a string like `"created_at:desc,name:asc"` and a whitelist of allowed column names, and returns a list of SQLAlchemy `ColumnElement` order-by clauses. Invalid columns raise `HTTPException(400)`. Invalid directions default to `asc` silently (lenient on direction, strict on columns).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_admin_crud_helpers.py`:

```python
"""Tests for flexloop.admin.crud helpers."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import DeclarativeBase

from flexloop.admin.crud import parse_sort_spec


# Use a real DeclarativeBase — bare ``Column()`` objects on a plain class
# don't get a ``.key`` assigned, so the ORDER BY rendering would come out
# as ``"<name unknown>" ASC`` and the column-name assertions would pass
# only by accident.
class _FakeBase(DeclarativeBase):
    pass


class _FakeModel(_FakeBase):
    __tablename__ = "_fake_model"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    created_at = Column(String)  # type doesn't matter for sort tests


class TestParseSortSpec:
    def test_single_column_asc(self) -> None:
        clauses = parse_sort_spec("name:asc", model=_FakeModel, allowed={"name"})
        assert len(clauses) == 1
        # The ORDER BY rendering contains "name ASC"
        assert "name" in str(clauses[0]).lower()
        assert "asc" in str(clauses[0]).lower()

    def test_single_column_desc(self) -> None:
        clauses = parse_sort_spec("created_at:desc", model=_FakeModel, allowed={"created_at"})
        assert "desc" in str(clauses[0]).lower()

    def test_multiple_columns_preserve_order(self) -> None:
        clauses = parse_sort_spec(
            "created_at:desc,name:asc",
            model=_FakeModel,
            allowed={"created_at", "name"},
        )
        assert len(clauses) == 2
        assert "created_at" in str(clauses[0]).lower()
        assert "name" in str(clauses[1]).lower()

    def test_missing_direction_defaults_to_asc(self) -> None:
        clauses = parse_sort_spec("name", model=_FakeModel, allowed={"name"})
        assert "asc" in str(clauses[0]).lower()

    def test_unknown_column_raises_400(self) -> None:
        with pytest.raises(HTTPException) as exc:
            parse_sort_spec("bogus:desc", model=_FakeModel, allowed={"name"})
        assert exc.value.status_code == 400
        assert "bogus" in exc.value.detail.lower()

    def test_empty_string_returns_empty_list(self) -> None:
        clauses = parse_sort_spec("", model=_FakeModel, allowed={"name"})
        assert clauses == []

    def test_none_returns_empty_list(self) -> None:
        clauses = parse_sort_spec(None, model=_FakeModel, allowed={"name"})
        assert clauses == []

    def test_whitespace_tolerated(self) -> None:
        clauses = parse_sort_spec(" name : asc , created_at : desc ", model=_FakeModel, allowed={"name", "created_at"})
        assert len(clauses) == 2

    def test_direction_case_insensitive(self) -> None:
        clauses = parse_sort_spec("name:DESC", model=_FakeModel, allowed={"name"})
        assert "desc" in str(clauses[0]).lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_admin_crud_helpers.py -v`
Expected: ImportError / ModuleNotFoundError on `from flexloop.admin.crud import parse_sort_spec` (module doesn't exist yet).

- [ ] **Step 3: Write the minimal implementation**

Create `src/flexloop/admin/crud.py`:

```python
"""Reusable CRUD helpers for admin resource routers.

Every admin resource router follows the same pattern:
- GET /api/admin/{resource}           → list with pagination/sort/filter/search
- GET /api/admin/{resource}/{id}       → detail
- POST /api/admin/{resource}           → create
- PUT /api/admin/{resource}/{id}       → update
- DELETE /api/admin/{resource}/{id}    → delete

This module provides the shared building blocks so each router only has to
supply the model class, the schemas, and its whitelists.
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import ColumnElement
from sqlalchemy.orm import InstrumentedAttribute


def parse_sort_spec(
    spec: str | None,
    *,
    model: Any,
    allowed: set[str],
) -> list[ColumnElement[Any]]:
    """Parse a sort spec like 'created_at:desc,name:asc' into ORDER BY clauses.

    Args:
        spec: The raw ?sort=... query string value. None or "" returns [].
        model: The SQLAlchemy model class whose columns are being sorted on.
        allowed: Whitelist of column names the caller permits sorting on.

    Returns:
        A list of SQLAlchemy ColumnElement order-by clauses, in the order
        they appeared in the spec.

    Raises:
        HTTPException(400) if a requested column is not in `allowed`.
    """
    if not spec:
        return []

    clauses: list[ColumnElement[Any]] = []
    for raw in spec.split(","):
        raw = raw.strip()
        if not raw:
            continue
        if ":" in raw:
            col_name, _, direction = raw.partition(":")
            col_name = col_name.strip()
            direction = direction.strip().lower()
        else:
            col_name = raw
            direction = "asc"

        if col_name not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Sort column '{col_name}' is not allowed. Allowed: {sorted(allowed)}",
            )

        column: InstrumentedAttribute[Any] = getattr(model, col_name)
        if direction == "desc":
            clauses.append(column.desc())
        else:
            clauses.append(column.asc())

    return clauses
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_admin_crud_helpers.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add src/flexloop/admin/crud.py tests/test_admin_crud_helpers.py
git commit -m "feat(admin): add parse_sort_spec helper for CRUD list endpoints"
```

---

### Task 2: Add `parse_filter_params` to `crud.py`

**Files:**
- Modify: `src/flexloop/admin/crud.py`
- Modify: `tests/test_admin_crud_helpers.py`

Parses `filter[key]=value` query params from a FastAPI `Request` into a `dict[str, str]`, enforcing a whitelist. Values are returned as raw strings — type coercion is the caller's job because filters like `user_id` (int) and `type` (str) have different coercion rules.

- [ ] **Step 1: Append failing tests**

Append to `tests/test_admin_crud_helpers.py`:

```python
from starlette.datastructures import QueryParams

from flexloop.admin.crud import parse_filter_params


class TestParseFilterParams:
    def test_extracts_filter_brackets(self) -> None:
        qp = QueryParams("filter[user_id]=4&filter[type]=weight&page=1")
        result = parse_filter_params(qp, allowed={"user_id", "type"})
        assert result == {"user_id": "4", "type": "weight"}

    def test_ignores_non_filter_params(self) -> None:
        qp = QueryParams("page=1&per_page=50&sort=name:asc")
        result = parse_filter_params(qp, allowed={"user_id"})
        assert result == {}

    def test_unknown_filter_key_raises_400(self) -> None:
        qp = QueryParams("filter[secret]=1")
        with pytest.raises(HTTPException) as exc:
            parse_filter_params(qp, allowed={"user_id"})
        assert exc.value.status_code == 400
        assert "secret" in exc.value.detail.lower()

    def test_empty_allowed_rejects_all(self) -> None:
        qp = QueryParams("filter[anything]=x")
        with pytest.raises(HTTPException):
            parse_filter_params(qp, allowed=set())

    def test_empty_query_returns_empty_dict(self) -> None:
        qp = QueryParams("")
        assert parse_filter_params(qp, allowed={"user_id"}) == {}

    def test_malformed_key_ignored(self) -> None:
        """filter_without_brackets=1 is not a 'filter[...]' param."""
        qp = QueryParams("filter_user_id=4")
        assert parse_filter_params(qp, allowed={"user_id"}) == {}
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_admin_crud_helpers.py::TestParseFilterParams -v`
Expected: ImportError on `parse_filter_params`.

- [ ] **Step 3: Add the implementation**

Append the function body to `src/flexloop/admin/crud.py`, then hoist the new import to the top of the file next to the existing imports (the concatenation would otherwise leave the import mid-file):

```python
# Add to the top-of-file import block:
from starlette.datastructures import QueryParams


# Add after the existing parse_sort_spec function:
def parse_filter_params(
    query_params: QueryParams,
    *,
    allowed: set[str],
) -> dict[str, str]:
    """Extract ``filter[key]=value`` query params into a whitelisted dict.

    Only keys of the form ``filter[name]`` are considered. Keys whose ``name``
    is not in ``allowed`` cause a 400. Values are returned as raw strings;
    callers coerce to the appropriate SQLAlchemy column type.

    Args:
        query_params: Starlette ``QueryParams`` from ``request.query_params``.
        allowed: Whitelist of filter names the caller permits.

    Returns:
        A dict mapping filter name → string value.

    Raises:
        HTTPException(400) if an unknown filter key is present.
    """
    result: dict[str, str] = {}
    for key, value in query_params.items():
        if not (key.startswith("filter[") and key.endswith("]")):
            continue
        name = key[len("filter[") : -1]
        if name not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Filter '{name}' is not allowed. Allowed: {sorted(allowed)}",
            )
        result[name] = value
    return result
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_admin_crud_helpers.py -v`
Expected: 15 passed (9 sort + 6 filter).

- [ ] **Step 5: Commit**

```bash
git add src/flexloop/admin/crud.py tests/test_admin_crud_helpers.py
git commit -m "feat(admin): add parse_filter_params helper"
```

---

### Task 3: Add `paginated_response` to `crud.py`

**Files:**
- Modify: `src/flexloop/admin/crud.py`
- Modify: `tests/test_admin_crud_helpers.py`

Takes a SQLAlchemy `Select` query, pagination params, and an item schema class. Returns a dict matching the spec's standard response shape: `{items, total, page, per_page, total_pages}`. This is the only piece of the helper module that touches the DB, so it's async.

- [ ] **Step 1: Append failing tests**

Append to `tests/test_admin_crud_helpers.py`:

```python
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.crud import paginated_response
from flexloop.models.user import User


# Inline test schema — keeps this task independent of any resource-level
# schemas defined in later tasks. We only validate the couple of fields
# we assert on.
class _RowSchemaForTests(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class TestPaginatedResponse:
    async def test_empty_table(self, db_session: AsyncSession) -> None:
        query = select(User)
        result = await paginated_response(
            db_session,
            query=query,
            item_schema=_RowSchemaForTests,
            page=1,
            per_page=50,
        )
        assert result == {
            "items": [],
            "total": 0,
            "page": 1,
            "per_page": 50,
            "total_pages": 0,
        }

    async def test_first_page_partial(self, db_session: AsyncSession) -> None:
        for i in range(3):
            db_session.add(User(
                name=f"U{i}", gender="other", age=30, height=180, weight=80,
                weight_unit="kg", height_unit="cm", experience_level="intermediate",
                goals="stay fit", available_equipment=[],
            ))
        await db_session.commit()

        query = select(User).order_by(User.id)
        result = await paginated_response(
            db_session, query=query, item_schema=_RowSchemaForTests, page=1, per_page=50,
        )
        assert result["total"] == 3
        assert result["page"] == 1
        assert result["per_page"] == 50
        assert result["total_pages"] == 1
        assert len(result["items"]) == 3
        assert result["items"][0].name == "U0"

    async def test_second_page(self, db_session: AsyncSession) -> None:
        for i in range(5):
            db_session.add(User(
                name=f"U{i}", gender="other", age=30, height=180, weight=80,
                weight_unit="kg", height_unit="cm", experience_level="intermediate",
                goals="stay fit", available_equipment=[],
            ))
        await db_session.commit()

        query = select(User).order_by(User.id)
        result = await paginated_response(
            db_session, query=query, item_schema=_RowSchemaForTests, page=2, per_page=2,
        )
        assert result["total"] == 5
        assert result["page"] == 2
        assert result["per_page"] == 2
        assert result["total_pages"] == 3
        assert len(result["items"]) == 2
        assert result["items"][0].name == "U2"
        assert result["items"][1].name == "U3"

    async def test_page_out_of_range_returns_empty_items(self, db_session: AsyncSession) -> None:
        db_session.add(User(
            name="only", gender="other", age=30, height=180, weight=80,
            weight_unit="kg", height_unit="cm", experience_level="intermediate",
            goals="stay fit", available_equipment=[],
        ))
        await db_session.commit()

        query = select(User)
        result = await paginated_response(
            db_session, query=query, item_schema=_RowSchemaForTests, page=99, per_page=10,
        )
        assert result["total"] == 1
        assert result["items"] == []
```

> The `db_session` fixture comes from `tests/conftest.py` (phase 1). The `pyproject.toml` has `asyncio_mode = "auto"` under `[tool.pytest.ini_options]`, so async tests are collected and run automatically — no `@pytest.mark.asyncio` decorator needed.

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_admin_crud_helpers.py::TestPaginatedResponse -v`
Expected: ImportError on `paginated_response`.

- [ ] **Step 3: Add the implementation**

Append the function body to `src/flexloop/admin/crud.py`, then hoist the new imports to the top of the file alongside the existing ones — the `TypeVar` aliased to `SchemaT` must live near the top so `parse_filter_params` (defined above) can't end up visually sandwiched between import blocks.

```python
# Add to the top-of-file import block:
from typing import TypeVar

from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Add near the top-level type aliases (below the imports):
SchemaT = TypeVar("SchemaT", bound=BaseModel)


# Add the function after parse_filter_params:
async def paginated_response(
    db: AsyncSession,
    *,
    query: Select[Any],
    item_schema: type[SchemaT],
    page: int,
    per_page: int,
) -> dict[str, Any]:
    """Run a list query with pagination and wrap the result in the standard shape.

    The caller builds the ``query`` with whatever ``.where()``/``.order_by()``
    clauses it wants. This helper:
      1. Runs a ``SELECT COUNT(*)`` over the same filters to produce ``total``.
      2. Applies ``LIMIT``/``OFFSET`` based on ``page``/``per_page``.
      3. Runs the paginated query.
      4. Validates each row through ``item_schema``.

    The returned dict matches spec §9.1:
        ``{items, total, page, per_page, total_pages}``

    Pydantic models (the ``items``) are returned as model instances, not dicts —
    FastAPI serializes them through the endpoint's response_model. If the caller
    wants dicts, they can dump after.
    """
    # Total count: wrap the query as a subquery so any WHERE clauses stay.
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total: int = total_result.scalar_one()

    # Page slice
    offset = (page - 1) * per_page
    page_query = query.offset(offset).limit(per_page)
    page_result = await db.execute(page_query)
    rows = page_result.scalars().all()
    items = [item_schema.model_validate(row, from_attributes=True) for row in rows]

    total_pages = (total + per_page - 1) // per_page if per_page > 0 else 0

    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
    }
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_admin_crud_helpers.py -v`
Expected: 19 passed (9 sort + 6 filter + 4 pagination).

- [ ] **Step 5: Commit**

```bash
git add src/flexloop/admin/crud.py tests/test_admin_crud_helpers.py
git commit -m "feat(admin): add paginated_response helper"
```

---

### Task 4: Create admin schemas package + common list params schema

**Files:**
- Create: `src/flexloop/admin/schemas/__init__.py`
- Create: `src/flexloop/admin/schemas/common.py`

`common.py` holds the reusable `ListQueryParams` (for `Depends()` injection) and `PaginatedResponse[T]` generic response model. Every list endpoint imports from here.

- [ ] **Step 1: Create the package**

Create `src/flexloop/admin/schemas/__init__.py` (empty file, just a newline).

- [ ] **Step 2: Create `common.py`**

Create `src/flexloop/admin/schemas/common.py`:

```python
"""Shared schemas for admin CRUD list/detail endpoints."""
from __future__ import annotations

from typing import Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel, Field

T = TypeVar("T")

MAX_PER_PAGE = 200


class ListQueryParams(BaseModel):
    """Standard list query params injected via ``Depends()`` on every list endpoint.

    Filter params (``filter[key]=value``) are NOT in this model — they're
    parsed directly from ``request.query_params`` by ``parse_filter_params``
    because FastAPI's query-param parser doesn't handle bracket syntax natively.
    """
    page: int = Field(1, ge=1)
    per_page: int = Field(50, ge=1, le=MAX_PER_PAGE)
    search: str | None = None
    sort: str | None = None

    @classmethod
    def as_dependency(
        cls,
        page: int = Query(1, ge=1),
        per_page: int = Query(50, ge=1, le=MAX_PER_PAGE),
        search: str | None = Query(None),
        sort: str | None = Query(None),
    ) -> "ListQueryParams":
        """Call this via ``Depends(ListQueryParams.as_dependency)`` to get one instance."""
        return cls(page=page, per_page=per_page, search=search, sort=sort)


class PaginatedResponse(BaseModel, Generic[T]):
    """Standard list response shape. Matches spec §9.1."""
    items: list[T]
    total: int
    page: int
    per_page: int
    total_pages: int
```

- [ ] **Step 3: Sanity import check**

Run: `uv run python -c "from flexloop.admin.schemas.common import ListQueryParams, PaginatedResponse; print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add src/flexloop/admin/schemas/__init__.py src/flexloop/admin/schemas/common.py
git commit -m "feat(admin): add common list query params + paginated response schemas"
```

---

### Task 5: Create users resource schemas

**Files:**
- Create: `src/flexloop/admin/schemas/users.py`

Schemas for the end-user `User` table (NOT the admin_users table — that's Task 20 in Chunk 2). Every field is included because admins see everything; no field masking.

- [ ] **Step 1: Create the file**

Create `src/flexloop/admin/schemas/users.py`:

```python
"""Admin CRUD schemas for the end-user ``User`` table.

Distinct from ``flexloop.schemas.user`` — those are iOS-facing DTOs which
intentionally expose only a subset of fields. Admin callers see everything
including internal timestamps and full raw JSON columns.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserAdminResponse(BaseModel):
    """Full user row as seen by the admin dashboard."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    gender: str
    age: int
    height: float
    weight: float
    weight_unit: str
    height_unit: str
    experience_level: str
    goals: str
    available_equipment: list[str] | None
    created_at: datetime


class UserAdminCreate(BaseModel):
    """Payload for POST /api/admin/users."""
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    gender: str = Field(min_length=1, max_length=20)
    age: int = Field(ge=0, le=150)
    height: float = Field(gt=0)
    weight: float = Field(gt=0)
    weight_unit: str = "kg"
    height_unit: str = "cm"
    experience_level: str = Field(min_length=1, max_length=20)
    goals: str = Field(default="", max_length=500)
    available_equipment: list[str] | None = None


class UserAdminUpdate(BaseModel):
    """Payload for PUT /api/admin/users/{id}. All fields optional — partial update."""
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    gender: str | None = Field(default=None, min_length=1, max_length=20)
    age: int | None = Field(default=None, ge=0, le=150)
    height: float | None = Field(default=None, gt=0)
    weight: float | None = Field(default=None, gt=0)
    weight_unit: str | None = None
    height_unit: str | None = None
    experience_level: str | None = Field(default=None, min_length=1, max_length=20)
    goals: str | None = Field(default=None, max_length=500)
    available_equipment: list[str] | None = None
```

- [ ] **Step 2: Sanity import check**

Run: `uv run python -c "from flexloop.admin.schemas.users import UserAdminResponse, UserAdminCreate, UserAdminUpdate; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add src/flexloop/admin/schemas/users.py
git commit -m "feat(admin): add users resource schemas (create/update/response)"
```

---

**End of Chunk 1.** The backend now has:
- `flexloop.admin.crud` with 3 helpers (sort parser, filter parser, paginated response) — ~19 unit tests.
- `flexloop.admin.schemas` package with `common.py` (ListQueryParams, PaginatedResponse) and `users.py`.

No routes are mounted yet. That happens in Chunk 2.

---

## Chunk 2: Users Router — Full CRUD

This chunk delivers the canonical resource router for the end-user `User` table. Every subsequent resource router (Chunk 3) is a ~80-line copy of this one with different models, filters, and schemas — so this chunk doubles as the template.

### Task 6: Users router — list + detail endpoints

**Files:**
- Create: `src/flexloop/admin/routers/users.py`
- Create: `tests/test_admin_users.py`

This task delivers the two read endpoints. Create/update/delete are added in Tasks 7-9 so each test file stays focused and the TDD cycles stay small.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_admin_users.py`:

```python
"""Integration tests for /api/admin/users."""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import SESSION_COOKIE_NAME, create_session, hash_password
from flexloop.models.admin_user import AdminUser
from flexloop.models.user import User


async def _make_admin_and_cookie(db: AsyncSession) -> dict[str, str]:
    """Create an admin user + session; return a cookie dict usable on httpx client."""
    admin = AdminUser(username="tester", password_hash=hash_password("password123"))
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    token, _ = await create_session(db, admin_user_id=admin.id)
    return {SESSION_COOKIE_NAME: token}


async def _seed_users(db: AsyncSession, n: int) -> list[User]:
    users = [
        User(
            name=f"User{i}", gender="other", age=20 + i, height=170.0, weight=70.0,
            weight_unit="kg", height_unit="cm", experience_level="intermediate",
            goals="stay fit", available_equipment=["barbell"],
        )
        for i in range(n)
    ]
    db.add_all(users)
    await db.commit()
    for u in users:
        await db.refresh(u)
    return users


class TestListUsers:
    async def test_requires_auth(self, client: AsyncClient) -> None:
        res = await client.get("/api/admin/users")
        assert res.status_code == 401

    async def test_empty_list(self, client: AsyncClient, db_session: AsyncSession) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.get("/api/admin/users", cookies=cookies)
        assert res.status_code == 200
        body = res.json()
        assert body == {"items": [], "total": 0, "page": 1, "per_page": 50, "total_pages": 0}

    async def test_returns_seeded_users(self, client: AsyncClient, db_session: AsyncSession) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        await _seed_users(db_session, 3)
        res = await client.get("/api/admin/users", cookies=cookies)
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 3
        assert len(body["items"]) == 3
        assert body["items"][0]["name"] == "User0"
        assert "available_equipment" in body["items"][0]

    async def test_pagination(self, client: AsyncClient, db_session: AsyncSession) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        await _seed_users(db_session, 5)
        res = await client.get("/api/admin/users?page=2&per_page=2", cookies=cookies)
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 5
        assert body["total_pages"] == 3
        assert len(body["items"]) == 2
        assert body["items"][0]["name"] == "User2"

    async def test_search_by_name(self, client: AsyncClient, db_session: AsyncSession) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        await _seed_users(db_session, 3)
        res = await client.get("/api/admin/users?search=User1", cookies=cookies)
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 1
        assert body["items"][0]["name"] == "User1"

    async def test_sort_name_desc(self, client: AsyncClient, db_session: AsyncSession) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        await _seed_users(db_session, 3)
        res = await client.get("/api/admin/users?sort=name:desc", cookies=cookies)
        assert res.status_code == 200
        names = [u["name"] for u in res.json()["items"]]
        assert names == ["User2", "User1", "User0"]

    async def test_bogus_sort_column_rejected(self, client: AsyncClient, db_session: AsyncSession) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.get("/api/admin/users?sort=password:asc", cookies=cookies)
        assert res.status_code == 400

    async def test_filter_experience_level(self, client: AsyncClient, db_session: AsyncSession) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        db_session.add(User(
            name="Beginner Bob", gender="m", age=25, height=180, weight=80,
            weight_unit="kg", height_unit="cm", experience_level="beginner",
            goals="start lifting", available_equipment=[],
        ))
        db_session.add(User(
            name="Advanced Alice", gender="f", age=30, height=170, weight=60,
            weight_unit="kg", height_unit="cm", experience_level="advanced",
            goals="compete", available_equipment=[],
        ))
        await db_session.commit()
        res = await client.get(
            "/api/admin/users?filter[experience_level]=beginner",
            cookies=cookies,
        )
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 1
        assert body["items"][0]["name"] == "Beginner Bob"

    async def test_bogus_filter_rejected(self, client: AsyncClient, db_session: AsyncSession) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.get("/api/admin/users?filter[secret]=1", cookies=cookies)
        assert res.status_code == 400


class TestGetUserDetail:
    async def test_requires_auth(self, client: AsyncClient) -> None:
        res = await client.get("/api/admin/users/1")
        assert res.status_code == 401

    async def test_returns_user(self, client: AsyncClient, db_session: AsyncSession) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        users = await _seed_users(db_session, 1)
        res = await client.get(f"/api/admin/users/{users[0].id}", cookies=cookies)
        assert res.status_code == 200
        assert res.json()["id"] == users[0].id
        assert res.json()["name"] == "User0"

    async def test_404_on_missing(self, client: AsyncClient, db_session: AsyncSession) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.get("/api/admin/users/99999", cookies=cookies)
        assert res.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_admin_users.py -v`
Expected: 404s on every call — router not mounted yet, so all routes return "Not Found".

- [ ] **Step 3: Write the users router (list + detail only)**

Create `src/flexloop/admin/routers/users.py`:

```python
"""Admin CRUD endpoints for the end-user ``User`` table."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import require_admin
from flexloop.admin.crud import (
    paginated_response,
    parse_filter_params,
    parse_sort_spec,
)
from flexloop.admin.schemas.common import ListQueryParams, PaginatedResponse
from flexloop.admin.schemas.users import (
    UserAdminCreate,
    UserAdminResponse,
    UserAdminUpdate,
)
from flexloop.db.engine import get_session
from flexloop.models.user import User

router = APIRouter(prefix="/api/admin/users", tags=["admin:users"])

ALLOWED_SORT_COLUMNS = {"id", "name", "age", "experience_level", "created_at"}
ALLOWED_FILTER_COLUMNS = {"experience_level", "gender"}
SEARCH_COLUMNS = (User.name, User.goals)


@router.get("", response_model=PaginatedResponse[UserAdminResponse])
async def list_users(
    request: Request,
    params: ListQueryParams = Depends(ListQueryParams.as_dependency),
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> dict:
    query = select(User)

    # Filters
    filters = parse_filter_params(request.query_params, allowed=ALLOWED_FILTER_COLUMNS)
    for key, value in filters.items():
        query = query.where(getattr(User, key) == value)

    # Search — OR over SEARCH_COLUMNS with ILIKE
    if params.search:
        like = f"%{params.search}%"
        query = query.where(or_(*(col.ilike(like) for col in SEARCH_COLUMNS)))

    # Sort — default to id asc so tests are deterministic
    sort_clauses = parse_sort_spec(params.sort, model=User, allowed=ALLOWED_SORT_COLUMNS)
    if sort_clauses:
        query = query.order_by(*sort_clauses)
    else:
        query = query.order_by(User.id.asc())

    return await paginated_response(
        db,
        query=query,
        item_schema=UserAdminResponse,
        page=params.page,
        per_page=params.per_page,
    )


@router.get("/{user_id}", response_model=UserAdminResponse)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    return user
```

- [ ] **Step 4: Wire the router into main.py**

Modify `src/flexloop/main.py` — add an import and an `include_router` call alongside the phase 1 admin router registrations:

```python
# near the other admin router imports
from flexloop.admin.routers.users import router as admin_users_router

# near the other include_router calls for admin routers
app.include_router(admin_users_router)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_admin_users.py -v`
Expected: 12 passed (9 list + 3 detail).

- [ ] **Step 6: Commit**

```bash
git add src/flexloop/admin/routers/users.py src/flexloop/main.py tests/test_admin_users.py
git commit -m "feat(admin): users list + detail endpoints"
```

---

### Task 7: Users router — create endpoint

**Files:**
- Modify: `src/flexloop/admin/routers/users.py`
- Modify: `tests/test_admin_users.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_admin_users.py`:

```python
class TestCreateUser:
    async def test_requires_auth(self, client: AsyncClient) -> None:
        # Include Origin header so the CSRF middleware (which runs before auth)
        # lets the request reach require_admin; otherwise we'd get 403 for the
        # CSRF rejection and never verify the auth gate.
        res = await client.post(
            "/api/admin/users",
            headers={"Origin": "http://localhost:5173"},
            json={
                "name": "A", "gender": "other", "age": 25, "height": 170, "weight": 70,
                "experience_level": "beginner",
            },
        )
        assert res.status_code == 401

    async def test_creates_user(self, client: AsyncClient, db_session: AsyncSession) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.post(
            "/api/admin/users",
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
            json={
                "name": "New Person", "gender": "f", "age": 30, "height": 165,
                "weight": 60, "experience_level": "intermediate",
                "goals": "get strong", "available_equipment": ["dumbbells"],
            },
        )
        assert res.status_code == 201
        body = res.json()
        assert body["id"] > 0
        assert body["name"] == "New Person"
        assert body["available_equipment"] == ["dumbbells"]

    async def test_rejects_bad_payload(self, client: AsyncClient, db_session: AsyncSession) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.post(
            "/api/admin/users",
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
            json={"name": ""},  # missing required fields
        )
        assert res.status_code == 422
```

> **Why `Origin: http://localhost:5173` header?** The phase 1 CSRF middleware (`flexloop.admin.csrf.OriginCheckMiddleware`) enforces Origin on state-changing methods. The phase 1 whitelist is `["http://localhost:5173", "http://localhost:8000"]`. Tests must send a matching Origin header or get 403.

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_admin_users.py::TestCreateUser -v`
Expected: 405 or 404 on POST (endpoint not defined yet).

- [ ] **Step 3: Append create endpoint to the router**

Append to `src/flexloop/admin/routers/users.py`:

```python
@router.post("", response_model=UserAdminResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserAdminCreate,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> User:
    user = User(**payload.model_dump())
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_admin_users.py::TestCreateUser -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/flexloop/admin/routers/users.py tests/test_admin_users.py
git commit -m "feat(admin): users create endpoint"
```

---

### Task 8: Users router — update endpoint

**Files:**
- Modify: `src/flexloop/admin/routers/users.py`
- Modify: `tests/test_admin_users.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_admin_users.py`:

```python
class TestUpdateUser:
    async def test_requires_auth(self, client: AsyncClient) -> None:
        res = await client.put(
            "/api/admin/users/1",
            headers={"Origin": "http://localhost:5173"},
            json={"name": "X"},
        )
        assert res.status_code == 401

    async def test_partial_update(self, client: AsyncClient, db_session: AsyncSession) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        users = await _seed_users(db_session, 1)
        res = await client.put(
            f"/api/admin/users/{users[0].id}",
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
            json={"name": "Renamed", "age": 99},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["name"] == "Renamed"
        assert body["age"] == 99
        # Untouched fields preserved
        assert body["gender"] == "other"

    async def test_404_on_missing(self, client: AsyncClient, db_session: AsyncSession) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.put(
            "/api/admin/users/99999",
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
            json={"name": "X"},
        )
        assert res.status_code == 404

    async def test_empty_body_is_noop(self, client: AsyncClient, db_session: AsyncSession) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        users = await _seed_users(db_session, 1)
        res = await client.put(
            f"/api/admin/users/{users[0].id}",
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
            json={},
        )
        assert res.status_code == 200
        assert res.json()["name"] == "User0"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_admin_users.py::TestUpdateUser -v`
Expected: 405 on PUT.

- [ ] **Step 3: Append update endpoint**

Append to `src/flexloop/admin/routers/users.py`:

```python
@router.put("/{user_id}", response_model=UserAdminResponse)
async def update_user(
    user_id: int,
    payload: UserAdminUpdate,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)

    await db.commit()
    await db.refresh(user)
    return user
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_admin_users.py::TestUpdateUser -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/flexloop/admin/routers/users.py tests/test_admin_users.py
git commit -m "feat(admin): users update endpoint (partial)"
```

---

### Task 9: Users router — delete endpoint

**Files:**
- Modify: `src/flexloop/admin/routers/users.py`
- Modify: `tests/test_admin_users.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_admin_users.py`:

```python
class TestDeleteUser:
    async def test_requires_auth(self, client: AsyncClient) -> None:
        res = await client.delete(
            "/api/admin/users/1",
            headers={"Origin": "http://localhost:5173"},
        )
        assert res.status_code == 401

    async def test_deletes_user(self, client: AsyncClient, db_session: AsyncSession) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        users = await _seed_users(db_session, 1)
        res = await client.delete(
            f"/api/admin/users/{users[0].id}",
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
        )
        assert res.status_code == 204

        # Confirm gone
        res2 = await client.get(f"/api/admin/users/{users[0].id}", cookies=cookies)
        assert res2.status_code == 404

    async def test_404_on_missing(self, client: AsyncClient, db_session: AsyncSession) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.delete(
            "/api/admin/users/99999",
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
        )
        assert res.status_code == 404
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_admin_users.py::TestDeleteUser -v`
Expected: 405.

- [ ] **Step 3: Append delete endpoint**

Append to `src/flexloop/admin/routers/users.py`:

```python
@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> None:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    await db.delete(user)
    await db.commit()
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_admin_users.py -v`
Expected: all 22 tests pass (9 list + 3 detail + 3 create + 4 update + 3 delete).

- [ ] **Step 5: Run the whole admin test suite to catch regressions**

Run: `uv run pytest tests/test_admin_*.py -v`
Expected: phase 1 tests still green + all phase 2 users tests green.

- [ ] **Step 6: Commit**

```bash
git add src/flexloop/admin/routers/users.py tests/test_admin_users.py
git commit -m "feat(admin): users delete endpoint — completes Users CRUD"
```

---

**End of Chunk 2.** At this point:
- `/api/admin/users` supports all 5 CRUD operations (list, detail, create, update, delete).
- Integration test file `tests/test_admin_users.py` covers ~22 cases including auth, pagination, search, sort, filter, validation, and 404s.
- All phase 1 tests still pass.
- The users router is the canonical template — Chunk 3 copies it 6 times.

---

## Chunk 3: User Data Routers — Workouts, Measurements, PRs

Three resource routers under the sidebar "User Data" group. Each task stands up one full resource by copying the Users pattern from Chunk 2, with resource-specific schemas, sort/filter/search whitelists, and a minimal test file covering auth + list + happy-path create. The purpose of the per-resource tests is to catch wiring mistakes (wrong model, wrong whitelist, forgotten `require_admin`) — not to re-exercise the helper logic that Chunk 1 already tests.

Conventions used in Chunks 3 and 4 to stay DRY:
- **Test helper reuse:** Each test file re-defines the `_make_admin_and_cookie` helper from `tests/test_admin_users.py` — copy-pasted intentionally instead of hoisted into conftest.py. Reason: conftest additions cascade to every test file in the suite and we want to keep this change localized. If the helper grows, move it to `tests/_admin_helpers.py` in a follow-up.
- **`Origin: http://localhost:5173` header** is required on every POST/PUT/DELETE test, matching Chunk 2's Users write tests. If the phase 1 CSRF middleware origin whitelist is ever changed, these tests will need to match.
- **Every router uses `Depends(require_admin)`** and returns `PaginatedResponse[<resource>Response]` for its list endpoint.

### Task 10: Workouts router

**Files:**
- Create: `src/flexloop/admin/schemas/workouts.py`
- Create: `src/flexloop/admin/routers/workouts.py`
- Create: `tests/test_admin_workouts.py`
- Modify: `src/flexloop/main.py`

The Workouts resource covers the `WorkoutSession` table, not the nested sets. Sets are embedded into the response (read-only, because editing individual sets is better done through a future dedicated UI). Admin create accepts only the session header — admins can't add sets via this endpoint; instead they'd go to the iOS client or a future set editor.

Filters per spec §9.2: `user_id`, `completed` (derived from `completed_at IS NULL`), `source` (plan/custom). Search: `notes`. Sort: `started_at`, `completed_at`, `user_id`.

- [ ] **Step 1: Create schemas**

Create `src/flexloop/admin/schemas/workouts.py`:

```python
"""Admin CRUD schemas for ``WorkoutSession``."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WorkoutSetAdminResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    exercise_id: int
    exercise_group_id: int | None
    set_number: int
    set_type: str
    weight: float | None
    reps: int | None
    rpe: float | None
    duration_sec: int | None
    distance_m: float | None
    rest_sec: int | None


class WorkoutSessionAdminResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    plan_day_id: int | None
    template_id: int | None
    source: str
    started_at: datetime
    completed_at: datetime | None
    notes: str | None
    sets: list[WorkoutSetAdminResponse] = Field(default_factory=list)


class WorkoutSessionAdminCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: int
    plan_day_id: int | None = None
    template_id: int | None = None
    source: str = "plan"
    started_at: datetime
    completed_at: datetime | None = None
    notes: str | None = None


class WorkoutSessionAdminUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_day_id: int | None = None
    template_id: int | None = None
    source: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    notes: str | None = None
```

- [ ] **Step 2: Write failing tests**

Create `tests/test_admin_workouts.py`:

```python
"""Integration tests for /api/admin/workouts."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import SESSION_COOKIE_NAME, create_session, hash_password
from flexloop.models.admin_user import AdminUser
from flexloop.models.user import User
from flexloop.models.workout import WorkoutSession


async def _make_admin_and_cookie(db: AsyncSession) -> dict[str, str]:
    admin = AdminUser(username="tester", password_hash=hash_password("password123"))
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    token, _ = await create_session(db, admin_user_id=admin.id)
    return {SESSION_COOKIE_NAME: token}


async def _make_user(db: AsyncSession) -> User:
    user = User(
        name="WO Owner", gender="other", age=30, height=180, weight=80,
        weight_unit="kg", height_unit="cm", experience_level="intermediate",
        goals="", available_equipment=[],
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


class TestListWorkouts:
    async def test_requires_auth(self, client: AsyncClient) -> None:
        assert (await client.get("/api/admin/workouts")).status_code == 401

    async def test_empty_list(self, client: AsyncClient, db_session: AsyncSession) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.get("/api/admin/workouts", cookies=cookies)
        assert res.status_code == 200
        assert res.json()["total"] == 0

    async def test_lists_sessions_with_sets_embedded(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        user = await _make_user(db_session)
        ws = WorkoutSession(
            user_id=user.id, source="plan", started_at=datetime.utcnow(),
        )
        db_session.add(ws)
        await db_session.commit()

        res = await client.get("/api/admin/workouts", cookies=cookies)
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 1
        assert body["items"][0]["user_id"] == user.id
        assert body["items"][0]["sets"] == []

    async def test_filter_by_user(
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

        db_session.add(WorkoutSession(user_id=u1.id, source="plan", started_at=datetime.utcnow()))
        db_session.add(WorkoutSession(user_id=u2.id, source="plan", started_at=datetime.utcnow()))
        await db_session.commit()

        res = await client.get(
            f"/api/admin/workouts?filter[user_id]={u1.id}", cookies=cookies,
        )
        assert res.status_code == 200
        assert res.json()["total"] == 1

    async def test_filter_completed_true(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        user = await _make_user(db_session)
        now = datetime.utcnow()
        db_session.add(WorkoutSession(user_id=user.id, source="plan", started_at=now))  # in-progress
        db_session.add(WorkoutSession(
            user_id=user.id, source="plan", started_at=now - timedelta(hours=2),
            completed_at=now,
        ))
        await db_session.commit()

        res = await client.get(
            "/api/admin/workouts?filter[completed]=true", cookies=cookies,
        )
        assert res.status_code == 200
        assert res.json()["total"] == 1

        res2 = await client.get(
            "/api/admin/workouts?filter[completed]=false", cookies=cookies,
        )
        assert res2.json()["total"] == 1


class TestCreateWorkout:
    async def test_creates_session(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        user = await _make_user(db_session)
        res = await client.post(
            "/api/admin/workouts",
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
            json={
                "user_id": user.id,
                "source": "custom",
                "started_at": "2026-04-07T10:00:00",
            },
        )
        assert res.status_code == 201
        assert res.json()["source"] == "custom"


class TestDeleteWorkout:
    async def test_deletes_and_cascades_sets(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        user = await _make_user(db_session)
        ws = WorkoutSession(user_id=user.id, source="plan", started_at=datetime.utcnow())
        db_session.add(ws)
        await db_session.commit()
        await db_session.refresh(ws)

        res = await client.delete(
            f"/api/admin/workouts/{ws.id}",
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
        )
        assert res.status_code == 204
```

- [ ] **Step 3: Write the router**

Create `src/flexloop/admin/routers/workouts.py`:

```python
"""Admin CRUD endpoints for WorkoutSession."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from flexloop.admin.auth import require_admin
from flexloop.admin.crud import (
    paginated_response,
    parse_filter_params,
    parse_sort_spec,
)
from flexloop.admin.schemas.common import ListQueryParams, PaginatedResponse
from flexloop.admin.schemas.workouts import (
    WorkoutSessionAdminCreate,
    WorkoutSessionAdminResponse,
    WorkoutSessionAdminUpdate,
)
from flexloop.db.engine import get_session
from flexloop.models.workout import WorkoutSession

router = APIRouter(prefix="/api/admin/workouts", tags=["admin:workouts"])

ALLOWED_SORT_COLUMNS = {"id", "started_at", "completed_at", "user_id", "source"}
# Plain-column filters (no translation). `completed` is handled separately.
ALLOWED_FILTER_COLUMNS = {"user_id", "source", "template_id", "plan_day_id", "completed"}


@router.get("", response_model=PaginatedResponse[WorkoutSessionAdminResponse])
async def list_workouts(
    request: Request,
    params: ListQueryParams = Depends(ListQueryParams.as_dependency),
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> dict:
    query = select(WorkoutSession).options(selectinload(WorkoutSession.sets))

    filters = parse_filter_params(request.query_params, allowed=ALLOWED_FILTER_COLUMNS)
    for key, value in filters.items():
        if key == "completed":
            if value.lower() in ("true", "1", "yes"):
                query = query.where(WorkoutSession.completed_at.is_not(None))
            elif value.lower() in ("false", "0", "no"):
                query = query.where(WorkoutSession.completed_at.is_(None))
            else:
                raise HTTPException(
                    status_code=400,
                    detail="filter[completed] must be true or false",
                )
        else:
            query = query.where(getattr(WorkoutSession, key) == value)

    if params.search:
        like = f"%{params.search}%"
        query = query.where(WorkoutSession.notes.ilike(like))

    sort_clauses = parse_sort_spec(params.sort, model=WorkoutSession, allowed=ALLOWED_SORT_COLUMNS)
    if sort_clauses:
        query = query.order_by(*sort_clauses)
    else:
        query = query.order_by(WorkoutSession.started_at.desc())

    return await paginated_response(
        db, query=query,
        item_schema=WorkoutSessionAdminResponse,
        page=params.page, per_page=params.per_page,
    )


@router.get("/{workout_id}", response_model=WorkoutSessionAdminResponse)
async def get_workout(
    workout_id: int,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> WorkoutSession:
    result = await db.execute(
        select(WorkoutSession)
        .options(selectinload(WorkoutSession.sets))
        .where(WorkoutSession.id == workout_id)
    )
    ws = result.scalar_one_or_none()
    if ws is None:
        raise HTTPException(404, "workout session not found")
    return ws


@router.post("", response_model=WorkoutSessionAdminResponse, status_code=201)
async def create_workout(
    payload: WorkoutSessionAdminCreate,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> WorkoutSession:
    ws = WorkoutSession(**payload.model_dump())
    db.add(ws)
    await db.commit()
    await db.refresh(ws, attribute_names=["sets"])
    return ws


@router.put("/{workout_id}", response_model=WorkoutSessionAdminResponse)
async def update_workout(
    workout_id: int,
    payload: WorkoutSessionAdminUpdate,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> WorkoutSession:
    result = await db.execute(
        select(WorkoutSession)
        .options(selectinload(WorkoutSession.sets))
        .where(WorkoutSession.id == workout_id)
    )
    ws = result.scalar_one_or_none()
    if ws is None:
        raise HTTPException(404, "workout session not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(ws, field, value)
    await db.commit()
    await db.refresh(ws, attribute_names=["sets"])
    return ws


@router.delete("/{workout_id}", status_code=204)
async def delete_workout(
    workout_id: int,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> None:
    result = await db.execute(select(WorkoutSession).where(WorkoutSession.id == workout_id))
    ws = result.scalar_one_or_none()
    if ws is None:
        raise HTTPException(404, "workout session not found")
    await db.delete(ws)
    await db.commit()
```

- [ ] **Step 4: Wire into main.py**

Add to `src/flexloop/main.py` (next to the users router import/include):

```python
from flexloop.admin.routers.workouts import router as admin_workouts_router
# ...
app.include_router(admin_workouts_router)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_admin_workouts.py -v`
Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add src/flexloop/admin/schemas/workouts.py \
        src/flexloop/admin/routers/workouts.py \
        src/flexloop/main.py \
        tests/test_admin_workouts.py
git commit -m "feat(admin): workouts CRUD router"
```

---

### Task 11: Measurements router

**Files:**
- Create: `src/flexloop/admin/schemas/measurements.py`
- Create: `src/flexloop/admin/routers/measurements.py`
- Create: `tests/test_admin_measurements.py`
- Modify: `src/flexloop/main.py`

Simplest resource. Filters: `user_id`, `type`. Sort: `date`, `value`. Search: `notes`.

- [ ] **Step 1: Create schemas**

Create `src/flexloop/admin/schemas/measurements.py`:

```python
"""Admin CRUD schemas for Measurement."""
from __future__ import annotations

# Aliased import to avoid the field name `date` shadowing the type `date`
# under PEP 563 / `from __future__ import annotations` — Pydantic's forward-ref
# evaluator otherwise resolves the annotation to the field's default value.
from datetime import date as date_type

from pydantic import BaseModel, ConfigDict, Field


class MeasurementAdminResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    date: date_type
    type: str
    value: float
    notes: str | None


class MeasurementAdminCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: int
    date: date_type
    type: str = Field(min_length=1, max_length=20)
    value: float
    notes: str | None = None


class MeasurementAdminUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date_type | None = None
    type: str | None = Field(default=None, min_length=1, max_length=20)
    value: float | None = None
    notes: str | None = None
```

- [ ] **Step 2: Write failing tests**

Create `tests/test_admin_measurements.py`:

```python
"""Integration tests for /api/admin/measurements."""
from __future__ import annotations

from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import SESSION_COOKIE_NAME, create_session, hash_password
from flexloop.models.admin_user import AdminUser
from flexloop.models.measurement import Measurement
from flexloop.models.user import User


async def _make_admin_and_cookie(db: AsyncSession) -> dict[str, str]:
    admin = AdminUser(username="t", password_hash=hash_password("password123"))
    db.add(admin); await db.commit(); await db.refresh(admin)
    token, _ = await create_session(db, admin_user_id=admin.id)
    return {SESSION_COOKIE_NAME: token}


async def _make_user(db: AsyncSession) -> User:
    u = User(
        name="M Owner", gender="f", age=30, height=165, weight=60,
        weight_unit="kg", height_unit="cm", experience_level="intermediate",
        goals="", available_equipment=[],
    )
    db.add(u); await db.commit(); await db.refresh(u)
    return u


class TestMeasurements:
    async def test_list_requires_auth(self, client: AsyncClient) -> None:
        assert (await client.get("/api/admin/measurements")).status_code == 401

    async def test_create_list_delete(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        user = await _make_user(db_session)

        # Create
        res = await client.post(
            "/api/admin/measurements",
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
            json={
                "user_id": user.id, "date": "2026-04-01",
                "type": "weight", "value": 60.5, "notes": "morning",
            },
        )
        assert res.status_code == 201
        mid = res.json()["id"]

        # List
        res = await client.get(
            f"/api/admin/measurements?filter[user_id]={user.id}",
            cookies=cookies,
        )
        assert res.json()["total"] == 1

        # Delete
        res = await client.delete(
            f"/api/admin/measurements/{mid}",
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
        )
        assert res.status_code == 204

    async def test_filter_by_type(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        user = await _make_user(db_session)
        db_session.add(Measurement(user_id=user.id, date=date(2026, 1, 1), type="weight", value=60))
        db_session.add(Measurement(user_id=user.id, date=date(2026, 1, 1), type="body_fat", value=18))
        await db_session.commit()

        res = await client.get("/api/admin/measurements?filter[type]=weight", cookies=cookies)
        assert res.json()["total"] == 1
```

- [ ] **Step 3: Write the router**

Create `src/flexloop/admin/routers/measurements.py`:

```python
"""Admin CRUD endpoints for Measurement."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import require_admin
from flexloop.admin.crud import paginated_response, parse_filter_params, parse_sort_spec
from flexloop.admin.schemas.common import ListQueryParams, PaginatedResponse
from flexloop.admin.schemas.measurements import (
    MeasurementAdminCreate,
    MeasurementAdminResponse,
    MeasurementAdminUpdate,
)
from flexloop.db.engine import get_session
from flexloop.models.measurement import Measurement

router = APIRouter(prefix="/api/admin/measurements", tags=["admin:measurements"])

ALLOWED_SORT = {"id", "date", "value", "type", "user_id"}
ALLOWED_FILTER = {"user_id", "type"}


@router.get("", response_model=PaginatedResponse[MeasurementAdminResponse])
async def list_measurements(
    request: Request,
    params: ListQueryParams = Depends(ListQueryParams.as_dependency),
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> dict:
    query = select(Measurement)

    for key, value in parse_filter_params(request.query_params, allowed=ALLOWED_FILTER).items():
        query = query.where(getattr(Measurement, key) == value)

    if params.search:
        query = query.where(Measurement.notes.ilike(f"%{params.search}%"))

    sort_clauses = parse_sort_spec(params.sort, model=Measurement, allowed=ALLOWED_SORT)
    query = query.order_by(*sort_clauses) if sort_clauses else query.order_by(Measurement.date.desc())

    return await paginated_response(
        db, query=query, item_schema=MeasurementAdminResponse,
        page=params.page, per_page=params.per_page,
    )


@router.get("/{measurement_id}", response_model=MeasurementAdminResponse)
async def get_measurement(
    measurement_id: int,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> Measurement:
    result = await db.execute(select(Measurement).where(Measurement.id == measurement_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "measurement not found")
    return row


@router.post("", response_model=MeasurementAdminResponse, status_code=201)
async def create_measurement(
    payload: MeasurementAdminCreate,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> Measurement:
    row = Measurement(**payload.model_dump())
    db.add(row); await db.commit(); await db.refresh(row)
    return row


@router.put("/{measurement_id}", response_model=MeasurementAdminResponse)
async def update_measurement(
    measurement_id: int,
    payload: MeasurementAdminUpdate,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> Measurement:
    result = await db.execute(select(Measurement).where(Measurement.id == measurement_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "measurement not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    await db.commit(); await db.refresh(row)
    return row


@router.delete("/{measurement_id}", status_code=204)
async def delete_measurement(
    measurement_id: int,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> None:
    result = await db.execute(select(Measurement).where(Measurement.id == measurement_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "measurement not found")
    await db.delete(row); await db.commit()
```

- [ ] **Step 4: Wire into main.py**

```python
from flexloop.admin.routers.measurements import router as admin_measurements_router
# ...
app.include_router(admin_measurements_router)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_admin_measurements.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add src/flexloop/admin/schemas/measurements.py \
        src/flexloop/admin/routers/measurements.py \
        src/flexloop/main.py \
        tests/test_admin_measurements.py
git commit -m "feat(admin): measurements CRUD router"
```

---

### Task 12: Personal Records router

**Files:**
- Create: `src/flexloop/admin/schemas/prs.py`
- Create: `src/flexloop/admin/routers/prs.py`
- Create: `tests/test_admin_prs.py`
- Modify: `src/flexloop/main.py`

URL path `/api/admin/prs`. Filters: `user_id`, `exercise_id`, `pr_type`. Sort: `achieved_at`, `value`.

- [ ] **Step 1: Create schemas**

Create `src/flexloop/admin/schemas/prs.py`:

```python
"""Admin CRUD schemas for PersonalRecord."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PersonalRecordAdminResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    exercise_id: int
    pr_type: str
    value: float
    session_id: int | None
    achieved_at: datetime


class PersonalRecordAdminCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: int
    exercise_id: int
    pr_type: str = Field(min_length=1, max_length=20)
    value: float
    session_id: int | None = None
    achieved_at: datetime


class PersonalRecordAdminUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exercise_id: int | None = None
    pr_type: str | None = Field(default=None, min_length=1, max_length=20)
    value: float | None = None
    session_id: int | None = None
    achieved_at: datetime | None = None
```

- [ ] **Step 2: Write failing tests**

Create `tests/test_admin_prs.py`:

```python
"""Integration tests for /api/admin/prs."""
from __future__ import annotations

from datetime import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import SESSION_COOKIE_NAME, create_session, hash_password
from flexloop.models.admin_user import AdminUser
from flexloop.models.exercise import Exercise
from flexloop.models.personal_record import PersonalRecord
from flexloop.models.user import User


async def _make_admin_and_cookie(db: AsyncSession) -> dict[str, str]:
    admin = AdminUser(username="t", password_hash=hash_password("password123"))
    db.add(admin); await db.commit(); await db.refresh(admin)
    token, _ = await create_session(db, admin_user_id=admin.id)
    return {SESSION_COOKIE_NAME: token}


async def _make_user_and_exercise(db: AsyncSession) -> tuple[User, Exercise]:
    u = User(
        name="PR Owner", gender="m", age=28, height=175, weight=80,
        weight_unit="kg", height_unit="cm", experience_level="intermediate",
        goals="", available_equipment=[],
    )
    e = Exercise(
        name="Bench Press", muscle_group="chest", equipment="barbell",
        category="compound", difficulty="intermediate",
    )
    db.add_all([u, e]); await db.commit()
    await db.refresh(u); await db.refresh(e)
    return u, e


class TestPRs:
    async def test_list_requires_auth(self, client: AsyncClient) -> None:
        assert (await client.get("/api/admin/prs")).status_code == 401

    async def test_create_and_list(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        user, ex = await _make_user_and_exercise(db_session)

        res = await client.post(
            "/api/admin/prs",
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
            json={
                "user_id": user.id, "exercise_id": ex.id,
                "pr_type": "max_weight", "value": 120.0,
                "achieved_at": "2026-04-01T12:00:00",
            },
        )
        assert res.status_code == 201

        res = await client.get(
            f"/api/admin/prs?filter[user_id]={user.id}", cookies=cookies,
        )
        assert res.json()["total"] == 1
        assert res.json()["items"][0]["pr_type"] == "max_weight"

    async def test_filter_by_exercise(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        user, ex = await _make_user_and_exercise(db_session)
        db_session.add(PersonalRecord(
            user_id=user.id, exercise_id=ex.id, pr_type="max_weight",
            value=100, achieved_at=datetime.utcnow(),
        ))
        await db_session.commit()

        res = await client.get(
            f"/api/admin/prs?filter[exercise_id]={ex.id}", cookies=cookies,
        )
        assert res.json()["total"] == 1
```

- [ ] **Step 3: Write the router**

Create `src/flexloop/admin/routers/prs.py`:

```python
"""Admin CRUD endpoints for PersonalRecord."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import require_admin
from flexloop.admin.crud import paginated_response, parse_filter_params, parse_sort_spec
from flexloop.admin.schemas.common import ListQueryParams, PaginatedResponse
from flexloop.admin.schemas.prs import (
    PersonalRecordAdminCreate,
    PersonalRecordAdminResponse,
    PersonalRecordAdminUpdate,
)
from flexloop.db.engine import get_session
from flexloop.models.personal_record import PersonalRecord

router = APIRouter(prefix="/api/admin/prs", tags=["admin:prs"])

ALLOWED_SORT = {"id", "achieved_at", "value", "user_id", "exercise_id"}
ALLOWED_FILTER = {"user_id", "exercise_id", "pr_type"}


@router.get("", response_model=PaginatedResponse[PersonalRecordAdminResponse])
async def list_prs(
    request: Request,
    params: ListQueryParams = Depends(ListQueryParams.as_dependency),
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> dict:
    query = select(PersonalRecord)
    for key, value in parse_filter_params(request.query_params, allowed=ALLOWED_FILTER).items():
        query = query.where(getattr(PersonalRecord, key) == value)

    sort_clauses = parse_sort_spec(params.sort, model=PersonalRecord, allowed=ALLOWED_SORT)
    query = query.order_by(*sort_clauses) if sort_clauses else query.order_by(PersonalRecord.achieved_at.desc())

    return await paginated_response(
        db, query=query, item_schema=PersonalRecordAdminResponse,
        page=params.page, per_page=params.per_page,
    )


@router.get("/{pr_id}", response_model=PersonalRecordAdminResponse)
async def get_pr(
    pr_id: int,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> PersonalRecord:
    result = await db.execute(select(PersonalRecord).where(PersonalRecord.id == pr_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "personal record not found")
    return row


@router.post("", response_model=PersonalRecordAdminResponse, status_code=201)
async def create_pr(
    payload: PersonalRecordAdminCreate,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> PersonalRecord:
    row = PersonalRecord(**payload.model_dump())
    db.add(row); await db.commit(); await db.refresh(row)
    return row


@router.put("/{pr_id}", response_model=PersonalRecordAdminResponse)
async def update_pr(
    pr_id: int,
    payload: PersonalRecordAdminUpdate,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> PersonalRecord:
    result = await db.execute(select(PersonalRecord).where(PersonalRecord.id == pr_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "personal record not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    await db.commit(); await db.refresh(row)
    return row


@router.delete("/{pr_id}", status_code=204)
async def delete_pr(
    pr_id: int,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> None:
    result = await db.execute(select(PersonalRecord).where(PersonalRecord.id == pr_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "personal record not found")
    await db.delete(row); await db.commit()
```

- [ ] **Step 4: Wire into main.py**

```python
from flexloop.admin.routers.prs import router as admin_prs_router
# ...
app.include_router(admin_prs_router)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_admin_prs.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add src/flexloop/admin/schemas/prs.py \
        src/flexloop/admin/routers/prs.py \
        src/flexloop/main.py \
        tests/test_admin_prs.py
git commit -m "feat(admin): personal records CRUD router"
```

---

**End of Chunk 3.** Three user-data resource routers live: Workouts (with embedded sets + the completed/in-progress filter), Measurements, Personal Records. Chunk 4 finishes the catalog + AI + admin-user resources.

---

## Chunk 4: Catalog, AI Usage, and Admin Users Routers

Finishes the backend phase 2 surface. After this chunk, every phase 2 backend endpoint exists and the OpenAPI doc is complete — the frontend can codegen against it in Chunk 5.

### Task 13: Exercises router

**Files:**
- Create: `src/flexloop/admin/schemas/exercises.py`
- Create: `src/flexloop/admin/routers/exercises.py`
- Create: `tests/test_admin_exercises.py`
- Modify: `src/flexloop/main.py`

Catalog table — admin-editable. Filters: `muscle_group`, `equipment`, `category`, `difficulty`, `source_plugin`. Sort: `name`, `muscle_group`. Search: `name`.

- [ ] **Step 1: Create schemas**

Create `src/flexloop/admin/schemas/exercises.py`:

```python
"""Admin CRUD schemas for Exercise."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExerciseAdminResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    muscle_group: str
    equipment: str
    category: str
    difficulty: str
    source_plugin: str | None
    metadata_json: dict[str, Any] | None


class ExerciseAdminCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    muscle_group: str = Field(min_length=1, max_length=50)
    equipment: str = Field(min_length=1, max_length=50)
    category: str = Field(min_length=1, max_length=50)
    difficulty: str = Field(min_length=1, max_length=20)
    source_plugin: str | None = None
    metadata_json: dict[str, Any] | None = None


class ExerciseAdminUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    muscle_group: str | None = Field(default=None, min_length=1, max_length=50)
    equipment: str | None = Field(default=None, min_length=1, max_length=50)
    category: str | None = Field(default=None, min_length=1, max_length=50)
    difficulty: str | None = Field(default=None, min_length=1, max_length=20)
    source_plugin: str | None = None
    metadata_json: dict[str, Any] | None = None
```

- [ ] **Step 2: Write failing tests**

Create `tests/test_admin_exercises.py`:

```python
"""Integration tests for /api/admin/exercises."""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import SESSION_COOKIE_NAME, create_session, hash_password
from flexloop.models.admin_user import AdminUser
from flexloop.models.exercise import Exercise


async def _cookie(db: AsyncSession) -> dict[str, str]:
    a = AdminUser(username="t", password_hash=hash_password("password123"))
    db.add(a); await db.commit(); await db.refresh(a)
    token, _ = await create_session(db, admin_user_id=a.id)
    return {SESSION_COOKIE_NAME: token}


class TestExercises:
    async def test_auth(self, client: AsyncClient) -> None:
        assert (await client.get("/api/admin/exercises")).status_code == 401

    async def test_create_and_search_by_name(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        res = await client.post(
            "/api/admin/exercises",
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
            json={
                "name": "Bulgarian Split Squat", "muscle_group": "legs",
                "equipment": "dumbbell", "category": "compound",
                "difficulty": "intermediate",
            },
        )
        assert res.status_code == 201

        res = await client.get(
            "/api/admin/exercises?search=bulgarian", cookies=cookies,
        )
        assert res.json()["total"] == 1

    async def test_filter_by_muscle_group(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        db_session.add(Exercise(
            name="Squat", muscle_group="legs", equipment="barbell",
            category="compound", difficulty="intermediate",
        ))
        db_session.add(Exercise(
            name="Bench", muscle_group="chest", equipment="barbell",
            category="compound", difficulty="intermediate",
        ))
        await db_session.commit()

        res = await client.get(
            "/api/admin/exercises?filter[muscle_group]=legs", cookies=cookies,
        )
        assert res.json()["total"] == 1
        assert res.json()["items"][0]["name"] == "Squat"
```

- [ ] **Step 3: Write the router**

Create `src/flexloop/admin/routers/exercises.py`:

```python
"""Admin CRUD endpoints for Exercise."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import require_admin
from flexloop.admin.crud import paginated_response, parse_filter_params, parse_sort_spec
from flexloop.admin.schemas.common import ListQueryParams, PaginatedResponse
from flexloop.admin.schemas.exercises import (
    ExerciseAdminCreate,
    ExerciseAdminResponse,
    ExerciseAdminUpdate,
)
from flexloop.db.engine import get_session
from flexloop.models.exercise import Exercise

router = APIRouter(prefix="/api/admin/exercises", tags=["admin:exercises"])

ALLOWED_SORT = {"id", "name", "muscle_group", "equipment", "category", "difficulty"}
ALLOWED_FILTER = {"muscle_group", "equipment", "category", "difficulty", "source_plugin"}


@router.get("", response_model=PaginatedResponse[ExerciseAdminResponse])
async def list_exercises(
    request: Request,
    params: ListQueryParams = Depends(ListQueryParams.as_dependency),
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> dict:
    query = select(Exercise)
    for key, value in parse_filter_params(request.query_params, allowed=ALLOWED_FILTER).items():
        query = query.where(getattr(Exercise, key) == value)

    if params.search:
        query = query.where(Exercise.name.ilike(f"%{params.search}%"))

    sort_clauses = parse_sort_spec(params.sort, model=Exercise, allowed=ALLOWED_SORT)
    query = query.order_by(*sort_clauses) if sort_clauses else query.order_by(Exercise.name.asc())

    return await paginated_response(
        db, query=query, item_schema=ExerciseAdminResponse,
        page=params.page, per_page=params.per_page,
    )


@router.get("/{exercise_id}", response_model=ExerciseAdminResponse)
async def get_exercise(
    exercise_id: int,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> Exercise:
    result = await db.execute(select(Exercise).where(Exercise.id == exercise_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "exercise not found")
    return row


@router.post("", response_model=ExerciseAdminResponse, status_code=201)
async def create_exercise(
    payload: ExerciseAdminCreate,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> Exercise:
    row = Exercise(**payload.model_dump())
    db.add(row); await db.commit(); await db.refresh(row)
    return row


@router.put("/{exercise_id}", response_model=ExerciseAdminResponse)
async def update_exercise(
    exercise_id: int,
    payload: ExerciseAdminUpdate,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> Exercise:
    result = await db.execute(select(Exercise).where(Exercise.id == exercise_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "exercise not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    await db.commit(); await db.refresh(row)
    return row


@router.delete("/{exercise_id}", status_code=204)
async def delete_exercise(
    exercise_id: int,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> None:
    result = await db.execute(select(Exercise).where(Exercise.id == exercise_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "exercise not found")
    await db.delete(row); await db.commit()
```

- [ ] **Step 4: Wire into main.py**

```python
from flexloop.admin.routers.exercises import router as admin_exercises_router
# ...
app.include_router(admin_exercises_router)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_admin_exercises.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add src/flexloop/admin/schemas/exercises.py \
        src/flexloop/admin/routers/exercises.py \
        src/flexloop/main.py \
        tests/test_admin_exercises.py
git commit -m "feat(admin): exercises CRUD router"
```

---

### Task 14: AI Usage router

**Files:**
- Create: `src/flexloop/admin/schemas/ai_usage.py`
- Create: `src/flexloop/admin/routers/ai_usage.py`
- Create: `tests/test_admin_ai_usage.py`
- Modify: `src/flexloop/main.py`

Mounted at `/api/admin/ai/usage` (not `/api/admin/ai_usage`) to match the sidebar's `AI > Usage` grouping. Filters: `user_id`, `month`. Sort: `month`, `estimated_cost`, `call_count`.

> **Note on non-standard mount path:** This is the only router in phase 2 with a grouped prefix. It's not enough to justify a factory abstraction — just commit the divergence and move on.

- [ ] **Step 1: Create schemas**

Create `src/flexloop/admin/schemas/ai_usage.py`:

```python
"""Admin CRUD schemas for AIUsage (per-month rollup table)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AIUsageAdminResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    month: str
    total_input_tokens: int
    total_output_tokens: int
    total_cache_read_tokens: int
    total_cache_creation_tokens: int
    estimated_cost: float
    call_count: int


class AIUsageAdminCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: int
    month: str = Field(min_length=7, max_length=7)  # "YYYY-MM"
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cache_creation_tokens: int = 0
    estimated_cost: float = 0.0
    call_count: int = 0


class AIUsageAdminUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_input_tokens: int | None = None
    total_output_tokens: int | None = None
    total_cache_read_tokens: int | None = None
    total_cache_creation_tokens: int | None = None
    estimated_cost: float | None = None
    call_count: int | None = None
```

- [ ] **Step 2: Write failing tests**

Create `tests/test_admin_ai_usage.py`:

```python
"""Integration tests for /api/admin/ai/usage."""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import SESSION_COOKIE_NAME, create_session, hash_password
from flexloop.models.admin_user import AdminUser
from flexloop.models.ai import AIUsage
from flexloop.models.user import User


async def _cookie(db: AsyncSession) -> dict[str, str]:
    a = AdminUser(username="t", password_hash=hash_password("password123"))
    db.add(a); await db.commit(); await db.refresh(a)
    token, _ = await create_session(db, admin_user_id=a.id)
    return {SESSION_COOKIE_NAME: token}


async def _user(db: AsyncSession) -> User:
    u = User(
        name="AI User", gender="other", age=30, height=170, weight=70,
        weight_unit="kg", height_unit="cm", experience_level="intermediate",
        goals="", available_equipment=[],
    )
    db.add(u); await db.commit(); await db.refresh(u)
    return u


class TestAIUsage:
    async def test_auth(self, client: AsyncClient) -> None:
        assert (await client.get("/api/admin/ai/usage")).status_code == 401

    async def test_list_and_filter_by_month(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        user = await _user(db_session)
        db_session.add_all([
            AIUsage(user_id=user.id, month="2026-03", total_input_tokens=1000, estimated_cost=0.01, call_count=5),
            AIUsage(user_id=user.id, month="2026-04", total_input_tokens=2000, estimated_cost=0.02, call_count=7),
        ])
        await db_session.commit()

        res = await client.get("/api/admin/ai/usage", cookies=cookies)
        assert res.json()["total"] == 2

        res = await client.get(
            "/api/admin/ai/usage?filter[month]=2026-04", cookies=cookies,
        )
        assert res.json()["total"] == 1
        assert res.json()["items"][0]["call_count"] == 7
```

- [ ] **Step 3: Write the router**

Create `src/flexloop/admin/routers/ai_usage.py`:

```python
"""Admin CRUD endpoints for AIUsage."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import require_admin
from flexloop.admin.crud import paginated_response, parse_filter_params, parse_sort_spec
from flexloop.admin.schemas.ai_usage import (
    AIUsageAdminCreate,
    AIUsageAdminResponse,
    AIUsageAdminUpdate,
)
from flexloop.admin.schemas.common import ListQueryParams, PaginatedResponse
from flexloop.db.engine import get_session
from flexloop.models.ai import AIUsage

router = APIRouter(prefix="/api/admin/ai/usage", tags=["admin:ai-usage"])

ALLOWED_SORT = {"id", "month", "estimated_cost", "call_count", "user_id"}
ALLOWED_FILTER = {"user_id", "month"}


@router.get("", response_model=PaginatedResponse[AIUsageAdminResponse])
async def list_ai_usage(
    request: Request,
    params: ListQueryParams = Depends(ListQueryParams.as_dependency),
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> dict:
    query = select(AIUsage)
    for key, value in parse_filter_params(request.query_params, allowed=ALLOWED_FILTER).items():
        query = query.where(getattr(AIUsage, key) == value)

    sort_clauses = parse_sort_spec(params.sort, model=AIUsage, allowed=ALLOWED_SORT)
    query = query.order_by(*sort_clauses) if sort_clauses else query.order_by(AIUsage.month.desc())

    return await paginated_response(
        db, query=query, item_schema=AIUsageAdminResponse,
        page=params.page, per_page=params.per_page,
    )


@router.get("/{usage_id}", response_model=AIUsageAdminResponse)
async def get_ai_usage(
    usage_id: int,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> AIUsage:
    result = await db.execute(select(AIUsage).where(AIUsage.id == usage_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "ai usage row not found")
    return row


@router.post("", response_model=AIUsageAdminResponse, status_code=201)
async def create_ai_usage(
    payload: AIUsageAdminCreate,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> AIUsage:
    row = AIUsage(**payload.model_dump())
    db.add(row); await db.commit(); await db.refresh(row)
    return row


@router.put("/{usage_id}", response_model=AIUsageAdminResponse)
async def update_ai_usage(
    usage_id: int,
    payload: AIUsageAdminUpdate,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> AIUsage:
    result = await db.execute(select(AIUsage).where(AIUsage.id == usage_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "ai usage row not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    await db.commit(); await db.refresh(row)
    return row


@router.delete("/{usage_id}", status_code=204)
async def delete_ai_usage(
    usage_id: int,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> None:
    result = await db.execute(select(AIUsage).where(AIUsage.id == usage_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "ai usage row not found")
    await db.delete(row); await db.commit()
```

- [ ] **Step 4: Wire into main.py**

```python
from flexloop.admin.routers.ai_usage import router as admin_ai_usage_router
# ...
app.include_router(admin_ai_usage_router)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_admin_ai_usage.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add src/flexloop/admin/schemas/ai_usage.py \
        src/flexloop/admin/routers/ai_usage.py \
        src/flexloop/main.py \
        tests/test_admin_ai_usage.py
git commit -m "feat(admin): AI usage CRUD router"
```

---

### Task 15: Admin Users router

**Files:**
- Create: `src/flexloop/admin/schemas/admin_users.py`
- Create: `src/flexloop/admin/routers/admin_users.py`
- Create: `tests/test_admin_admin_users.py`
- Modify: `src/flexloop/main.py`

**Critical differences from other resources:**
1. `password_hash` is never in responses (security).
2. `create` payload has a `password` field (plain text) that gets bcrypt'd server-side.
3. `update` payload has an optional `password` field that triggers a re-hash when present.
4. `delete` cascades via FK to `admin_sessions` (phase 1 migration sets `ON DELETE CASCADE`).
5. Guard against deleting your own account — return 400 if `user_id == request.state.admin_session.admin_user_id`.

- [ ] **Step 1: Create schemas**

Create `src/flexloop/admin/schemas/admin_users.py`:

```python
"""Admin CRUD schemas for the ``admin_users`` table itself."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AdminAdminUserResponse(BaseModel):
    """Response shape — password_hash intentionally excluded."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    created_at: datetime
    last_login_at: datetime | None
    is_active: bool


class AdminAdminUserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=256)
    is_active: bool = True


class AdminAdminUserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str | None = Field(default=None, min_length=1, max_length=64)
    password: str | None = Field(default=None, min_length=8, max_length=256)
    is_active: bool | None = None
```

- [ ] **Step 2: Write failing tests**

Create `tests/test_admin_admin_users.py`:

```python
"""Integration tests for /api/admin/admin-users."""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import SESSION_COOKIE_NAME, create_session, hash_password, verify_password
from flexloop.models.admin_user import AdminUser


async def _make_admin_and_cookie(db: AsyncSession, username: str = "t") -> tuple[AdminUser, dict[str, str]]:
    a = AdminUser(username=username, password_hash=hash_password("password123"))
    db.add(a); await db.commit(); await db.refresh(a)
    token, _ = await create_session(db, admin_user_id=a.id)
    return a, {SESSION_COOKIE_NAME: token}


class TestListAdminUsers:
    async def test_auth(self, client: AsyncClient) -> None:
        assert (await client.get("/api/admin/admin-users")).status_code == 401

    async def test_response_has_no_password_hash(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, cookies = await _make_admin_and_cookie(db_session)
        res = await client.get("/api/admin/admin-users", cookies=cookies)
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 1
        assert "password_hash" not in body["items"][0]
        assert "password" not in body["items"][0]


class TestCreateAdminUser:
    async def test_hashes_password(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, cookies = await _make_admin_and_cookie(db_session)
        res = await client.post(
            "/api/admin/admin-users",
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
            json={"username": "newadmin", "password": "freshpass1"},
        )
        assert res.status_code == 201
        body = res.json()
        assert body["username"] == "newadmin"
        assert "password" not in body
        assert "password_hash" not in body

        # Verify DB hash matches
        result = await db_session.execute(
            select(AdminUser).where(AdminUser.username == "newadmin")
        )
        row = result.scalar_one()
        assert verify_password("freshpass1", row.password_hash)

    async def test_rejects_short_password(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, cookies = await _make_admin_and_cookie(db_session)
        res = await client.post(
            "/api/admin/admin-users",
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
            json={"username": "x", "password": "short"},
        )
        assert res.status_code == 422


class TestUpdateAdminUser:
    async def test_password_update_rehashes(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        admin, cookies = await _make_admin_and_cookie(db_session)
        other = AdminUser(username="other", password_hash=hash_password("oldpassword"))
        db_session.add(other); await db_session.commit(); await db_session.refresh(other)

        res = await client.put(
            f"/api/admin/admin-users/{other.id}",
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
            json={"password": "newpassword1"},
        )
        assert res.status_code == 200

        await db_session.refresh(other)
        assert verify_password("newpassword1", other.password_hash)

    async def test_deactivate(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        admin, cookies = await _make_admin_and_cookie(db_session)
        other = AdminUser(username="other", password_hash=hash_password("oldpassword"))
        db_session.add(other); await db_session.commit(); await db_session.refresh(other)

        res = await client.put(
            f"/api/admin/admin-users/{other.id}",
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
            json={"is_active": False},
        )
        assert res.status_code == 200
        assert res.json()["is_active"] is False


class TestDeleteAdminUser:
    async def test_cannot_delete_self(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        admin, cookies = await _make_admin_and_cookie(db_session)
        res = await client.delete(
            f"/api/admin/admin-users/{admin.id}",
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
        )
        assert res.status_code == 400

    async def test_delete_other(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        admin, cookies = await _make_admin_and_cookie(db_session)
        other = AdminUser(username="other", password_hash=hash_password("oldpassword"))
        db_session.add(other); await db_session.commit(); await db_session.refresh(other)

        res = await client.delete(
            f"/api/admin/admin-users/{other.id}",
            cookies=cookies,
            headers={"Origin": "http://localhost:5173"},
        )
        assert res.status_code == 204
```

- [ ] **Step 3: Write the router**

Create `src/flexloop/admin/routers/admin_users.py`:

```python
"""Admin CRUD endpoints for the ``admin_users`` table itself.

Security notes:
- Passwords are never returned in responses; only ``AdminAdminUserResponse``
  is used as ``response_model``, which has no password fields.
- Create hashes the password with bcrypt via the phase 1 ``hash_password``.
- Update re-hashes the password only when present (partial update).
- Delete refuses to delete the currently-authenticated admin — you can't
  lock yourself out.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import hash_password, require_admin
from flexloop.admin.crud import paginated_response, parse_filter_params, parse_sort_spec
from flexloop.admin.schemas.admin_users import (
    AdminAdminUserCreate,
    AdminAdminUserResponse,
    AdminAdminUserUpdate,
)
from flexloop.admin.schemas.common import ListQueryParams, PaginatedResponse
from flexloop.db.engine import get_session
from flexloop.models.admin_user import AdminUser

router = APIRouter(prefix="/api/admin/admin-users", tags=["admin:admin-users"])

ALLOWED_SORT = {"id", "username", "created_at", "last_login_at"}
ALLOWED_FILTER = {"is_active"}


@router.get("", response_model=PaginatedResponse[AdminAdminUserResponse])
async def list_admin_users(
    request: Request,
    params: ListQueryParams = Depends(ListQueryParams.as_dependency),
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> dict:
    query = select(AdminUser)
    for key, value in parse_filter_params(request.query_params, allowed=ALLOWED_FILTER).items():
        if key == "is_active":
            query = query.where(AdminUser.is_active.is_(value.lower() in ("true", "1")))
        else:
            query = query.where(getattr(AdminUser, key) == value)

    if params.search:
        query = query.where(AdminUser.username.ilike(f"%{params.search}%"))

    sort_clauses = parse_sort_spec(params.sort, model=AdminUser, allowed=ALLOWED_SORT)
    query = query.order_by(*sort_clauses) if sort_clauses else query.order_by(AdminUser.username.asc())

    return await paginated_response(
        db, query=query, item_schema=AdminAdminUserResponse,
        page=params.page, per_page=params.per_page,
    )


@router.get("/{admin_user_id}", response_model=AdminAdminUserResponse)
async def get_admin_user(
    admin_user_id: int,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> AdminUser:
    result = await db.execute(select(AdminUser).where(AdminUser.id == admin_user_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "admin user not found")
    return row


@router.post("", response_model=AdminAdminUserResponse, status_code=201)
async def create_admin_user(
    payload: AdminAdminUserCreate,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> AdminUser:
    # Uniqueness check — prefer a clean 409 over SQL integrity error
    existing = await db.execute(
        select(AdminUser).where(AdminUser.username == payload.username)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "username already exists")

    row = AdminUser(
        username=payload.username,
        password_hash=hash_password(payload.password),
        is_active=payload.is_active,
    )
    db.add(row); await db.commit(); await db.refresh(row)
    return row


@router.put("/{admin_user_id}", response_model=AdminAdminUserResponse)
async def update_admin_user(
    admin_user_id: int,
    payload: AdminAdminUserUpdate,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> AdminUser:
    result = await db.execute(select(AdminUser).where(AdminUser.id == admin_user_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "admin user not found")

    data = payload.model_dump(exclude_unset=True)
    if "password" in data:
        row.password_hash = hash_password(data.pop("password"))
    for field, value in data.items():
        setattr(row, field, value)

    await db.commit(); await db.refresh(row)
    return row


@router.delete("/{admin_user_id}", status_code=204)
async def delete_admin_user(
    admin_user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current=Depends(require_admin),
) -> None:
    if admin_user_id == current.id:
        raise HTTPException(
            status_code=400,
            detail="cannot delete your own admin account; deactivate instead",
        )
    result = await db.execute(select(AdminUser).where(AdminUser.id == admin_user_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "admin user not found")
    await db.delete(row); await db.commit()
```

- [ ] **Step 4: Wire into main.py**

```python
from flexloop.admin.routers.admin_users import router as admin_admin_users_router
# ...
app.include_router(admin_admin_users_router)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_admin_admin_users.py -v`
Expected: 8 passed (TestListAdminUsers: 2, TestCreateAdminUser: 2, TestUpdateAdminUser: 2, TestDeleteAdminUser: 2).

- [ ] **Step 6: Commit**

```bash
git add src/flexloop/admin/schemas/admin_users.py \
        src/flexloop/admin/routers/admin_users.py \
        src/flexloop/main.py \
        tests/test_admin_admin_users.py
git commit -m "feat(admin): admin_users CRUD router with password re-hash guard"
```

---

### Task 16: Full backend regression check

Before moving to the frontend, confirm the whole backend test suite is green and the OpenAPI doc is sane.

- [ ] **Step 1: Run every test**

Run: `uv run pytest -v`
Expected: all prior tests still green + ~40 new phase 2 tests green.

- [ ] **Step 2: Smoke-check the FastAPI OpenAPI spec**

Run in one terminal:
```bash
uv run uvicorn flexloop.main:app --port 8000
```

In another terminal:
```bash
curl -s http://127.0.0.1:8000/openapi.json | python -m json.tool | grep -E '"(/api/admin/[^"]*)"' | sort -u
```

Expected paths (exact count: 7 resources × ~5 endpoints each + phase 1 endpoints):
```
"/api/admin/admin-users"
"/api/admin/admin-users/{admin_user_id}"
"/api/admin/ai/usage"
"/api/admin/ai/usage/{usage_id}"
"/api/admin/auth/change-password"
"/api/admin/auth/login"
"/api/admin/auth/logout"
"/api/admin/auth/me"
"/api/admin/auth/sessions"
"/api/admin/auth/sessions/{session_id}"
"/api/admin/exercises"
"/api/admin/exercises/{exercise_id}"
"/api/admin/health"
"/api/admin/measurements"
"/api/admin/measurements/{measurement_id}"
"/api/admin/prs"
"/api/admin/prs/{pr_id}"
"/api/admin/users"
"/api/admin/users/{user_id}"
"/api/admin/workouts"
"/api/admin/workouts/{workout_id}"
```

Stop the server after verifying.

- [ ] **Step 3: Commit the regression pass (empty commit to mark the milestone)**

```bash
git commit --allow-empty -m "milestone: all phase 2 backend routers green"
```

---

**End of Chunk 4.** Backend phase 2 is complete. All 7 resource routers are live, ~40 integration tests pass, and the FastAPI OpenAPI doc exposes the full phase 2 schema. Frontend work starts in Chunk 5.

---

## Chunk 5: Frontend Shared CRUD Infrastructure

This chunk builds the frontend building blocks every Chunk 6 page will use: OpenAPI-generated types, generic `useList/useDetail/useCreate/useUpdate/useDelete` hooks over TanStack Query, and the shared `<DataTable>`, `<DeleteDialog>`, `<EditSheet>` / `<JsonEditor>` components. No resource page is written yet — Chunk 6 glues them together.

All paths below are relative to `admin-ui/` inside the flexloop-server worktree.

### Task 17: Add `openapi-typescript` + codegen script

**Files:**
- Modify: `admin-ui/package.json`
- Create: `admin-ui/src/lib/api.types.ts` (generated)

- [ ] **Step 1: Install the dev dependency**

Run from `admin-ui/`:
```bash
npm install --save-dev openapi-typescript@^7 --legacy-peer-deps
```

> **Why `--legacy-peer-deps`:** phase 1 pinned `typescript@~6.0.2` but `openapi-typescript@7.x` declares a peer dep of `typescript@^5.x`. The peer is a dev-time hint — `openapi-typescript` uses TypeScript only as a string emitter, not to typecheck the project — so the generated file works fine under TS 6. Without the flag, npm fails with `ERESOLVE`.

- [ ] **Step 2: Add the codegen script**

Edit `admin-ui/package.json` — add a `codegen` entry inside `scripts`:

```json
{
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "lint": "eslint .",
    "preview": "vite preview",
    "codegen": "openapi-typescript http://127.0.0.1:8000/openapi.json -o src/lib/api.types.ts"
  }
}
```

- [ ] **Step 3: Run the server and codegen once**

In one terminal (from the server root):
```bash
uv run uvicorn flexloop.main:app --port 8000
```

In another (from `admin-ui/`):
```bash
npm run codegen
```

Expected: `src/lib/api.types.ts` is created with TypeScript types matching every FastAPI schema. It starts with a comment like `// This file was auto-generated by openapi-typescript.` and contains a top-level `paths` interface and a `components` interface.

- [ ] **Step 4: Quick sanity check**

Open `admin-ui/src/lib/api.types.ts` and confirm it contains, at minimum:
- A type under `components.schemas.UserAdminResponse`
- A type under `components.schemas.PaginatedResponse_UserAdminResponse_` (pydantic generics serialize with the type arg suffix)
- A type under `components.schemas.WorkoutSessionAdminResponse`

Stop the server after verifying.

- [ ] **Step 5: Commit**

```bash
git add admin-ui/package.json admin-ui/package-lock.json admin-ui/src/lib/api.types.ts
git commit -m "chore(admin-ui): add openapi-typescript codegen + generated types"
```

> **Regeneration workflow going forward:** any time the backend schemas or endpoints change, re-run `npm run codegen` (server must be up). The generated file is committed to git so Chunk 6 hooks can import from it without needing a live server during build.

---

### Task 18: Install shadcn components for CRUD

**Files:**
- Create: `admin-ui/src/components/ui/{table,alert-dialog,select,textarea,tabs,checkbox,badge,pagination,form}.tsx`

Use the shadcn CLI to add the components. If the CLI prompts to overwrite existing files, say no — phase 1 already installed `button`, `card`, `input`, `label`, `dialog`, `sheet`, `sidebar`, `tooltip`, `dropdown-menu`, `sonner`, `skeleton`, `avatar`, `separator`.

- [ ] **Step 1: Add the components**

From `admin-ui/`:
```bash
npx shadcn@latest add table alert-dialog select textarea tabs checkbox badge pagination form
```

Confirm each prompt. The CLI drops files into `src/components/ui/`.

- [ ] **Step 2: Verify the build still compiles**

```bash
npm run build
```

Expected: no errors. The built output goes to `../src/flexloop/static/admin/`.

- [ ] **Step 3: Commit**

```bash
git add admin-ui/src/components/ui/ admin-ui/components.json
git commit -m "chore(admin-ui): install shadcn components for phase 2 CRUD"
```

---

### Task 19: Create `lib/crud.ts` — shared CRUD types

**Files:**
- Create: `admin-ui/src/lib/crud.ts`

Small module that re-exports the common paginated response shape for hooks to reference. Keeping this separate from `lib/api.ts` (the fetch wrapper) keeps concerns clean.

- [ ] **Step 1: Write the file**

Create `admin-ui/src/lib/crud.ts`:

```typescript
/**
 * Shared CRUD types used by the generic useList/useDetail/useCreate/... hooks.
 *
 * `PaginatedResponse<T>` mirrors the backend's ``flexloop.admin.schemas.common.PaginatedResponse``.
 * Resource-specific item types come from `lib/api.types.ts` (generated from the FastAPI OpenAPI).
 */

export type PaginatedResponse<T> = {
  items: T[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
};

export type ListParams = {
  page?: number;
  per_page?: number;
  search?: string;
  sort?: string;
  /** Resource-specific filters. Stored as a flat dict; the hook serializes them to `filter[key]=value`. */
  filters?: Record<string, string | number | boolean | undefined>;
};

/** Turn a ListParams into a flat query-string params object for `api.get(..., params)`. */
export function listParamsToQuery(params: ListParams): Record<string, string | number | undefined> {
  const q: Record<string, string | number | undefined> = {};
  if (params.page !== undefined) q.page = params.page;
  if (params.per_page !== undefined) q.per_page = params.per_page;
  if (params.search) q.search = params.search;
  if (params.sort) q.sort = params.sort;
  if (params.filters) {
    for (const [k, v] of Object.entries(params.filters)) {
      if (v === undefined || v === "" || v === null) continue;
      q[`filter[${k}]`] = String(v);
    }
  }
  return q;
}
```

- [ ] **Step 2: Lint check**

```bash
npm run lint
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add admin-ui/src/lib/crud.ts
git commit -m "feat(admin-ui): shared CRUD types + listParamsToQuery helper"
```

---

### Task 20: Create generic `useCrud` hooks

**Files:**
- Create: `admin-ui/src/hooks/useCrud.ts`

Thin generic wrappers over TanStack Query. Each hook is parameterized by a resource key (used for both the URL path and the query key). The types are parameterized by the item type from `api.types.ts`.

- [ ] **Step 1: Write the file**

Create `admin-ui/src/hooks/useCrud.ts`:

```typescript
/**
 * Generic CRUD hooks for admin resource pages.
 *
 * Every resource in phase 2 uses the same five operations with the same shape:
 *   - GET /api/admin/{resource}?<params>            → PaginatedResponse<T>
 *   - GET /api/admin/{resource}/{id}                → T
 *   - POST /api/admin/{resource}                    → T
 *   - PUT /api/admin/{resource}/{id}                → T
 *   - DELETE /api/admin/{resource}/{id}             → void
 *
 * The resource key (e.g. "users", "workouts") is used BOTH as the URL path
 * segment and as the root of the TanStack Query key, so invalidating writes
 * across list + detail is automatic.
 *
 * For non-standard paths like "ai/usage", pass the full path.
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { api } from "@/lib/api";
import { ListParams, PaginatedResponse, listParamsToQuery } from "@/lib/crud";

type ResourceKey = string;

function rootKey(resource: ResourceKey): string[] {
  return ["admin", "crud", resource];
}

function listKey(resource: ResourceKey, params: ListParams): (string | ListParams)[] {
  return [...rootKey(resource), "list", params];
}

function detailKey(resource: ResourceKey, id: string | number): (string | number)[] {
  return [...rootKey(resource), "detail", id];
}

export function useList<T>(resource: ResourceKey, params: ListParams = {}) {
  return useQuery({
    queryKey: listKey(resource, params),
    queryFn: () =>
      api.get<PaginatedResponse<T>>(
        `/api/admin/${resource}`,
        listParamsToQuery(params),
      ),
    placeholderData: (prev) => prev, // keep previous page while loading new one
  });
}

export function useDetail<T>(resource: ResourceKey, id: string | number | null) {
  return useQuery({
    queryKey: detailKey(resource, id ?? "none"),
    queryFn: () => api.get<T>(`/api/admin/${resource}/${id}`),
    enabled: id !== null && id !== undefined,
  });
}

export function useCreate<T, TInput>(resource: ResourceKey) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: TInput) => api.post<T>(`/api/admin/${resource}`, input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: rootKey(resource) });
    },
  });
}

export function useUpdate<T, TInput>(resource: ResourceKey) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: string | number; input: TInput }) =>
      api.put<T>(`/api/admin/${resource}/${id}`, input),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: rootKey(resource) });
      qc.invalidateQueries({ queryKey: detailKey(resource, variables.id) });
    },
  });
}

export function useDelete(resource: ResourceKey) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string | number) => api.delete(`/api/admin/${resource}/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: rootKey(resource) });
    },
  });
}
```

- [ ] **Step 2: Lint check**

```bash
npm run lint
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add admin-ui/src/hooks/useCrud.ts
git commit -m "feat(admin-ui): generic useList/useDetail/useCreate/useUpdate/useDelete hooks"
```

---

### Task 21: Create `<DataTable>` component

**Files:**
- Create: `admin-ui/src/components/DataTable.tsx`

A generic, presentational table. The parent page supplies columns + rows + pagination/sort callbacks. No TanStack Table — keeping it hand-rolled keeps the bundle small and the mental model simple for ~7 pages.

- [ ] **Step 1: Write the file**

Create `admin-ui/src/components/DataTable.tsx`:

```typescript
/**
 * Generic data table for admin list pages.
 *
 * Intentionally NOT TanStack Table — that's ~20KB of extra bundle for
 * functionality we don't need (column reordering, row selection, etc.).
 * Each resource page supplies its own column definitions as a list of
 * {key, header, render?} triples.
 *
 * Pagination, sort, and search are HOISTED to the parent: this component
 * is purely presentational. The parent owns the state (usually via
 * useState + useList).
 */
import { ChevronDown, ChevronsUpDown, ChevronUp } from "lucide-react";
import { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export type Column<T> = {
  /** Internal key for sort state. Matches the backend ALLOWED_SORT_COLUMNS. */
  key: string;
  /** Visible header text. */
  header: string;
  /** Optional custom cell renderer. Defaults to `String(row[key])`. */
  render?: (row: T) => ReactNode;
  /** Is this column sortable? Must be in backend's ALLOWED_SORT_COLUMNS. */
  sortable?: boolean;
  /** Optional cell className (e.g. "text-right tabular-nums"). */
  className?: string;
};

export type SortState = {
  column: string;
  direction: "asc" | "desc";
} | null;

type Props<T> = {
  columns: Column<T>[];
  rows: T[];
  isLoading?: boolean;
  isError?: boolean;
  total: number;
  page: number;
  perPage: number;
  search: string;
  onSearchChange: (s: string) => void;
  onPageChange: (page: number) => void;
  sort: SortState;
  onSortChange: (sort: SortState) => void;
  onRowClick?: (row: T) => void;
  /** Resource name used in the empty state message. */
  resourceLabel?: string;
  /** Slot for action buttons (e.g. a "New user" button) above the table. */
  toolbar?: ReactNode;
  rowKey?: (row: T) => string | number;
};

export function DataTable<T>({
  columns,
  rows,
  isLoading = false,
  isError = false,
  total,
  page,
  perPage,
  search,
  onSearchChange,
  onPageChange,
  sort,
  onSortChange,
  onRowClick,
  resourceLabel = "items",
  toolbar,
  rowKey,
}: Props<T>) {
  const totalPages = Math.max(1, Math.ceil(total / perPage));

  const toggleSort = (col: Column<T>) => {
    if (!col.sortable) return;
    if (!sort || sort.column !== col.key) {
      onSortChange({ column: col.key, direction: "asc" });
    } else if (sort.direction === "asc") {
      onSortChange({ column: col.key, direction: "desc" });
    } else {
      onSortChange(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <Input
          placeholder={`Search ${resourceLabel}...`}
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          className="max-w-sm"
        />
        {toolbar}
      </div>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              {columns.map((col) => {
                const isSorted = sort?.column === col.key;
                const Icon = !col.sortable
                  ? null
                  : !isSorted
                    ? ChevronsUpDown
                    : sort.direction === "asc"
                      ? ChevronUp
                      : ChevronDown;
                return (
                  <TableHead
                    key={col.key}
                    onClick={() => toggleSort(col)}
                    className={`${col.sortable ? "cursor-pointer select-none" : ""} ${col.className ?? ""}`}
                  >
                    <span className="inline-flex items-center gap-1">
                      {col.header}
                      {Icon && <Icon className="h-3 w-3 opacity-60" />}
                    </span>
                  </TableHead>
                );
              })}
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              Array.from({ length: Math.min(perPage, 8) }).map((_, i) => (
                <TableRow key={`sk-${i}`}>
                  {columns.map((col) => (
                    <TableCell key={col.key}>
                      <Skeleton className="h-4 w-full" />
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : isError ? (
              <TableRow>
                <TableCell colSpan={columns.length} className="text-center text-sm text-destructive">
                  Failed to load {resourceLabel}.
                </TableCell>
              </TableRow>
            ) : rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={columns.length} className="text-center text-sm text-muted-foreground">
                  No {resourceLabel} found.
                </TableCell>
              </TableRow>
            ) : (
              rows.map((row, i) => (
                <TableRow
                  key={rowKey ? rowKey(row) : i}
                  onClick={() => onRowClick?.(row)}
                  className={onRowClick ? "cursor-pointer" : undefined}
                >
                  {columns.map((col) => (
                    <TableCell key={col.key} className={col.className}>
                      {col.render
                        ? col.render(row)
                        : String((row as unknown as Record<string, unknown>)[col.key] ?? "")}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <div>
          {total === 0
            ? "No results"
            : `Showing ${(page - 1) * perPage + 1}–${Math.min(page * perPage, total)} of ${total}`}
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onPageChange(Math.max(1, page - 1))}
            disabled={page <= 1 || isLoading}
          >
            Previous
          </Button>
          <span>
            Page {page} of {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => onPageChange(Math.min(totalPages, page + 1))}
            disabled={page >= totalPages || isLoading}
          >
            Next
          </Button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Build check**

```bash
npm run build
```

Expected: succeeds.

- [ ] **Step 3: Commit**

```bash
git add admin-ui/src/components/DataTable.tsx
git commit -m "feat(admin-ui): generic DataTable with search, sort, pagination"
```

---

### Task 22: Create `<DeleteDialog>` component

**Files:**
- Create: `admin-ui/src/components/DeleteDialog.tsx`

A small `<AlertDialog>` wrapper. Pages pass a description string (e.g. `"Delete User #4 (Jane Doe)?"`) and an async `onConfirm` handler. The component manages open state internally via a render-prop style trigger.

- [ ] **Step 1: Write the file**

Create `admin-ui/src/components/DeleteDialog.tsx`:

```typescript
/**
 * Reusable confirm-delete dialog.
 *
 * Usage:
 *   const [target, setTarget] = useState<User | null>(null);
 *   const del = useDelete("users");
 *   ...
 *   <DeleteDialog
 *     open={target !== null}
 *     onOpenChange={(o) => !o && setTarget(null)}
 *     title={`Delete user "${target?.name}"?`}
 *     description="This cannot be undone."
 *     isPending={del.isPending}
 *     onConfirm={async () => {
 *       if (target) await del.mutateAsync(target.id);
 *       setTarget(null);
 *     }}
 *   />
 */
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  confirmLabel?: string;
  isPending?: boolean;
  onConfirm: () => void | Promise<void>;
};

export function DeleteDialog({
  open,
  onOpenChange,
  title,
  description = "This cannot be undone.",
  confirmLabel = "Delete",
  isPending = false,
  onConfirm,
}: Props) {
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={isPending}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={(e) => {
              e.preventDefault();
              void onConfirm();
            }}
            disabled={isPending}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            {isPending ? "Deleting..." : confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
```

- [ ] **Step 2: Build check**

```bash
npm run build
```

- [ ] **Step 3: Commit**

```bash
git add admin-ui/src/components/DeleteDialog.tsx
git commit -m "feat(admin-ui): DeleteDialog component"
```

---

### Task 23: Create `<JsonEditor>` component

**Files:**
- Create: `admin-ui/src/components/JsonEditor.tsx`

Simple textarea wrapper that parses JSON on save and surfaces errors inline. Used as the "JSON" tab inside `<EditSheet>` for the escape hatch described in spec §9.4.

> **Deliberate deviation from spec §9.4.** The spec suggests `@uiw/react-json-view` or CodeMirror with JSON mode. Phase 2 ships a plain `<Textarea>` instead because (1) only ~7 resources need it, (2) a 30-80 KB editor library isn't worth the bundle cost for admin tooling, (3) if phase 4 adds CodeMirror for the prompt editor we can revisit and drop in CodeMirror's JSON mode here. Revisit the pick during phase 4 planning.

- [ ] **Step 1: Write the file**

Create `admin-ui/src/components/JsonEditor.tsx`:

```typescript
/**
 * Simple JSON escape hatch — a textarea that validates on save.
 *
 * This is NOT a syntax-highlighted JSON editor; for ~7 admin resources
 * that's overkill. If we ever add CodeMirror for the prompt editor in
 * phase 4, revisit whether to reuse it here.
 */
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

type Props<T> = {
  value: T;
  onSave: (parsed: T) => void | Promise<void>;
  isSaving?: boolean;
};

export function JsonEditor<T>({ value, onSave, isSaving = false }: Props<T>) {
  const initial = JSON.stringify(value, null, 2);
  const [text, setText] = useState(initial);
  const [error, setError] = useState<string | null>(null);

  const handleSave = async () => {
    let parsed: T;
    try {
      parsed = JSON.parse(text) as T;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Invalid JSON");
      return;
    }
    setError(null);
    await onSave(parsed);
  };

  const isDirty = text !== initial;

  return (
    <div className="space-y-2">
      <Textarea
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setError(null);
        }}
        rows={18}
        className="font-mono text-xs"
        spellCheck={false}
      />
      {error && (
        <p className="text-xs text-destructive">{error}</p>
      )}
      <div className="flex justify-end gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            setText(initial);
            setError(null);
          }}
          disabled={!isDirty || isSaving}
        >
          Reset
        </Button>
        <Button size="sm" onClick={handleSave} disabled={!isDirty || isSaving}>
          {isSaving ? "Saving..." : "Save JSON"}
        </Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Build check**

```bash
npm run build
```

- [ ] **Step 3: Commit**

```bash
git add admin-ui/src/components/JsonEditor.tsx
git commit -m "feat(admin-ui): JSON escape hatch editor component"
```

---

### Task 24: Create `<EditSheet>` component with Form + JSON tabs

**Files:**
- Create: `admin-ui/src/components/EditSheet.tsx`

Slide-out drawer with two tabs: "Form" (where the parent renders a hand-written react-hook-form) and "JSON" (the `<JsonEditor>`). When creating a new resource, the JSON tab is hidden (no existing object to edit).

- [ ] **Step 1: Write the file**

Create `admin-ui/src/components/EditSheet.tsx`:

```typescript
/**
 * Slide-out drawer for creating/editing admin resources.
 *
 * Exposes two tabs:
 *  - "Form": whatever node the parent passes via the `form` prop (typically
 *    a resource-specific react-hook-form component).
 *  - "JSON": the raw JSON editor, only shown when editing an existing row.
 *
 * The parent owns the mutation state. This component is just layout.
 */
import { ReactNode } from "react";

import { JsonEditor } from "@/components/JsonEditor";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";

type Props<T> = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  /** The current row being edited. If null, the JSON tab is hidden. */
  row: T | null;
  form: ReactNode;
  onJsonSave: (parsed: T) => void | Promise<void>;
  isSaving?: boolean;
};

export function EditSheet<T>({
  open,
  onOpenChange,
  title,
  description,
  row,
  form,
  onJsonSave,
  isSaving = false,
}: Props<T>) {
  const showJson = row !== null;
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-xl overflow-y-auto">
        <SheetHeader>
          <SheetTitle>{title}</SheetTitle>
          {description && <SheetDescription>{description}</SheetDescription>}
        </SheetHeader>

        <div className="mt-6">
          {showJson ? (
            <Tabs defaultValue="form">
              <TabsList>
                <TabsTrigger value="form">Form</TabsTrigger>
                <TabsTrigger value="json">JSON</TabsTrigger>
              </TabsList>
              <TabsContent value="form" className="mt-4">
                {form}
              </TabsContent>
              <TabsContent value="json" className="mt-4">
                <JsonEditor value={row} onSave={onJsonSave} isSaving={isSaving} />
              </TabsContent>
            </Tabs>
          ) : (
            form
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
```

- [ ] **Step 2: Build check**

```bash
npm run build
```

Expected: succeeds. All Chunk 5 components compile together now.

- [ ] **Step 3: Commit**

```bash
git add admin-ui/src/components/EditSheet.tsx
git commit -m "feat(admin-ui): EditSheet component with Form + JSON tabs"
```

---

**End of Chunk 5.** Frontend shared infrastructure is complete:
- `openapi-typescript` codegen set up; `src/lib/api.types.ts` generated.
- 9 new shadcn components installed.
- `lib/crud.ts` with shared types + `listParamsToQuery`.
- `hooks/useCrud.ts` with 5 generic hooks.
- `components/DataTable.tsx`, `DeleteDialog.tsx`, `JsonEditor.tsx`, `EditSheet.tsx`.

Chunk 6 glues these into 7 resource pages.

---

## Chunk 6: Frontend Resource Pages

This chunk wires every phase 2 resource into a working page. The UsersPage is the canonical template written out in full. Measurements and Workouts get full listings too because they show distinct patterns (simple flat vs. nested embedded children). The remaining four resources (PRs, Exercises, AI Usage, Admin Users) share the same shape; Task 28 lists their deltas against the canonical.

All files in this chunk live under `admin-ui/src/`.

### Task 25: UserForm + UsersPage (canonical)

**Files:**
- Create: `admin-ui/src/components/forms/UserForm.tsx`
- Create: `admin-ui/src/pages/UsersPage.tsx`

- [ ] **Step 1: Create `components/forms/UserForm.tsx`**

```typescript
/**
 * Hand-written react-hook-form + zod form for Users.
 *
 * Why hand-written: auto-form generators make a mess of JSON array columns
 * like `available_equipment`. The per-resource form is ~80 lines and worth
 * the clarity.
 */
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { components } from "@/lib/api.types";

type UserAdminResponse = components["schemas"]["UserAdminResponse"];

const schema = z.object({
  name: z.string().min(1).max(100),
  gender: z.string().min(1).max(20),
  age: z.coerce.number().int().min(0).max(150),
  height: z.coerce.number().positive(),
  weight: z.coerce.number().positive(),
  weight_unit: z.string().default("kg"),
  height_unit: z.string().default("cm"),
  experience_level: z.string().min(1).max(20),
  goals: z.string().max(500).default(""),
  available_equipment_csv: z.string().default(""),
});

export type UserFormValues = z.infer<typeof schema>;

type Props = {
  defaultValues?: UserAdminResponse | null;
  onSubmit: (values: UserFormValues & { available_equipment: string[] | null }) => void | Promise<void>;
  isSaving?: boolean;
};

export function UserForm({ defaultValues, onSubmit, isSaving = false }: Props) {
  const { register, handleSubmit, formState: { errors } } = useForm<UserFormValues>({
    resolver: zodResolver(schema),
    defaultValues: defaultValues
      ? {
          name: defaultValues.name,
          gender: defaultValues.gender,
          age: defaultValues.age,
          height: defaultValues.height,
          weight: defaultValues.weight,
          weight_unit: defaultValues.weight_unit,
          height_unit: defaultValues.height_unit,
          experience_level: defaultValues.experience_level,
          goals: defaultValues.goals,
          available_equipment_csv: (defaultValues.available_equipment ?? []).join(", "),
        }
      : {
          name: "", gender: "other", age: 30, height: 170, weight: 70,
          weight_unit: "kg", height_unit: "cm", experience_level: "intermediate",
          goals: "", available_equipment_csv: "",
        },
  });

  const submit = handleSubmit(async (values) => {
    const equipment = values.available_equipment_csv
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    await onSubmit({ ...values, available_equipment: equipment.length ? equipment : null });
  });

  const field = (name: keyof UserFormValues, label: string, props: React.InputHTMLAttributes<HTMLInputElement> = {}) => (
    <div className="space-y-1">
      <Label htmlFor={name}>{label}</Label>
      <Input id={name} {...props} {...register(name)} />
      {errors[name] && <p className="text-xs text-destructive">{String(errors[name]?.message)}</p>}
    </div>
  );

  return (
    <form onSubmit={submit} className="space-y-4">
      {field("name", "Name")}
      {field("gender", "Gender")}
      <div className="grid grid-cols-2 gap-3">
        {field("age", "Age", { type: "number", min: 0, max: 150 })}
        {field("experience_level", "Experience")}
      </div>
      <div className="grid grid-cols-2 gap-3">
        {field("height", "Height", { type: "number", step: "0.1" })}
        {field("height_unit", "Height unit")}
      </div>
      <div className="grid grid-cols-2 gap-3">
        {field("weight", "Weight", { type: "number", step: "0.1" })}
        {field("weight_unit", "Weight unit")}
      </div>

      <div className="space-y-1">
        <Label htmlFor="goals">Goals</Label>
        <Textarea id="goals" rows={3} {...register("goals")} />
      </div>

      <div className="space-y-1">
        <Label htmlFor="available_equipment_csv">Available equipment (comma-separated)</Label>
        <Input
          id="available_equipment_csv"
          placeholder="barbell, dumbbells, cables"
          {...register("available_equipment_csv")}
        />
      </div>

      <div className="flex justify-end gap-2 pt-2">
        <Button type="submit" disabled={isSaving}>
          {isSaving ? "Saving..." : defaultValues ? "Save changes" : "Create user"}
        </Button>
      </div>
    </form>
  );
}
```

- [ ] **Step 2: Create `pages/UsersPage.tsx`**

```typescript
/**
 * Users admin page — canonical template for all phase 2 CRUD pages.
 *
 * State layout:
 *   - page/per_page/search/sort  → local state, passed to useList
 *   - editTarget                 → null | "new" | User (drives EditSheet)
 *   - deleteTarget               → null | User (drives DeleteDialog)
 *
 * This page is deliberately written without any helper/abstraction for the
 * table-edit-delete trio. Six more resource pages follow the exact same
 * pattern; consolidating them behind a generic <ResourcePage> would save
 * lines but hurt readability for a 7-page surface.
 */
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { DataTable, Column, SortState } from "@/components/DataTable";
import { DeleteDialog } from "@/components/DeleteDialog";
import { EditSheet } from "@/components/EditSheet";
import { UserForm } from "@/components/forms/UserForm";
import { useCreate, useDelete, useList, useUpdate } from "@/hooks/useCrud";
import { components } from "@/lib/api.types";

type User = components["schemas"]["UserAdminResponse"];
type UserCreate = components["schemas"]["UserAdminCreate"];
type UserUpdate = components["schemas"]["UserAdminUpdate"];

const RESOURCE = "users";

const COLUMNS: Column<User>[] = [
  { key: "id", header: "ID", sortable: true, className: "w-16 tabular-nums" },
  { key: "name", header: "Name", sortable: true },
  { key: "gender", header: "Gender" },
  { key: "age", header: "Age", sortable: true, className: "w-16 tabular-nums" },
  { key: "experience_level", header: "Experience", sortable: true },
  {
    key: "available_equipment",
    header: "Equipment",
    render: (u) => (u.available_equipment ?? []).join(", ") || "—",
  },
];

export function UsersPage() {
  const [page, setPage] = useState(1);
  const [perPage] = useState(50);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortState>(null);
  const [editTarget, setEditTarget] = useState<User | "new" | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<User | null>(null);

  const list = useList<User>(RESOURCE, {
    page,
    per_page: perPage,
    search: search || undefined,
    sort: sort ? `${sort.column}:${sort.direction}` : undefined,
  });

  const create = useCreate<User, UserCreate>(RESOURCE);
  const update = useUpdate<User, UserUpdate>(RESOURCE);
  const del = useDelete(RESOURCE);

  const handleFormSubmit = async (
    values: Parameters<React.ComponentProps<typeof UserForm>["onSubmit"]>[0],
  ) => {
    try {
      if (editTarget === "new") {
        await create.mutateAsync(values as UserCreate);
        toast.success("User created");
      } else if (editTarget) {
        await update.mutateAsync({ id: editTarget.id, input: values as UserUpdate });
        toast.success("User updated");
      }
      setEditTarget(null);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Save failed");
    }
  };

  const handleJsonSave = async (parsed: User) => {
    if (editTarget === "new" || !editTarget) return;
    try {
      const { id, created_at, ...rest } = parsed;
      await update.mutateAsync({ id: editTarget.id, input: rest as UserUpdate });
      toast.success("User updated via JSON");
      setEditTarget(null);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "JSON save failed");
    }
  };

  const handleDeleteConfirm = async () => {
    if (!deleteTarget) return;
    try {
      await del.mutateAsync(deleteTarget.id);
      toast.success("User deleted");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setDeleteTarget(null);
    }
  };

  const columns: Column<User>[] = [
    ...COLUMNS,
    {
      key: "_actions",
      header: "",
      className: "w-32 text-right",
      render: (u) => (
        <div className="flex justify-end gap-1">
          <Button size="sm" variant="outline" onClick={(e) => { e.stopPropagation(); setEditTarget(u); }}>
            Edit
          </Button>
          <Button size="sm" variant="ghost" onClick={(e) => { e.stopPropagation(); setDeleteTarget(u); }}>
            Delete
          </Button>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Users</h1>
      </div>

      <DataTable<User>
        columns={columns}
        rows={list.data?.items ?? []}
        isLoading={list.isLoading}
        isError={list.isError}
        total={list.data?.total ?? 0}
        page={page}
        perPage={perPage}
        search={search}
        onSearchChange={(s) => { setSearch(s); setPage(1); }}
        onPageChange={setPage}
        sort={sort}
        onSortChange={setSort}
        rowKey={(u) => u.id}
        resourceLabel="users"
        toolbar={<Button onClick={() => setEditTarget("new")}>New user</Button>}
      />

      <EditSheet<User>
        open={editTarget !== null}
        onOpenChange={(o) => !o && setEditTarget(null)}
        title={editTarget === "new" ? "New user" : `Edit user #${editTarget && editTarget !== "new" ? editTarget.id : ""}`}
        row={editTarget && editTarget !== "new" ? editTarget : null}
        form={
          <UserForm
            defaultValues={editTarget && editTarget !== "new" ? editTarget : null}
            onSubmit={handleFormSubmit}
            isSaving={create.isPending || update.isPending}
          />
        }
        onJsonSave={handleJsonSave}
        isSaving={update.isPending}
      />

      <DeleteDialog
        open={deleteTarget !== null}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
        title={deleteTarget ? `Delete user "${deleteTarget.name}"?` : ""}
        description="This cannot be undone."
        isPending={del.isPending}
        onConfirm={handleDeleteConfirm}
      />
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add admin-ui/src/components/forms/UserForm.tsx admin-ui/src/pages/UsersPage.tsx
git commit -m "feat(admin-ui): users CRUD page (canonical resource template)"
```

---

### Task 26: MeasurementForm + MeasurementsPage

**Files:**
- Create: `admin-ui/src/components/forms/MeasurementForm.tsx`
- Create: `admin-ui/src/pages/MeasurementsPage.tsx`

Follows the Users template exactly; only the form schema, columns, and default filters differ. The full source for both files is shown — **do not import from UsersPage**; the goal is that each resource page is independently readable without cross-file hopping.

- [ ] **Step 1: Create `components/forms/MeasurementForm.tsx`**

```typescript
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { components } from "@/lib/api.types";

type Measurement = components["schemas"]["MeasurementAdminResponse"];

const schema = z.object({
  user_id: z.coerce.number().int().positive(),
  date: z.string().min(1),  // "YYYY-MM-DD"
  type: z.string().min(1).max(20),
  value: z.coerce.number(),
  notes: z.string().nullable().optional(),
});

export type MeasurementFormValues = z.infer<typeof schema>;

type Props = {
  defaultValues?: Measurement | null;
  onSubmit: (values: MeasurementFormValues) => void | Promise<void>;
  isSaving?: boolean;
};

export function MeasurementForm({ defaultValues, onSubmit, isSaving = false }: Props) {
  const { register, handleSubmit, formState: { errors } } = useForm<MeasurementFormValues>({
    resolver: zodResolver(schema),
    defaultValues: defaultValues
      ? {
          user_id: defaultValues.user_id,
          date: defaultValues.date,
          type: defaultValues.type,
          value: defaultValues.value,
          notes: defaultValues.notes ?? "",
        }
      : { user_id: 1, date: new Date().toISOString().slice(0, 10), type: "weight", value: 0, notes: "" },
  });

  return (
    <form onSubmit={handleSubmit((v) => onSubmit(v))} className="space-y-4">
      <div className="space-y-1">
        <Label htmlFor="user_id">User ID</Label>
        <Input id="user_id" type="number" {...register("user_id")} />
        {errors.user_id && <p className="text-xs text-destructive">{errors.user_id.message}</p>}
      </div>
      <div className="space-y-1">
        <Label htmlFor="date">Date</Label>
        <Input id="date" type="date" {...register("date")} />
      </div>
      <div className="space-y-1">
        <Label htmlFor="type">Type</Label>
        <Input id="type" placeholder="weight, body_fat, chest..." {...register("type")} />
      </div>
      <div className="space-y-1">
        <Label htmlFor="value">Value</Label>
        <Input id="value" type="number" step="0.1" {...register("value")} />
      </div>
      <div className="space-y-1">
        <Label htmlFor="notes">Notes</Label>
        <Textarea id="notes" rows={3} {...register("notes")} />
      </div>
      <div className="flex justify-end pt-2">
        <Button type="submit" disabled={isSaving}>
          {isSaving ? "Saving..." : defaultValues ? "Save changes" : "Create measurement"}
        </Button>
      </div>
    </form>
  );
}
```

- [ ] **Step 2: Create `pages/MeasurementsPage.tsx`**

```typescript
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { DataTable, Column, SortState } from "@/components/DataTable";
import { DeleteDialog } from "@/components/DeleteDialog";
import { EditSheet } from "@/components/EditSheet";
import { MeasurementForm } from "@/components/forms/MeasurementForm";
import { useCreate, useDelete, useList, useUpdate } from "@/hooks/useCrud";
import { components } from "@/lib/api.types";

type Measurement = components["schemas"]["MeasurementAdminResponse"];
type MeasurementCreate = components["schemas"]["MeasurementAdminCreate"];
type MeasurementUpdate = components["schemas"]["MeasurementAdminUpdate"];

const RESOURCE = "measurements";

export function MeasurementsPage() {
  const [page, setPage] = useState(1);
  const [perPage] = useState(50);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortState>(null);
  const [editTarget, setEditTarget] = useState<Measurement | "new" | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Measurement | null>(null);

  const list = useList<Measurement>(RESOURCE, {
    page, per_page: perPage,
    search: search || undefined,
    sort: sort ? `${sort.column}:${sort.direction}` : undefined,
  });
  const create = useCreate<Measurement, MeasurementCreate>(RESOURCE);
  const update = useUpdate<Measurement, MeasurementUpdate>(RESOURCE);
  const del = useDelete(RESOURCE);

  const columns: Column<Measurement>[] = [
    { key: "id", header: "ID", sortable: true, className: "w-16 tabular-nums" },
    { key: "user_id", header: "User", sortable: true, className: "w-20 tabular-nums" },
    { key: "date", header: "Date", sortable: true, className: "w-28" },
    { key: "type", header: "Type" },
    { key: "value", header: "Value", sortable: true, className: "text-right tabular-nums" },
    { key: "notes", header: "Notes", render: (m) => m.notes ?? "—" },
    {
      key: "_actions", header: "", className: "w-32 text-right",
      render: (m) => (
        <div className="flex justify-end gap-1">
          <Button size="sm" variant="outline" onClick={(e) => { e.stopPropagation(); setEditTarget(m); }}>Edit</Button>
          <Button size="sm" variant="ghost" onClick={(e) => { e.stopPropagation(); setDeleteTarget(m); }}>Delete</Button>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Measurements</h1>
      <DataTable<Measurement>
        columns={columns}
        rows={list.data?.items ?? []}
        isLoading={list.isLoading} isError={list.isError}
        total={list.data?.total ?? 0}
        page={page} perPage={perPage} search={search}
        onSearchChange={(s) => { setSearch(s); setPage(1); }}
        onPageChange={setPage}
        sort={sort} onSortChange={setSort}
        rowKey={(m) => m.id}
        resourceLabel="measurements"
        toolbar={<Button onClick={() => setEditTarget("new")}>New measurement</Button>}
      />
      <EditSheet<Measurement>
        open={editTarget !== null}
        onOpenChange={(o) => !o && setEditTarget(null)}
        title={editTarget === "new" ? "New measurement" : `Edit measurement`}
        row={editTarget && editTarget !== "new" ? editTarget : null}
        form={
          <MeasurementForm
            defaultValues={editTarget && editTarget !== "new" ? editTarget : null}
            isSaving={create.isPending || update.isPending}
            onSubmit={async (v) => {
              try {
                if (editTarget === "new") {
                  await create.mutateAsync(v as MeasurementCreate);
                  toast.success("Measurement created");
                } else if (editTarget) {
                  await update.mutateAsync({ id: editTarget.id, input: v as MeasurementUpdate });
                  toast.success("Measurement updated");
                }
                setEditTarget(null);
              } catch (e) {
                toast.error(e instanceof Error ? e.message : "Save failed");
              }
            }}
          />
        }
        onJsonSave={async (parsed) => {
          if (editTarget === "new" || !editTarget) return;
          try {
            const { id, ...rest } = parsed;
            await update.mutateAsync({ id: editTarget.id, input: rest as MeasurementUpdate });
            toast.success("Measurement updated via JSON");
            setEditTarget(null);
          } catch (e) {
            toast.error(e instanceof Error ? e.message : "JSON save failed");
          }
        }}
        isSaving={update.isPending}
      />
      <DeleteDialog
        open={deleteTarget !== null}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
        title={deleteTarget ? `Delete measurement #${deleteTarget.id}?` : ""}
        isPending={del.isPending}
        onConfirm={async () => {
          if (!deleteTarget) return;
          try {
            await del.mutateAsync(deleteTarget.id);
            toast.success("Measurement deleted");
          } catch (e) {
            toast.error(e instanceof Error ? e.message : "Delete failed");
          } finally {
            setDeleteTarget(null);
          }
        }}
      />
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add admin-ui/src/components/forms/MeasurementForm.tsx admin-ui/src/pages/MeasurementsPage.tsx
git commit -m "feat(admin-ui): measurements CRUD page"
```

---

### Task 27: WorkoutForm + WorkoutsPage

**Files:**
- Create: `admin-ui/src/components/forms/WorkoutForm.tsx`
- Create: `admin-ui/src/pages/WorkoutsPage.tsx`

WorkoutsPage has one non-standard detail: the list rows include an embedded `sets` array that we render in a read-only expandable row. For phase 2 scope this is just "show N sets"; editing individual sets is deferred. The page also wires up the `completed` filter dropdown (true/false/any).

- [ ] **Step 1: Create `components/forms/WorkoutForm.tsx`**

```typescript
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { components } from "@/lib/api.types";

type Workout = components["schemas"]["WorkoutSessionAdminResponse"];

const schema = z.object({
  user_id: z.coerce.number().int().positive(),
  source: z.string().default("plan"),
  plan_day_id: z.coerce.number().int().positive().nullable().optional(),
  template_id: z.coerce.number().int().positive().nullable().optional(),
  started_at: z.string().min(1),
  completed_at: z.string().nullable().optional(),
  notes: z.string().nullable().optional(),
});

export type WorkoutFormValues = z.infer<typeof schema>;

type Props = {
  defaultValues?: Workout | null;
  onSubmit: (values: WorkoutFormValues) => void | Promise<void>;
  isSaving?: boolean;
};

export function WorkoutForm({ defaultValues, onSubmit, isSaving = false }: Props) {
  const { register, handleSubmit } = useForm<WorkoutFormValues>({
    resolver: zodResolver(schema),
    defaultValues: defaultValues
      ? {
          user_id: defaultValues.user_id,
          source: defaultValues.source,
          plan_day_id: defaultValues.plan_day_id ?? undefined,
          template_id: defaultValues.template_id ?? undefined,
          started_at: defaultValues.started_at,
          completed_at: defaultValues.completed_at ?? "",
          notes: defaultValues.notes ?? "",
        }
      : {
          user_id: 1, source: "plan",
          started_at: new Date().toISOString().slice(0, 16),
          completed_at: "", notes: "",
        },
  });

  return (
    <form onSubmit={handleSubmit((v) => onSubmit(v))} className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label htmlFor="user_id">User ID</Label>
          <Input id="user_id" type="number" {...register("user_id")} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="source">Source</Label>
          <Input id="source" placeholder="plan, custom..." {...register("source")} />
        </div>
      </div>
      <div className="space-y-1">
        <Label htmlFor="started_at">Started at</Label>
        <Input id="started_at" type="datetime-local" {...register("started_at")} />
      </div>
      <div className="space-y-1">
        <Label htmlFor="completed_at">Completed at (leave blank if in progress)</Label>
        <Input id="completed_at" type="datetime-local" {...register("completed_at")} />
      </div>
      <div className="space-y-1">
        <Label htmlFor="notes">Notes</Label>
        <Textarea id="notes" rows={3} {...register("notes")} />
      </div>
      <div className="flex justify-end pt-2">
        <Button type="submit" disabled={isSaving}>
          {isSaving ? "Saving..." : defaultValues ? "Save changes" : "Create workout"}
        </Button>
      </div>
    </form>
  );
}
```

- [ ] **Step 2: Create `pages/WorkoutsPage.tsx`**

```typescript
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { DataTable, Column, SortState } from "@/components/DataTable";
import { DeleteDialog } from "@/components/DeleteDialog";
import { EditSheet } from "@/components/EditSheet";
import { WorkoutForm } from "@/components/forms/WorkoutForm";
import { useCreate, useDelete, useList, useUpdate } from "@/hooks/useCrud";
import { components } from "@/lib/api.types";

type Workout = components["schemas"]["WorkoutSessionAdminResponse"];
type WorkoutCreate = components["schemas"]["WorkoutSessionAdminCreate"];
type WorkoutUpdate = components["schemas"]["WorkoutSessionAdminUpdate"];

const RESOURCE = "workouts";

export function WorkoutsPage() {
  const [page, setPage] = useState(1);
  const [perPage] = useState(50);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortState>(null);
  const [completed, setCompleted] = useState<"any" | "true" | "false">("any");
  const [editTarget, setEditTarget] = useState<Workout | "new" | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Workout | null>(null);

  const list = useList<Workout>(RESOURCE, {
    page, per_page: perPage,
    search: search || undefined,
    sort: sort ? `${sort.column}:${sort.direction}` : undefined,
    filters: { completed: completed === "any" ? undefined : completed },
  });
  const create = useCreate<Workout, WorkoutCreate>(RESOURCE);
  const update = useUpdate<Workout, WorkoutUpdate>(RESOURCE);
  const del = useDelete(RESOURCE);

  const columns: Column<Workout>[] = [
    { key: "id", header: "ID", sortable: true, className: "w-16 tabular-nums" },
    { key: "user_id", header: "User", sortable: true, className: "w-20 tabular-nums" },
    { key: "started_at", header: "Started", sortable: true, render: (w) => w.started_at.replace("T", " ").slice(0, 16) },
    {
      key: "status", header: "Status",
      render: (w) => w.completed_at
        ? <Badge variant="secondary">Completed</Badge>
        : <Badge>In progress</Badge>,
    },
    { key: "source", header: "Source" },
    {
      key: "sets_count", header: "Sets",
      render: (w) => <span className="tabular-nums">{w.sets.length}</span>,
      className: "text-right",
    },
    {
      key: "_actions", header: "", className: "w-32 text-right",
      render: (w) => (
        <div className="flex justify-end gap-1">
          <Button size="sm" variant="outline" onClick={(e) => { e.stopPropagation(); setEditTarget(w); }}>Edit</Button>
          <Button size="sm" variant="ghost" onClick={(e) => { e.stopPropagation(); setDeleteTarget(w); }}>Delete</Button>
        </div>
      ),
    },
  ];

  const toolbar = (
    <div className="flex items-center gap-2">
      <Select value={completed} onValueChange={(v) => { setCompleted(v as typeof completed); setPage(1); }}>
        <SelectTrigger className="w-36"><SelectValue /></SelectTrigger>
        <SelectContent>
          <SelectItem value="any">All</SelectItem>
          <SelectItem value="true">Completed</SelectItem>
          <SelectItem value="false">In progress</SelectItem>
        </SelectContent>
      </Select>
      <Button onClick={() => setEditTarget("new")}>New workout</Button>
    </div>
  );

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Workouts</h1>
      <DataTable<Workout>
        columns={columns}
        rows={list.data?.items ?? []}
        isLoading={list.isLoading} isError={list.isError}
        total={list.data?.total ?? 0}
        page={page} perPage={perPage} search={search}
        onSearchChange={(s) => { setSearch(s); setPage(1); }}
        onPageChange={setPage}
        sort={sort} onSortChange={setSort}
        rowKey={(w) => w.id}
        resourceLabel="workouts"
        toolbar={toolbar}
      />
      <EditSheet<Workout>
        open={editTarget !== null}
        onOpenChange={(o) => !o && setEditTarget(null)}
        title={editTarget === "new" ? "New workout" : `Edit workout #${editTarget && editTarget !== "new" ? editTarget.id : ""}`}
        row={editTarget && editTarget !== "new" ? editTarget : null}
        form={
          <WorkoutForm
            defaultValues={editTarget && editTarget !== "new" ? editTarget : null}
            isSaving={create.isPending || update.isPending}
            onSubmit={async (v) => {
              try {
                const payload = {
                  ...v,
                  completed_at: v.completed_at || null,
                  notes: v.notes || null,
                };
                if (editTarget === "new") {
                  await create.mutateAsync(payload as WorkoutCreate);
                  toast.success("Workout created");
                } else if (editTarget) {
                  await update.mutateAsync({ id: editTarget.id, input: payload as WorkoutUpdate });
                  toast.success("Workout updated");
                }
                setEditTarget(null);
              } catch (e) {
                toast.error(e instanceof Error ? e.message : "Save failed");
              }
            }}
          />
        }
        onJsonSave={async (parsed) => {
          if (editTarget === "new" || !editTarget) return;
          try {
            const { id, sets, ...rest } = parsed;
            await update.mutateAsync({ id: editTarget.id, input: rest as WorkoutUpdate });
            toast.success("Workout updated via JSON");
            setEditTarget(null);
          } catch (e) {
            toast.error(e instanceof Error ? e.message : "JSON save failed");
          }
        }}
        isSaving={update.isPending}
      />
      <DeleteDialog
        open={deleteTarget !== null}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
        title={deleteTarget ? `Delete workout #${deleteTarget.id}?` : ""}
        description={deleteTarget && deleteTarget.sets.length > 0
          ? `This will also delete ${deleteTarget.sets.length} set${deleteTarget.sets.length === 1 ? "" : "s"}. This cannot be undone.`
          : "This cannot be undone."}
        isPending={del.isPending}
        onConfirm={async () => {
          if (!deleteTarget) return;
          try {
            await del.mutateAsync(deleteTarget.id);
            toast.success("Workout deleted");
          } catch (e) {
            toast.error(e instanceof Error ? e.message : "Delete failed");
          } finally {
            setDeleteTarget(null);
          }
        }}
      />
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add admin-ui/src/components/forms/WorkoutForm.tsx admin-ui/src/pages/WorkoutsPage.tsx
git commit -m "feat(admin-ui): workouts CRUD page with completed filter + child-count delete message"
```

---

**End of Chunk 6.** Three canonical resource pages are live (Users, Measurements, Workouts) along with their hand-written forms. These three cover every phase 2 pattern: simple flat rows (Measurements), JSON-array column (Users), and nested children + status filter (Workouts). Chunk 7 applies the same template to the remaining four resources with deltas only.

---

## Chunk 7: Remaining Pages, Sidebar Wiring, and Final Smoke Test

This chunk ties up all remaining frontend work and produces the manual smoke-test checklist that gates the merge back to main.

### Task 28: Delta-only pages — PRs, Exercises, AI Usage, Admin Users

The remaining four pages follow the MeasurementsPage structure 1:1. Each one:
- has a form file under `components/forms/<X>Form.tsx`
- has a page file under `pages/<X>Page.tsx`
- starts by copy-pasting `MeasurementsPage.tsx` + `MeasurementForm.tsx`
- then applies the deltas listed below

Each resource is its own commit.

#### 28.1: PRs

**Files:**
- Create: `admin-ui/src/components/forms/PRForm.tsx`
- Create: `admin-ui/src/pages/PRsPage.tsx`

- [ ] **Step 1: Copy MeasurementForm.tsx → PRForm.tsx, apply deltas**

Deltas to `PRForm.tsx`:
- Import `PersonalRecordAdminResponse` instead of `MeasurementAdminResponse`.
- Form schema:
  ```typescript
  const schema = z.object({
    user_id: z.coerce.number().int().positive(),
    exercise_id: z.coerce.number().int().positive(),
    pr_type: z.string().min(1).max(20),
    value: z.coerce.number(),
    session_id: z.coerce.number().int().positive().nullable().optional(),
    achieved_at: z.string().min(1),  // datetime-local
  });
  ```
- Form fields (replace the Measurement ones): `user_id`, `exercise_id`, `pr_type` (placeholder "max_weight, max_reps, max_distance"), `value`, `session_id` (optional), `achieved_at` (`type="datetime-local"`).
- Rename submit button label and default values accordingly.

- [ ] **Step 2: Copy MeasurementsPage.tsx → PRsPage.tsx, apply deltas**

Deltas to `PRsPage.tsx`:
- `const RESOURCE = "prs";`
- Types: `PersonalRecordAdminResponse/Create/Update` from `api.types`.
- Columns: `id`, `user_id`, `exercise_id`, `pr_type`, `value` (right-aligned), `achieved_at` (rendered as first 16 chars), actions.
- Title: "Personal Records".
- Toast messages: "PR created", "PR updated", "PR deleted".

- [ ] **Step 3: Commit**

```bash
git add admin-ui/src/components/forms/PRForm.tsx admin-ui/src/pages/PRsPage.tsx
git commit -m "feat(admin-ui): personal records CRUD page"
```

#### 28.2: Exercises

**Files:**
- Create: `admin-ui/src/components/forms/ExerciseForm.tsx`
- Create: `admin-ui/src/pages/ExercisesPage.tsx`

- [ ] **Step 1: Create `ExerciseForm.tsx`**

Schema:
```typescript
const schema = z.object({
  name: z.string().min(1).max(200),
  muscle_group: z.string().min(1).max(50),
  equipment: z.string().min(1).max(50),
  category: z.string().min(1).max(50),
  difficulty: z.string().min(1).max(20),
  source_plugin: z.string().nullable().optional(),
});
```

Fields: `name`, `muscle_group` (placeholder "chest, back, legs, ..."), `equipment`, `category` (placeholder "compound, isolation"), `difficulty` (placeholder "beginner, intermediate, advanced"), `source_plugin` (optional).

Note: `metadata_json` is NOT in the form — editable only via the JSON tab escape hatch.

- [ ] **Step 2: Create `ExercisesPage.tsx`**

Deltas from Measurements template:
- `const RESOURCE = "exercises";`
- Columns: `id`, `name`, `muscle_group`, `equipment`, `category`, `difficulty`, actions.
- Search placeholder: `exercises`.
- Title: "Exercises".

- [ ] **Step 3: Commit**

```bash
git add admin-ui/src/components/forms/ExerciseForm.tsx admin-ui/src/pages/ExercisesPage.tsx
git commit -m "feat(admin-ui): exercises CRUD page"
```

#### 28.3: AI Usage

**Files:**
- Create: `admin-ui/src/components/forms/AIUsageForm.tsx`
- Create: `admin-ui/src/pages/AIUsagePage.tsx`

Resource path is `"ai/usage"` (two URL segments), not just `"ai_usage"`.

- [ ] **Step 1: Create `AIUsageForm.tsx`**

Schema:
```typescript
const schema = z.object({
  user_id: z.coerce.number().int().positive(),
  month: z.string().regex(/^\d{4}-\d{2}$/, "Use YYYY-MM format"),
  total_input_tokens: z.coerce.number().int().min(0).default(0),
  total_output_tokens: z.coerce.number().int().min(0).default(0),
  total_cache_read_tokens: z.coerce.number().int().min(0).default(0),
  total_cache_creation_tokens: z.coerce.number().int().min(0).default(0),
  estimated_cost: z.coerce.number().min(0).default(0),
  call_count: z.coerce.number().int().min(0).default(0),
});
```

All fields are plain number inputs. The "month" field should be a text input with placeholder "2026-04".

- [ ] **Step 2: Create `AIUsagePage.tsx`**

Deltas:
- `const RESOURCE = "ai/usage";` — note the slash; it flows through `useList` → `api.get("/api/admin/ai/usage")`.
- Columns: `user_id`, `month`, `call_count`, `total_input_tokens`, `total_output_tokens`, `estimated_cost` (right-aligned, four-decimal: `$${row.estimated_cost.toFixed(4)}`), actions.
- The two cache-token fields (`total_cache_read_tokens`, `total_cache_creation_tokens`) are intentionally **form-only** — they're editable in the form and visible via the JSON tab, but the list table stays narrow by omitting them. Admins who need to see them can click into a row.
- Title: "AI Usage".
- Toolbar: just the "New usage row" button — no extra filters (month filter is search-like; skip for phase 2).

- [ ] **Step 3: Commit**

```bash
git add admin-ui/src/components/forms/AIUsageForm.tsx admin-ui/src/pages/AIUsagePage.tsx
git commit -m "feat(admin-ui): AI usage CRUD page"
```

#### 28.4: Admin Users

**Files:**
- Create: `admin-ui/src/components/forms/AdminUserForm.tsx`
- Create: `admin-ui/src/pages/AdminUsersPage.tsx`

**Critical:** password field is write-only (never in the response type) and is required on create, optional on edit.

- [ ] **Step 1: Create `AdminUserForm.tsx`**

Schema has a conditional for password:
```typescript
const createSchema = z.object({
  username: z.string().min(1).max(64),
  password: z.string().min(8).max(256),
  is_active: z.boolean().default(true),
});

const updateSchema = z.object({
  username: z.string().min(1).max(64),
  password: z.string().min(8).max(256).optional().or(z.literal("")),
  is_active: z.boolean().default(true),
});
```

Two mode props:
```typescript
type Props = {
  mode: "create" | "edit";
  defaultValues?: AdminAdminUserResponse | null;
  onSubmit: (values: AdminUserFormValues) => void | Promise<void>;
  isSaving?: boolean;
};
```

Render the password field with placeholder "Leave blank to keep existing" when `mode === "edit"`, otherwise placeholder "At least 8 characters".

- [ ] **Step 2: Create `AdminUsersPage.tsx`**

Deltas:
- `const RESOURCE = "admin-users";`
- Columns: `id`, `username`, `is_active` (`<Badge variant={u.is_active ? "default" : "secondary"}>`), `created_at`, `last_login_at`, actions.
- Title: "Admin Users".
- Pass `mode="create"` / `mode="edit"` to `AdminUserForm`.
- On delete-yourself error, the backend returns 400 with a message — let the toast surface it.
- **Omit password from the JSON tab save:** in `onJsonSave`, strip any `password` key before sending to avoid clobbering the hash with an editable-in-JSON plain string.

- [ ] **Step 3: Commit**

```bash
git add admin-ui/src/components/forms/AdminUserForm.tsx admin-ui/src/pages/AdminUsersPage.tsx
git commit -m "feat(admin-ui): admin users CRUD page (password write-only)"
```

---

### Task 29: Enable sidebar items + add routes

**Files:**
- Modify: `admin-ui/src/components/AppSidebar.tsx`
- Modify: `admin-ui/src/App.tsx`

- [ ] **Step 1: Enable phase 2 sidebar items**

Edit `admin-ui/src/components/AppSidebar.tsx` — remove `disabled: true` from these six entries:
- `Users`
- `Workouts`
- `Measurements`
- `Personal Records`
- `Exercises`
- `Usage` (under AI)

Leave disabled:
- `Plans` (phase 3)
- All other AI items (`Config`, `Prompts`, `Playground`) — phase 4
- All Operations items — phase 5

Also add a new "Admin Users" entry as its own trailing ungrouped section at the bottom of the sidebar (phase 1 has no footer section; add a new `groups[]` entry with an empty `label` after Operations). Entry:
```typescript
{
  label: "",  // ungrouped — no section header
  items: [
    { label: "Admin Users", to: "/admin-users", icon: ShieldUser },
  ],
}
```
Import `ShieldUser` from `lucide-react`; if that specific icon isn't exported in the installed version, fall back to `UserCog`.

- [ ] **Step 2: Add routes to `App.tsx`**

Add these routes inside the `<Route path="/" element={<AuthGate>...</AuthGate>}>` block, after the existing `ChangePasswordPage` / `SessionsPage` routes:

```typescript
<Route path="users" element={<UsersPage />} />
<Route path="workouts" element={<WorkoutsPage />} />
<Route path="measurements" element={<MeasurementsPage />} />
<Route path="prs" element={<PRsPage />} />
<Route path="exercises" element={<ExercisesPage />} />
<Route path="ai/usage" element={<AIUsagePage />} />
<Route path="admin-users" element={<AdminUsersPage />} />
```

Add the matching imports at the top of `App.tsx`:
```typescript
import { UsersPage } from "@/pages/UsersPage";
import { WorkoutsPage } from "@/pages/WorkoutsPage";
import { MeasurementsPage } from "@/pages/MeasurementsPage";
import { PRsPage } from "@/pages/PRsPage";
import { ExercisesPage } from "@/pages/ExercisesPage";
import { AIUsagePage } from "@/pages/AIUsagePage";
import { AdminUsersPage } from "@/pages/AdminUsersPage";
```

- [ ] **Step 3: Build**

```bash
cd admin-ui && npm run build
```

Expected: TypeScript compiles, Vite bundle output goes to `../src/flexloop/static/admin/`. No errors.

- [ ] **Step 4: Commit**

```bash
git add admin-ui/src/components/AppSidebar.tsx admin-ui/src/App.tsx
git commit -m "feat(admin-ui): enable phase 2 sidebar items + add resource routes"
```

---

### Task 30: End-to-end build + first-boot sanity check

- [ ] **Step 1: Full build from server root**

From the worktree root:
```bash
uv run pytest -v
cd admin-ui && npm run build && cd ..
```

Expected: all backend tests green, Vite build succeeds, `src/flexloop/static/admin/` has a fresh `index.html` + assets.

- [ ] **Step 2: Boot the server and smoke every page**

```bash
uv run uvicorn flexloop.main:app --port 8000
```

In a browser:
1. Go to `http://127.0.0.1:8000/admin` — should redirect to login.
2. Log in with your phase 1 admin credentials.
3. Click each of the 7 new sidebar items. Every page should render without a blank screen.
4. On the Users page, click "New user", fill in the form, save. The row should appear in the table.
5. On the same row, click "Edit", tweak a field, save.
6. Click "Edit" again, switch to the JSON tab. The raw row shows. Change `goals` to `"updated via JSON"` and save. Refresh — the change persists.
7. Click "Delete" on the row you just edited. Confirm. Row disappears.
8. Check the browser devtools Network tab: every `/api/admin/*` request includes the `flexloop_admin_session` cookie and mutations include an `Origin` header.

Stop the server after smoke-checking.

- [ ] **Step 3: Commit the milestone**

```bash
git commit --allow-empty -m "milestone: phase 2 end-to-end smoke clean"
```

---

---

### Task 31: Write the phase 2 smoke-test checklist document

**Files:**
- Create: `docs/admin-dashboard-phase2-smoke-test.md`

This file mirrors phase 1's `docs/admin-dashboard-phase1-smoke-test.md` — a manual checklist run before merging back to main and after each deploy. It's the trust signal the user relies on to ship.

- [ ] **Step 1: Create the checklist file**

Create `docs/admin-dashboard-phase2-smoke-test.md` with the following content:

```markdown
# Admin Dashboard — Phase 2 Smoke Test

Run before merging `feat/admin-dashboard-phase2` to main, and after deploying to the VPS.

**Prerequisites**
- Server running: `uv run uvicorn flexloop.main:app --port 8000`
- Admin UI built: `cd admin-ui && npm run build`
- You are logged in to `/admin` as a phase 1 admin user.

## Backend (automated)
- [ ] `uv run pytest -v` — all passing (phase 1 tests + ~40 new phase 2 tests)
- [ ] `curl -s http://127.0.0.1:8000/openapi.json | jq '.paths | keys | map(select(startswith("/api/admin/")))' | wc -l` returns 21 (phase 1 = 7 + phase 2 = 14)

## Authentication
- [ ] Visit `/admin/users` while logged out → redirected to `/admin/login`
- [ ] Log in, visit `/admin/users` → page loads

## Users page
- [ ] Table loads with pagination controls (if ≥1 user exists)
- [ ] Click a sortable column header (Name, ID, Age) — rows reorder and arrow icon flips
- [ ] Click the header again — direction flips to descending
- [ ] Click a third time — sort clears, default order restored
- [ ] Type in the search box — table filters after keystrokes; page resets to 1
- [ ] Click "New user", submit a valid form → row appears in list, toast shows "User created"
- [ ] Click "Edit" on the new row → sheet opens with pre-filled values
- [ ] Change a field, save → toast shows "User updated", row reflects change
- [ ] Click "Edit" again, switch to "JSON" tab → raw row visible; `goals` is editable; save → toast shows "User updated via JSON"
- [ ] Click "Delete" → confirm dialog appears with "This cannot be undone."
- [ ] Confirm delete → toast "User deleted", row disappears

## Workouts page
- [ ] Table loads
- [ ] Completed filter: switch between All / Completed / In progress → counts update
- [ ] Create a new workout with no completed_at → appears as "In progress" badge
- [ ] Edit the same row, set completed_at in the past → badge flips to "Completed"
- [ ] Sets column shows 0 for a session with no sets
- [ ] Delete a workout with ≥1 set → delete dialog shows the child-count message

## Measurements page
- [ ] Create a weight measurement → appears
- [ ] Filter by type=weight via query param (`?filter[type]=weight`) — direct URL visit → only weight rows
- [ ] Edit → save, delete → remove

## Personal Records page
- [ ] Create a PR with pr_type=max_weight → appears
- [ ] Edit the value → persists
- [ ] Delete → gone

## Exercises page
- [ ] List loads with existing plugin-seeded exercises
- [ ] Search for "squat" → filters to squat variants
- [ ] Create a new exercise → appears
- [ ] Edit the `metadata_json` via the JSON tab → persists

## AI Usage page
- [ ] List loads (may be empty on a fresh install)
- [ ] Create a row for month=2026-04 with some tokens → appears
- [ ] Edit and save → persists
- [ ] Delete → gone

## Admin Users page
- [ ] List shows at least the current admin
- [ ] Create another admin with username="test_admin2", password="testpass8" → appears
- [ ] Log out, log in as `test_admin2` → succeeds, `last_login_at` visible on that row
- [ ] Log back in as original admin
- [ ] Edit test_admin2, set is_active=false → row reflects inactive badge
- [ ] Try to delete the currently-logged-in admin → 400 error surfaces as toast, row remains
- [ ] Delete `test_admin2` → succeeds

## Cross-cutting
- [ ] All write requests in devtools → Network include an `Origin` header and the session cookie
- [ ] Reloading any page keeps state (React Router doesn't break on refresh)
- [ ] Sidebar items for Plans, AI Config/Prompts/Playground, Operations remain disabled (grayed out / non-clickable) — phase 3+ placeholders
- [ ] No errors in browser console on any page
- [ ] `/api/admin/health` still works and the Dashboard landing page from phase 1 still loads

## Result
- [ ] **PASS** — ready to merge to main
- [ ] **FAIL** — fix issues listed below and re-run the whole checklist
```

- [ ] **Step 2: Commit**

```bash
git add docs/admin-dashboard-phase2-smoke-test.md
git commit -m "docs: phase 2 smoke-test checklist"
```

- [ ] **Step 3: Actually run the checklist**

Work through every checkbox. Record the pass/fail at the bottom of the file before committing the updated version.

- [ ] **Step 4: Commit the result**

If everything passes:
```bash
git add docs/admin-dashboard-phase2-smoke-test.md
git commit -m "docs: phase 2 smoke test — all checks passing"
```

If anything fails, fix it (reopen the relevant task chunks), re-run the whole checklist, and only then commit the green result. Do not skip failing items.

---

### Task 32: Merge `feat/admin-dashboard-phase2` back to main

- [ ] **Step 1: Verify branch is clean**

```bash
git status
git log --oneline main..HEAD | wc -l
```

Expected: working tree clean, ~30+ commits on the feature branch.

- [ ] **Step 2: Fast-forward merge into main (from the flexloop-server root, not the worktree)**

```bash
cd /Users/flyingchickens/Projects/FlexLoop/flexloop-server
git fetch
git checkout main
git merge --ff-only feat/admin-dashboard-phase2
```

Expected: fast-forward merge succeeds.

- [ ] **Step 3: Run the full test suite one more time on main**

```bash
uv run pytest -v
```

Expected: all green.

- [ ] **Step 4: Push main**

```bash
git push origin main
```

- [ ] **Step 5: Bump the parent FlexLoop submodule pointer**

```bash
cd /Users/flyingchickens/Projects/FlexLoop
git add flexloop-server
git commit -m "chore: bump flexloop-server to admin dashboard phase 2"
```

> Per memory: the parent `FlexLoop` repo has no remote, so no push is needed after the submodule bump.

- [ ] **Step 6: Clean up the worktree and feature branch**

```bash
cd /Users/flyingchickens/Projects/FlexLoop/flexloop-server
git worktree remove /Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase2
git branch -d feat/admin-dashboard-phase2
```

- [ ] **Step 7: Update the auto-memory status file**

Edit `/Users/flyingchickens/.claude/projects/-Users-flyingchickens-Projects-FlexLoop/memory/project_admin_dashboard_status.md`:
- Mark phase 2 as COMPLETE with today's date.
- Move phase 3 (Plans editor) into the "next up" position.

---

**End of Chunk 7.** Phase 2 is shipped and merged. The admin dashboard now has full CRUD for every non-plan resource. Next up: phase 3 (Plans editor — the one resource that breaks the generic CRUD pattern).

---

## Summary

**Backend deliverables:**
- `flexloop.admin.crud` module — pagination, sort, filter helpers (Chunk 1)
- `flexloop.admin.schemas` package — 8 schema files including `common.py` (Chunks 1-4)
- 7 admin routers — `users`, `workouts`, `measurements`, `prs`, `exercises`, `ai/usage`, `admin-users` (Chunks 2-4)
- ~40 integration tests covering auth, pagination, filtering, write operations, validation, 404s, password re-hashing, self-delete guard

**Frontend deliverables:**
- `openapi-typescript` codegen wired up; generated types at `admin-ui/src/lib/api.types.ts`
- 9 new shadcn components installed
- `lib/crud.ts` + `hooks/useCrud.ts` — generic CRUD hooks over TanStack Query
- Shared `<DataTable>`, `<DeleteDialog>`, `<JsonEditor>`, `<EditSheet>` components
- 7 resource pages + 7 hand-written forms
- Sidebar and routing updated to enable the 7 new pages

**Docs:** `docs/admin-dashboard-phase2-smoke-test.md` — manual checklist gated behind the merge.

**End state:** operator can browse and edit every non-plan row in the FlexLoop database without touching SQL or the iOS client. Phase 3 (Plans editor — drag-and-drop day/exercise reordering, nested sets_json editing) is the next phase and will need its own plan file.
