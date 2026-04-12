# Admin Dashboard — Phase 4a (Config editor + audit log foundation) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the admin Config editor — runtime-mutable AI provider/model/key/etc. configuration stored in the `app_settings` table, with a sectioned form UI, masked API key, "Test connection" button, and audit log entries for every change. Also lands the foundation that later sub-plans (4b prompt editor, 4c playground) build on: a reusable audit log helper, runtime DB-backed settings with hot reload, and the CSRF middleware swap from a hardcoded allowed-origins list to the `app_settings.admin_allowed_origins` column.

**Architecture:**
1. **Data layer:** `app_settings` table already exists from phase 1 migration. Plan 4a adds a new Alembic migration that seeds a single row (id=1) from current `.env` values so existing deployments don't lose their config. Tests seed the row manually in fixtures.
2. **Runtime config:** `flexloop.config.Settings` stays as a pydantic-settings singleton with `.env` defaults. A new `refresh_settings_from_db(db)` async function mutates the singleton's runtime-mutable fields from the `app_settings` row. It's called from the FastAPI lifespan (after `init_db`) and from the `PUT /api/admin/config` handler. This gives us hot-reload without restart.
3. **CSRF swap:** The hardcoded `_PHASE1_ALLOWED_ORIGINS` list in `main.py` is replaced with `lambda: settings.admin_allowed_origins` — same callable shape, new source. The seed migration sets the initial column value to the old hardcoded list so behavior is unchanged on existing deployments.
4. **Audit log:** A new `flexloop.admin.audit.write_audit_log(...)` helper writes to the existing `admin_audit_log` table. The config PUT handler calls it with `action="config_update"`, `target_type="app_settings"`, and before/after snapshots (with the API key masked in both).
5. **Admin router:** `flexloop.admin.routers.config` exposes three endpoints: `GET /api/admin/config` (masked read), `PUT /api/admin/config` (validated update + audit log + settings refresh), `POST /api/admin/config/test-connection` (runs a tiny round-trip via the AI factory, returns latency + response text).
6. **Frontend:** Single-page config editor with sectioned form ("AI Provider", "Generation Defaults", "Review Schedule", "Allowed Origins"), masked API key field with reveal/clear affordances, "Test connection" button at the top, "Save" at the bottom. Sidebar Config item is enabled.

**Tech Stack (new to phase 4a):** No new backend dependencies. No new frontend dependencies (reuses existing shadcn form primitives).

**Spec reference:** `docs/superpowers/specs/2026-04-06-admin-dashboard-design.md`. Read §10.1 (Config editor — this is the authoritative spec), §5.5 (Admin allowed origins — CSRF context), §14 phase 4 bullet, §17 acceptance criterion 3.

**Phases 1-3 already delivered** (do not redo or rework): admin auth + CSRF middleware, 7 resource CRUD pages, Plans editor with per-day accordion. The `OriginCheckMiddleware` in `src/flexloop/admin/csrf.py` already takes a callable `allowed_origins_getter` — plan 4a only swaps the lambda, not the middleware itself. The `app_settings` and `admin_audit_log` tables exist in `src/flexloop/models/` and phase 1's migration created them. No audit log helper exists yet — plan 4a writes it.

**Phases 4b (Prompt editor), 4c (AI Playground), and 4d (AI Usage dashboard) are out of scope.** This plan delivers ONLY the config editor + audit log + runtime settings foundation. The "Test connection" button is in scope because it's part of the config editor spec, not because it's the same as the playground.

---

## Decisions locked in for this phase

These choices are fixed before implementation starts. Do not re-litigate them mid-execution — if a decision turns out to be wrong, stop and ask the user.

1. **`Settings` refactor approach: mutate-the-singleton, not rebuild.** `flexloop.config.settings` stays the same singleton object. `refresh_settings_from_db(db)` reads the `app_settings` row and assigns onto the existing instance (`settings.ai_provider = row.ai_provider`, etc.). No existing call site (`from flexloop.config import settings`) needs to change. The alternative of rebuilding the singleton would require every importing module to re-import, which is infeasible.

2. **`.env` defaults remain in `Settings.__fields__`.** `Settings` still reads `.env` on class instantiation. The DB row overrides those values at runtime, not at construction. Rationale: pydantic-settings does its own env validation; stripping that out is pointless given we still need defaults if the DB row is missing (cold start, migration failure, etc.).

3. **Alembic migration seeds `app_settings` row idempotently.** New migration file `alembic/versions/<new>_seed_app_settings.py` inserts a single row with id=1 ONLY if the row doesn't already exist (`SELECT COUNT(*) FROM app_settings`). Values come from `os.getenv(...)` at migration time — matches the spec's "seed from current .env values" guarantee. The `admin_allowed_origins` column is seeded with the old hardcoded list `["http://localhost:5173", "http://localhost:8000"]` so the CSRF behavior is unchanged on existing deployments. No down-migration data revert (the table itself is dropped by phase 1's down migration).

4. **Tests bypass the migration.** `tests/conftest.py` uses an in-memory SQLite and calls `Base.metadata.create_all` directly; it does NOT run Alembic. Config-related tests seed an `AppSettings` row manually via a helper (`_seed_default_app_settings`) at the top of each test that needs one. This mirrors the phase 2/3 convention of per-test data setup.

5. **API key masking format: `"•" * max(0, len(key) - 3) + key[-3:]`** (or `""` if key is empty). The last 3 characters are preserved so the admin can eyeball which key is set without exposing the full value. `GET /api/admin/config` always returns this masked form. `PUT /api/admin/config` accepts plaintext; if the payload's `ai_api_key` field is the exact masked value returned by GET, the backend treats it as "no change" and retains the existing key. Any other non-empty value overwrites the DB key.

6. **"Reveal" toggle is client-side only.** The frontend's reveal toggle flips the input's `type` from `password` to `text` and shows whatever the user has typed. It does NOT fetch the cleartext from the backend. If the user reloads the page, the cleartext is gone and the mask reappears. This matches the spec's "After save, the cleartext key is never returned to the frontend again" invariant without needing a separate reveal endpoint.

7. **"Rotate" button is also client-side only.** It clears the current API key input so the user can paste a new value. No separate backend endpoint.

8. **"Test connection" endpoint shape:**
   ```
   POST /api/admin/config/test-connection
   Body (all optional — uses saved config as defaults):
     {provider?, model?, api_key?, base_url?, temperature?, max_tokens?}
   Response (always 200):
     {status: "ok" | "error", latency_ms: int, response_text: str | null, error: str | null}
   ```
   Rationale: override fields let the admin test a new config BEFORE saving. Omitted fields fall back to the current saved values. Always returns 200 — connection failures are data, not HTTP errors, because the UI shows them inline in the test result card, not as a toast.

9. **Test connection system/user prompt and max_tokens:** hardcoded constants. `system_prompt = "You are a helpful assistant."`, `user_prompt = "Say hello in one word."`, `max_tokens=10`, `temperature=0.0`, 30-second `asyncio.wait_for` timeout. If the timeout fires, return `{status: "error", latency_ms: 30000, response_text: null, error: "timeout after 30s"}`.

10. **Audit log entries for config updates:**
    ```
    action="config_update"
    target_type="app_settings"
    target_id="1"
    before_json={<masked config dict>}
    after_json={<masked config dict>}
    admin_user_id=<from request>
    ```
    API keys are masked in BOTH `before_json` and `after_json` — an audit log that preserves plaintext keys is itself a security hole. Only fields that actually changed are included in the before/after dicts (omitted fields implicitly stayed the same). If nothing changed, no audit log entry is written.

11. **`flexloop.admin.audit.write_audit_log` is the ONLY audit-writing entry point** from now on. Future resource changes (plans, users, etc.) that need auditing go through this helper. Signature:
    ```python
    async def write_audit_log(
        db: AsyncSession,
        *,
        admin_user_id: int,
        action: str,
        target_type: str,
        target_id: str | None = None,
        before: dict | None = None,
        after: dict | None = None,
    ) -> AdminAuditLog:
        ...
    ```
    Returns the inserted row. Does NOT commit — the caller's transaction controls commit boundaries so audit + write are atomic.

12. **Frontend: one page, one `<form>`, no tabs.** The spec mentions "sectioned by logical group" but that's purely visual via heading + divider. No tab component. The JSON escape hatch from phase 2 is NOT added to the config page (the sectioned form is the only edit path; if you really need raw JSON, go edit the DB). The `admin_allowed_origins` field gets its own "Allowed Origins (comma-separated)" input — the UI splits/joins on `, ` around the JSON list.

13. **No smoke test for every existing admin resource.** Plan 4a only needs to verify the config editor and that the CSRF middleware still accepts writes after the allowed-origins swap. Regression tests for plans/workouts/etc. are already in place.

14. **Worktree + feature branch (per branch-strategy memory):**
    - Worktree path: `/Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase4a`
    - Branch: `feat/admin-dashboard-phase4a-config`
    - Merge strategy: fast-forward into `main`, delete branch + worktree, bump parent submodule, update memory.

---

## File Structure

All paths relative to `flexloop-server/` unless stated otherwise.

**Backend — new:**
```
src/flexloop/admin/
├── audit.py                      NEW — write_audit_log helper
└── routers/
    └── config.py                 NEW — GET/PUT/test-connection endpoints
alembic/versions/
└── <new>_seed_app_settings.py    NEW — idempotent row seed + allowed-origins seed
```

**Backend — modified:**
```
src/flexloop/
├── config.py                     add `admin_allowed_origins` field + runtime load function
├── db/engine.py                  call refresh_settings_from_db after init_db
└── main.py                       import admin_config_router + include_router;
                                  swap _PHASE1_ALLOWED_ORIGINS lambda to
                                  settings.admin_allowed_origins
```

**Backend — tests:**
```
tests/
├── test_admin_audit.py           NEW — write_audit_log helper unit tests
├── test_admin_config.py          NEW — config router integration tests
│                                 (list/update/test-connection, auth, masking, audit)
└── test_runtime_settings.py      NEW — refresh_settings_from_db mutation tests
```

**Frontend — new:**
```
admin-ui/src/
├── pages/ConfigPage.tsx          NEW — sectioned config form + test connection
└── components/forms/ConfigForm.tsx   NEW — rhf+zod form for AppSettings fields
```

**Frontend — modified:**
```
admin-ui/src/
├── App.tsx                       add /ai/config route
├── components/AppSidebar.tsx     remove `disabled: true` from Config item
└── lib/api.types.ts              regenerated from updated OpenAPI schema
```

**Docs:**
```
docs/admin-dashboard-phase4a-smoke-test.md   NEW — manual + automated smoke checklist
```

---

## Execution setup

Run these commands once before starting Chunk 1. All subsequent file paths are relative to the worktree.

```bash
cd /Users/flyingchickens/Projects/FlexLoop/flexloop-server
git worktree add /Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase4a -b feat/admin-dashboard-phase4a-config
cd /Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase4a
uv sync --extra dev
uv pip install -e .
cd admin-ui && npm install --legacy-peer-deps && cd ..
```

Verify baseline:

```bash
uv run pytest -q
```

Expected: 298 tests passing (matches phase 3 state). If red, stop and ask.

```bash
cd admin-ui && npx tsc --noEmit && npm run build && cd ..
```

Expected: both green.

---

## Chunk 1: Backend — audit log helper + seed migration

This chunk ships the reusable audit helper and the Alembic migration that seeds the `app_settings` row. No routes change yet — the audit helper is unit-tested, the migration is exercised by a dedicated test that applies it to a temp file DB.

### Task 1: Write failing tests for `write_audit_log`

**Files:**
- Create: `tests/test_admin_audit.py`

- [ ] **Step 1: Write the test file**

```python
"""Unit tests for flexloop.admin.audit.write_audit_log."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.audit import write_audit_log
from flexloop.admin.auth import hash_password
from flexloop.models.admin_audit_log import AdminAuditLog
from flexloop.models.admin_user import AdminUser


async def _make_admin(db: AsyncSession, username: str = "auditor") -> AdminUser:
    admin = AdminUser(username=username, password_hash=hash_password("password123"))
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    return admin


class TestWriteAuditLog:
    async def test_inserts_a_row(self, db_session: AsyncSession) -> None:
        admin = await _make_admin(db_session)
        entry = await write_audit_log(
            db_session,
            admin_user_id=admin.id,
            action="config_update",
            target_type="app_settings",
            target_id="1",
            before={"ai_provider": "openai"},
            after={"ai_provider": "anthropic"},
        )
        await db_session.commit()
        assert entry.id is not None
        fetched = (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.id == entry.id)
            )
        ).scalar_one()
        assert fetched.admin_user_id == admin.id
        assert fetched.action == "config_update"
        assert fetched.target_type == "app_settings"
        assert fetched.target_id == "1"
        assert fetched.before_json == {"ai_provider": "openai"}
        assert fetched.after_json == {"ai_provider": "anthropic"}
        assert fetched.timestamp is not None

    async def test_accepts_nullable_fields(self, db_session: AsyncSession) -> None:
        admin = await _make_admin(db_session)
        entry = await write_audit_log(
            db_session,
            admin_user_id=admin.id,
            action="plan_delete",
            target_type="plan",
            target_id=None,
            before=None,
            after=None,
        )
        await db_session.commit()
        assert entry.target_id is None
        assert entry.before_json is None
        assert entry.after_json is None

    async def test_does_not_commit_caller_transaction(
        self, db_session: AsyncSession
    ) -> None:
        """The helper must not auto-commit — the caller's transaction owns
        commit boundaries so the audit row + the audited write land atomically.
        """
        admin = await _make_admin(db_session)
        await write_audit_log(
            db_session,
            admin_user_id=admin.id,
            action="test",
            target_type="test",
        )
        # Rollback instead of commit — the audit row should NOT appear.
        await db_session.rollback()
        count = (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "test")
            )
        ).all()
        assert len(count) == 0
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
uv run pytest tests/test_admin_audit.py -v
```

Expected: all 3 tests fail with `ModuleNotFoundError: flexloop.admin.audit`.

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_admin_audit.py
git commit -m "test(admin): failing tests for write_audit_log helper"
```

---

### Task 2: Implement `flexloop.admin.audit.write_audit_log`

**Files:**
- Create: `src/flexloop/admin/audit.py`

- [ ] **Step 1: Write the helper**

```python
"""Admin audit log writer.

Every administrative mutation that needs an audit trail goes through
``write_audit_log``. The helper takes the caller's ``AsyncSession`` and
appends a row without committing — the caller controls the transaction
boundary so the audit entry and the audited write commit atomically.

For config updates the typical use is:

    before = _masked_config_dict(current)
    # mutate app_settings row
    after = _masked_config_dict(current)
    await write_audit_log(
        db,
        admin_user_id=admin.id,
        action="config_update",
        target_type="app_settings",
        target_id="1",
        before=before,
        after=after,
    )
    await db.commit()

API keys MUST be masked before being passed into ``before``/``after`` —
see ``flexloop.admin.routers.config`` for the masking helper used there.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.models.admin_audit_log import AdminAuditLog


async def write_audit_log(
    db: AsyncSession,
    *,
    admin_user_id: int,
    action: str,
    target_type: str,
    target_id: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
) -> AdminAuditLog:
    """Append an admin_audit_log row.

    Does NOT commit — the caller owns the transaction. Returns the newly
    added row (with ``id`` populated once the caller flushes/commits).
    """
    entry = AdminAuditLog(
        admin_user_id=admin_user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        before_json=before,
        after_json=after,
    )
    db.add(entry)
    await db.flush()
    return entry
```

- [ ] **Step 2: Run the tests**

```bash
uv run pytest tests/test_admin_audit.py -v
```

Expected: all 3 pass.

- [ ] **Step 3: Full suite sanity check**

```bash
uv run pytest -q
```

Expected: 298 + 3 = 301 tests green.

- [ ] **Step 4: Commit**

```bash
git add src/flexloop/admin/audit.py
git commit -m "feat(admin): add write_audit_log helper"
```

---

### Task 3: Alembic migration — seed `app_settings` row and default allowed-origins

**Files:**
- Create: `alembic/versions/<new_rev>_seed_app_settings.py`

Use `uv run alembic revision -m "seed app_settings"` to generate the revision file. Then replace its contents with the code below.

- [ ] **Step 1: Generate the revision skeleton**

```bash
cd /Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase4a
uv run alembic revision -m "seed app_settings"
```

Expected: a new file is created under `alembic/versions/`. Note its filename (includes a 12-char hex revision id).

- [ ] **Step 2: Replace the file contents**

Open the newly generated file and replace its body with (keeping the generated `revision` and `down_revision` values):

```python
"""seed app_settings

Revision ID: <keep_the_generated_value>
Revises: 1595e0843e18
Create Date: <keep_the_generated_value>
"""
import os
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from dotenv import load_dotenv

# Load the project's .env so os.getenv sees the deployment's current values.
# Same pattern used by the phase 1 migration.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# revision identifiers, used by Alembic.
revision: str = "<keep_the_generated_value>"
down_revision: Union[str, None] = "1595e0843e18"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Default allowed origins — mirrors the old hardcoded list in
# flexloop.main._PHASE1_ALLOWED_ORIGINS so behavior is unchanged on
# existing deployments that haven't set custom origins yet.
_DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:8000",
]


def _parse_int(raw: str | None, default: int) -> int:
    try:
        return int(raw) if raw is not None else default
    except ValueError:
        return default


def _parse_float(raw: str | None, default: float) -> float:
    try:
        return float(raw) if raw is not None else default
    except ValueError:
        return default


def upgrade() -> None:
    """Insert a single app_settings row if one doesn't already exist.

    Values come from the deployment's current environment (loaded from
    .env above). If a field isn't set, the pydantic-settings default is
    used to match what ``flexloop.config.Settings()`` would load.
    """
    conn = op.get_bind()
    existing = conn.execute(
        sa.text("SELECT COUNT(*) FROM app_settings WHERE id = 1")
    ).scalar_one()
    if existing > 0:
        return

    conn.execute(
        sa.text(
            """
            INSERT INTO app_settings (
                id, ai_provider, ai_model, ai_api_key, ai_base_url,
                ai_temperature, ai_max_tokens, ai_review_frequency,
                ai_review_block_weeks, admin_allowed_origins
            ) VALUES (
                1, :ai_provider, :ai_model, :ai_api_key, :ai_base_url,
                :ai_temperature, :ai_max_tokens, :ai_review_frequency,
                :ai_review_block_weeks, :admin_allowed_origins
            )
            """
        ),
        {
            "ai_provider": os.getenv("AI_PROVIDER", "openai"),
            "ai_model": os.getenv("AI_MODEL", "gpt-4o-mini"),
            "ai_api_key": os.getenv("AI_API_KEY", ""),
            "ai_base_url": os.getenv("AI_BASE_URL", ""),
            "ai_temperature": _parse_float(os.getenv("AI_TEMPERATURE"), 0.7),
            "ai_max_tokens": _parse_int(os.getenv("AI_MAX_TOKENS"), 2000),
            "ai_review_frequency": os.getenv("AI_REVIEW_FREQUENCY", "block"),
            "ai_review_block_weeks": _parse_int(
                os.getenv("AI_REVIEW_BLOCK_WEEKS"), 6
            ),
            # SQLAlchemy JSON columns serialize dicts/lists automatically
            # when bound via a parameterized query; wrap in sa.bindparam with
            # a JSON type to be explicit.
            "admin_allowed_origins": sa.func.json(
                sa.literal(_DEFAULT_ALLOWED_ORIGINS)
            ),
        },
    )


def downgrade() -> None:
    """Delete the seeded row. Phase 1's migration drops the table itself."""
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM app_settings WHERE id = 1"))
```

**Warning on the JSON binding:** SQLite's JSON column stores text. The `sa.func.json(sa.literal(...))` pattern may not bind cleanly through `op.get_bind().execute(sa.text(...), {...})`. If you hit a type error at Step 3, replace the `admin_allowed_origins` parameter with a pre-serialized JSON string:

```python
import json as _json
# ...
"admin_allowed_origins": _json.dumps(_DEFAULT_ALLOWED_ORIGINS),
```

And change the column value in the INSERT to `:admin_allowed_origins` as a raw string — SQLite's JSON column accepts text blobs.

- [ ] **Step 3: Apply the migration to a temp DB to verify**

```bash
# Create a scratch DB file
rm -f /tmp/flexloop-phase4a-migration-test.db
DATABASE_URL='sqlite+aiosqlite:////tmp/flexloop-phase4a-migration-test.db' \
  uv run python -c "
import asyncio
from flexloop.db.engine import init_db
asyncio.run(init_db())
"
```

Expected: runs without error. Then verify the row exists:

```bash
sqlite3 /tmp/flexloop-phase4a-migration-test.db "SELECT id, ai_provider, admin_allowed_origins FROM app_settings;"
```

Expected: exactly one row with id=1 and `admin_allowed_origins` containing the JSON list `["http://localhost:5173","http://localhost:8000"]`.

- [ ] **Step 4: Verify idempotency**

Run the migration path a second time via another `init_db()` call — should be a no-op because the existence check returns > 0.

```bash
DATABASE_URL='sqlite+aiosqlite:////tmp/flexloop-phase4a-migration-test.db' \
  uv run python -c "
import asyncio
from flexloop.db.engine import init_db
asyncio.run(init_db())
"
sqlite3 /tmp/flexloop-phase4a-migration-test.db "SELECT COUNT(*) FROM app_settings;"
```

Expected: `1` (not `2`).

- [ ] **Step 5: Clean up and run the full test suite**

```bash
rm -f /tmp/flexloop-phase4a-migration-test.db
uv run pytest -q
```

Expected: 301 tests green. Tests don't run Alembic (they use `Base.metadata.create_all` directly per `conftest.py`), so the new migration doesn't affect them.

- [ ] **Step 6: Commit**

```bash
git add alembic/versions/
git commit -m "feat(db): alembic migration to seed app_settings row from .env"
```

---

**End of Chunk 1.** Audit helper is reusable and tested; seed migration is idempotent and verified on a scratch DB. Next chunk refactors `Settings` to load from DB at runtime.

---

## Chunk 2: Backend — runtime DB-backed settings + CSRF swap

This chunk teaches `flexloop.config.Settings` to accept values from the `app_settings` row at startup and whenever `PUT /api/admin/config` runs. No new HTTP endpoints yet — the load function is unit-tested, the CSRF swap is verified by an existing admin test continuing to pass.

### Task 4: Write failing tests for `refresh_settings_from_db`

**Files:**
- Create: `tests/test_runtime_settings.py`

- [ ] **Step 1: Write the tests**

```python
"""Unit tests for flexloop.config.refresh_settings_from_db."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.config import refresh_settings_from_db, settings
from flexloop.models.app_settings import AppSettings


async def _seed_row(
    db: AsyncSession,
    *,
    ai_provider: str = "openai",
    ai_model: str = "gpt-4o-mini",
    ai_api_key: str = "",
    ai_base_url: str = "",
    ai_temperature: float = 0.7,
    ai_max_tokens: int = 2000,
    ai_review_frequency: str = "block",
    ai_review_block_weeks: int = 6,
    admin_allowed_origins: list | None = None,
) -> AppSettings:
    row = AppSettings(
        id=1,
        ai_provider=ai_provider,
        ai_model=ai_model,
        ai_api_key=ai_api_key,
        ai_base_url=ai_base_url,
        ai_temperature=ai_temperature,
        ai_max_tokens=ai_max_tokens,
        ai_review_frequency=ai_review_frequency,
        ai_review_block_weeks=ai_review_block_weeks,
        admin_allowed_origins=admin_allowed_origins
        if admin_allowed_origins is not None
        else ["http://localhost:5173", "http://localhost:8000"],
    )
    db.add(row)
    await db.commit()
    return row


class TestRefreshSettingsFromDb:
    async def test_noop_when_row_missing(self, db_session: AsyncSession) -> None:
        # Capture current defaults
        snapshot = {
            "ai_provider": settings.ai_provider,
            "ai_model": settings.ai_model,
        }
        await refresh_settings_from_db(db_session)
        assert settings.ai_provider == snapshot["ai_provider"]
        assert settings.ai_model == snapshot["ai_model"]

    async def test_mutates_singleton_from_row(self, db_session: AsyncSession) -> None:
        await _seed_row(
            db_session,
            ai_provider="anthropic",
            ai_model="claude-3-5-sonnet",
            ai_api_key="sk-test-abc",
            ai_temperature=0.3,
            ai_max_tokens=4000,
            admin_allowed_origins=["https://admin.example.com"],
        )
        await refresh_settings_from_db(db_session)
        assert settings.ai_provider == "anthropic"
        assert settings.ai_model == "claude-3-5-sonnet"
        assert settings.ai_api_key == "sk-test-abc"
        assert settings.ai_temperature == 0.3
        assert settings.ai_max_tokens == 4000
        assert settings.admin_allowed_origins == ["https://admin.example.com"]

    async def test_database_url_and_host_port_untouched(
        self, db_session: AsyncSession
    ) -> None:
        """Only runtime-mutable fields are refreshed. database_url/host/port
        stay with their .env values because they're needed before the DB is
        reachable.
        """
        snapshot = {
            "database_url": settings.database_url,
            "host": settings.host,
            "port": settings.port,
        }
        await _seed_row(db_session, ai_provider="anthropic")
        await refresh_settings_from_db(db_session)
        assert settings.database_url == snapshot["database_url"]
        assert settings.host == snapshot["host"]
        assert settings.port == snapshot["port"]
```

- [ ] **Step 2: Run them to confirm failure**

```bash
uv run pytest tests/test_runtime_settings.py -v
```

Expected: fails with `ImportError: cannot import name 'refresh_settings_from_db' from 'flexloop.config'`, or `AttributeError` on `settings.admin_allowed_origins`.

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_runtime_settings.py
git commit -m "test(config): failing tests for refresh_settings_from_db"
```

---

### Task 5: Extend `Settings` with `admin_allowed_origins` and add `refresh_settings_from_db`

**Files:**
- Modify: `src/flexloop/config.py`

- [ ] **Step 1: Rewrite `src/flexloop/config.py`**

```python
"""Runtime configuration.

The ``Settings`` singleton starts life loaded from ``.env`` via pydantic-settings.
After the DB is up, ``refresh_settings_from_db`` mutates the runtime-mutable
fields (everything in ``_DB_BACKED_FIELDS``) from the single ``app_settings``
row. This gives us hot-reload after PUT /api/admin/config without needing to
rebuild the singleton or notify every importing module.

The ``.env``-only fields (``database_url``, ``host``, ``port``) are required
to BOOT the app and must stay readable without the DB, so they live only
in ``.env``.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


# Default allowed origins — mirrors the previously hardcoded list in
# flexloop.main. The seed migration writes this same list into the
# app_settings row on first deployment, so existing behavior is unchanged.
_DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:8000",
]


class Settings(BaseSettings):
    # .env-only (needed to bring the DB up)
    database_url: str = "sqlite+aiosqlite:///./flexloop.db"
    host: str = "0.0.0.0"
    port: int = 8000

    # DB-backed (overridden at runtime by refresh_settings_from_db).
    # Defaults are the pre-phase-4 hardcoded values — used as cold-start
    # fallbacks if the app_settings row is missing (e.g. on a DB created
    # before the seed migration ran).
    ai_provider: str = "openai"
    ai_model: str = "gpt-4o-mini"
    ai_api_key: str = ""
    ai_base_url: str = ""
    ai_temperature: float = 0.7
    ai_max_tokens: int = 2000
    ai_review_frequency: str = "block"
    ai_review_block_weeks: int = 6
    admin_allowed_origins: list[str] = _DEFAULT_ALLOWED_ORIGINS

    model_config = {"env_file": ".env"}


settings = Settings()


# Fields that ``refresh_settings_from_db`` copies off the ``app_settings``
# row. database_url/host/port are deliberately absent.
_DB_BACKED_FIELDS = (
    "ai_provider",
    "ai_model",
    "ai_api_key",
    "ai_base_url",
    "ai_temperature",
    "ai_max_tokens",
    "ai_review_frequency",
    "ai_review_block_weeks",
    "admin_allowed_origins",
)


async def refresh_settings_from_db(db: AsyncSession) -> None:
    """Mutate the module-level ``settings`` singleton from the single
    ``app_settings`` row.

    Called from:
      * ``db.engine.init_db`` at startup, right after create_all + migrations
      * ``admin.routers.config.update_config`` after a successful PUT

    If the row is missing (should only happen on a brand-new dev DB that
    hasn't run the seed migration yet), this is a no-op — the singleton
    retains its .env defaults.
    """
    # Local import avoids circular dep with models -> engine -> config.
    from flexloop.models.app_settings import AppSettings

    result = await db.execute(select(AppSettings).where(AppSettings.id == 1))
    row = result.scalar_one_or_none()
    if row is None:
        return
    for field in _DB_BACKED_FIELDS:
        setattr(settings, field, getattr(row, field))
```

- [ ] **Step 2: Run the tests**

```bash
uv run pytest tests/test_runtime_settings.py -v
```

Expected: all 3 pass.

- [ ] **Step 3: Full suite sanity check**

```bash
uv run pytest -q
```

Expected: 304 tests green. Watch for any pre-existing test that imports `settings.admin_allowed_origins` and expects it not to exist — none should, but if one fails, read the error carefully.

- [ ] **Step 4: Commit**

```bash
git add src/flexloop/config.py
git commit -m "feat(config): add admin_allowed_origins + refresh_settings_from_db"
```

---

### Task 6: Call `refresh_settings_from_db` from `init_db`

**Files:**
- Modify: `src/flexloop/db/engine.py`

- [ ] **Step 1: Update `init_db`**

Open `src/flexloop/db/engine.py`. After the existing `_run_migrations()` call at the end of `init_db`, add a refresh call:

```python
async def init_db():
    from flexloop.db.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Run Alembic migrations to apply any schema updates
    # (handles columns added after initial create_all)
    _run_migrations()

    # Load runtime-mutable settings from the app_settings row so the
    # in-memory singleton matches the DB before any request is served.
    from flexloop.config import refresh_settings_from_db

    async with async_session() as db:
        await refresh_settings_from_db(db)
```

(The `async_session` factory is already defined at module scope — you don't need to import anything else.)

- [ ] **Step 2: Verify the full suite still passes**

```bash
uv run pytest -q
```

Expected: 304 tests green. `init_db` isn't called by tests (conftest uses `create_all` directly), so this change is effectively a no-op for tests.

- [ ] **Step 3: Smoke-check with a temp DB**

```bash
rm -f /tmp/flexloop-phase4a-engine-test.db
DATABASE_URL='sqlite+aiosqlite:////tmp/flexloop-phase4a-engine-test.db' \
  uv run python -c "
import asyncio
from flexloop.db.engine import init_db
from flexloop.config import settings
async def main():
    await init_db()
    print(f'ai_provider={settings.ai_provider}')
    print(f'admin_allowed_origins={settings.admin_allowed_origins}')
asyncio.run(main())
"
rm -f /tmp/flexloop-phase4a-engine-test.db
```

Expected output (or similar, depending on .env):
```
ai_provider=openai
admin_allowed_origins=['http://localhost:5173', 'http://localhost:8000']
```

If `admin_allowed_origins` is empty or missing, the migration didn't run or the refresh didn't read it. Debug before continuing.

- [ ] **Step 4: Commit**

```bash
git add src/flexloop/db/engine.py
git commit -m "feat(db): refresh runtime settings from DB after init_db"
```

---

### Task 7: Swap `_PHASE1_ALLOWED_ORIGINS` to `settings.admin_allowed_origins`

**Files:**
- Modify: `src/flexloop/main.py`

- [ ] **Step 1: Edit the CSRF middleware registration**

Open `src/flexloop/main.py`. Find the block around lines 61-65:

```python
# Add CSRF middleware BEFORE routers so it runs on every /api/admin/* request.
# For Phase 1: fixed allowed-origins list. Phase 4 will replace this callable
# with one that reads from app_settings.admin_allowed_origins.
_PHASE1_ALLOWED_ORIGINS = ["http://localhost:5173", "http://localhost:8000"]
app.add_middleware(
    OriginCheckMiddleware,
    allowed_origins_getter=lambda: _PHASE1_ALLOWED_ORIGINS,
)
```

Replace with:

```python
from flexloop.config import settings as _app_settings

# CSRF middleware BEFORE routers so it runs on every /api/admin/* request.
# The allowed-origins list is hot-reloadable: refresh_settings_from_db
# mutates the ``settings`` singleton on startup and after every config
# update, so this getter reflects the latest DB value without restart.
app.add_middleware(
    OriginCheckMiddleware,
    allowed_origins_getter=lambda: _app_settings.admin_allowed_origins,
)
```

(Place the `from flexloop.config import settings as _app_settings` import at the top of the file with the other flexloop imports. Alias it to `_app_settings` to avoid collision with any local variable named `settings`.)

- [ ] **Step 2: Run the full test suite**

```bash
uv run pytest -q
```

Expected: 304 tests green. Any admin test that exercises a state-changing endpoint runs through the CSRF middleware; if the allowed-origins default (`["http://localhost:5173", "http://localhost:8000"]`) matches the test's `headers={"Origin": "http://localhost:5173"}`, everything stays green.

If tests fail with 403s, investigate: the test sets an `Origin` header that may not match. Don't weaken the middleware — fix the test's Origin or the default list.

- [ ] **Step 3: Commit**

```bash
git add src/flexloop/main.py
git commit -m "feat(admin): swap CSRF middleware to read admin_allowed_origins from settings"
```

---

**End of Chunk 2.** The `Settings` singleton is now DB-backed for runtime-mutable fields, `init_db` refreshes it after migrations, and the CSRF middleware reads allowed origins from the hot-reloadable singleton. Next chunk adds the config router and test-connection endpoint.

---

## Chunk 3: Backend — admin config router (GET, PUT, test-connection)

This chunk ships the three admin config endpoints, wires them into `main.py`, and exercises them with integration tests that mock the AI adapter for the test-connection path.

### Task 8: Write failing tests for `GET /api/admin/config`

**Files:**
- Create: `tests/test_admin_config.py`

- [ ] **Step 1: Create the test file with the GET tests**

```python
"""Integration tests for /api/admin/config."""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import SESSION_COOKIE_NAME, create_session, hash_password
from flexloop.models.admin_audit_log import AdminAuditLog
from flexloop.models.admin_user import AdminUser
from flexloop.models.app_settings import AppSettings


ORIGIN = "http://localhost:5173"


async def _make_admin_and_cookie(db: AsyncSession) -> tuple[AdminUser, dict[str, str]]:
    admin = AdminUser(username="tester", password_hash=hash_password("password123"))
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    token, _ = await create_session(db, admin_user_id=admin.id)
    return admin, {SESSION_COOKIE_NAME: token}


async def _seed_default_app_settings(db: AsyncSession) -> AppSettings:
    row = AppSettings(
        id=1,
        ai_provider="openai",
        ai_model="gpt-4o-mini",
        ai_api_key="sk-test-1234567xyz",
        ai_base_url="",
        ai_temperature=0.7,
        ai_max_tokens=2000,
        ai_review_frequency="block",
        ai_review_block_weeks=6,
        admin_allowed_origins=["http://localhost:5173", "http://localhost:8000"],
    )
    db.add(row)
    await db.commit()
    return row


class TestGetConfig:
    async def test_requires_auth(self, client: AsyncClient) -> None:
        assert (await client.get("/api/admin/config")).status_code == 401

    async def test_404_when_row_missing(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, cookies = await _make_admin_and_cookie(db_session)
        res = await client.get("/api/admin/config", cookies=cookies)
        assert res.status_code == 404

    async def test_returns_masked_api_key(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, cookies = await _make_admin_and_cookie(db_session)
        await _seed_default_app_settings(db_session)
        res = await client.get("/api/admin/config", cookies=cookies)
        assert res.status_code == 200
        body = res.json()
        assert body["ai_provider"] == "openai"
        assert body["ai_model"] == "gpt-4o-mini"
        # Masked: last 3 chars preserved, everything else bullets
        assert body["ai_api_key"].endswith("xyz")
        assert "sk-test" not in body["ai_api_key"]
        assert body["ai_max_tokens"] == 2000
        assert body["admin_allowed_origins"] == [
            "http://localhost:5173",
            "http://localhost:8000",
        ]

    async def test_empty_key_returns_empty_string(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, cookies = await _make_admin_and_cookie(db_session)
        row = await _seed_default_app_settings(db_session)
        row.ai_api_key = ""
        await db_session.commit()
        res = await client.get("/api/admin/config", cookies=cookies)
        assert res.status_code == 200
        assert res.json()["ai_api_key"] == ""
```

- [ ] **Step 2: Run and confirm they fail**

```bash
uv run pytest tests/test_admin_config.py::TestGetConfig -v
```

Expected: all 4 fail (endpoint doesn't exist, 404 for unmounted route).

- [ ] **Step 3: Commit**

```bash
git add tests/test_admin_config.py
git commit -m "test(admin): failing tests for GET /api/admin/config"
```

---

### Task 9: Implement the config router skeleton + `GET /api/admin/config`

**Files:**
- Create: `src/flexloop/admin/routers/config.py`
- Modify: `src/flexloop/main.py`

- [ ] **Step 1: Write the router**

```python
"""Admin config editor endpoints.

Three endpoints:
- GET  /api/admin/config                  masked read
- PUT  /api/admin/config                  validated update + audit log
- POST /api/admin/config/test-connection  tiny round-trip via the AI factory

The GET response always masks ``ai_api_key`` — the cleartext is never
echoed back. PUT accepts plaintext; if the incoming ``ai_api_key`` value
matches the masked form exactly, the server treats it as "no change" and
keeps the existing key.
"""
from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.audit import write_audit_log
from flexloop.admin.auth import require_admin
from flexloop.ai.factory import create_adapter
from flexloop.config import refresh_settings_from_db
from flexloop.db.engine import get_session
from flexloop.models.admin_user import AdminUser
from flexloop.models.app_settings import AppSettings

router = APIRouter(prefix="/api/admin/config", tags=["admin:config"])


# --- Schemas ---------------------------------------------------------------


class AppSettingsResponse(BaseModel):
    """GET /api/admin/config response shape.

    ``ai_api_key`` is always masked — the cleartext value stays on the
    server. A client that wants to "see" the key has to type it in again.
    """
    model_config = ConfigDict(from_attributes=False)

    ai_provider: str
    ai_model: str
    ai_api_key: str  # always masked
    ai_base_url: str
    ai_temperature: float
    ai_max_tokens: int
    ai_review_frequency: str
    ai_review_block_weeks: int
    admin_allowed_origins: list[str]


class AppSettingsUpdate(BaseModel):
    """PUT /api/admin/config payload.

    All fields optional — partial update. ``ai_api_key`` accepts either
    a new plaintext value or the masked form returned by GET (treated as
    "leave unchanged"). Omitted fields are not touched.
    """
    model_config = ConfigDict(extra="forbid")

    ai_provider: str | None = None
    ai_model: str | None = None
    ai_api_key: str | None = None
    ai_base_url: str | None = None
    ai_temperature: float | None = None
    ai_max_tokens: int | None = None
    ai_review_frequency: str | None = None
    ai_review_block_weeks: int | None = None
    admin_allowed_origins: list[str] | None = None


class TestConnectionRequest(BaseModel):
    """POST /api/admin/config/test-connection payload.

    All fields optional — omitted fields fall back to the currently saved
    DB value. This lets the admin test a new config without saving first.
    """
    model_config = ConfigDict(extra="forbid")

    provider: str | None = None
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None


class TestConnectionResponse(BaseModel):
    status: str  # "ok" | "error"
    latency_ms: int
    response_text: str | None
    error: str | None


# --- Helpers ---------------------------------------------------------------


def _mask_key(key: str) -> str:
    """Return a masked form of an API key: bullets + last 3 chars.

    Empty string stays empty. Keys shorter than 3 chars are fully bulleted.
    """
    if not key:
        return ""
    if len(key) <= 3:
        return "\u2022" * len(key)  # • bullet
    return "\u2022" * (len(key) - 3) + key[-3:]


def _masked_dict(row: AppSettings) -> dict:
    """Snapshot the app_settings row as a dict suitable for audit logging.

    API key is masked so the audit log never stores plaintext keys.
    """
    return {
        "ai_provider": row.ai_provider,
        "ai_model": row.ai_model,
        "ai_api_key": _mask_key(row.ai_api_key),
        "ai_base_url": row.ai_base_url,
        "ai_temperature": row.ai_temperature,
        "ai_max_tokens": row.ai_max_tokens,
        "ai_review_frequency": row.ai_review_frequency,
        "ai_review_block_weeks": row.ai_review_block_weeks,
        "admin_allowed_origins": list(row.admin_allowed_origins or []),
    }


async def _load_row(db: AsyncSession) -> AppSettings:
    result = await db.execute(select(AppSettings).where(AppSettings.id == 1))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="app_settings row not found — run the seed migration",
        )
    return row


# --- GET -------------------------------------------------------------------


@router.get("", response_model=AppSettingsResponse)
async def get_config(
    db: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(require_admin),
) -> dict:
    row = await _load_row(db)
    return AppSettingsResponse(
        ai_provider=row.ai_provider,
        ai_model=row.ai_model,
        ai_api_key=_mask_key(row.ai_api_key),
        ai_base_url=row.ai_base_url,
        ai_temperature=row.ai_temperature,
        ai_max_tokens=row.ai_max_tokens,
        ai_review_frequency=row.ai_review_frequency,
        ai_review_block_weeks=row.ai_review_block_weeks,
        admin_allowed_origins=list(row.admin_allowed_origins or []),
    )
```

- [ ] **Step 2: Mount the router in `main.py`**

Open `src/flexloop/main.py`. Add the import:

```python
from flexloop.admin.routers.config import router as admin_config_router
```

Add the `include_router` call next to the other admin routers:

```python
app.include_router(admin_config_router)
```

- [ ] **Step 3: Run the GET tests**

```bash
uv run pytest tests/test_admin_config.py::TestGetConfig -v
```

Expected: all 4 pass.

- [ ] **Step 4: Full suite check**

```bash
uv run pytest -q
```

Expected: 308 tests green.

- [ ] **Step 5: Commit**

```bash
git add src/flexloop/admin/routers/config.py src/flexloop/main.py
git commit -m "feat(admin): GET /api/admin/config with masked API key"
```

---

### Task 10: Failing tests for `PUT /api/admin/config` (with audit log)

**Files:**
- Modify: `tests/test_admin_config.py`

- [ ] **Step 1: Append PUT tests**

```python
class TestUpdateConfig:
    async def test_requires_auth(self, client: AsyncClient) -> None:
        res = await client.put(
            "/api/admin/config",
            json={"ai_provider": "anthropic"},
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 401

    async def test_404_when_row_missing(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, cookies = await _make_admin_and_cookie(db_session)
        res = await client.put(
            "/api/admin/config",
            json={"ai_provider": "anthropic"},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 404

    async def test_updates_fields(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, cookies = await _make_admin_and_cookie(db_session)
        await _seed_default_app_settings(db_session)
        res = await client.put(
            "/api/admin/config",
            json={
                "ai_provider": "anthropic",
                "ai_model": "claude-3-5-sonnet",
                "ai_temperature": 0.3,
            },
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["ai_provider"] == "anthropic"
        assert body["ai_model"] == "claude-3-5-sonnet"
        assert body["ai_temperature"] == 0.3
        # Unchanged fields still present
        assert body["ai_max_tokens"] == 2000

    async def test_updates_api_key_plaintext(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, cookies = await _make_admin_and_cookie(db_session)
        await _seed_default_app_settings(db_session)
        res = await client.put(
            "/api/admin/config",
            json={"ai_api_key": "sk-new-key-9999abc"},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 200
        # Response is masked, not plaintext
        assert res.json()["ai_api_key"].endswith("abc")
        assert "sk-new-key" not in res.json()["ai_api_key"]
        # DB has the plaintext
        row = (
            await db_session.execute(select(AppSettings).where(AppSettings.id == 1))
        ).scalar_one()
        assert row.ai_api_key == "sk-new-key-9999abc"

    async def test_masked_key_input_is_treated_as_no_change(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """If the client PUTs the masked form back (e.g. didn't touch the
        key field), the server must NOT overwrite the stored plaintext
        with the bullets.
        """
        _, cookies = await _make_admin_and_cookie(db_session)
        await _seed_default_app_settings(db_session)
        # Fetch to learn the current masked value
        get_res = await client.get("/api/admin/config", cookies=cookies)
        masked_key = get_res.json()["ai_api_key"]
        # Submit it back unchanged
        res = await client.put(
            "/api/admin/config",
            json={"ai_api_key": masked_key, "ai_provider": "anthropic"},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 200
        # DB still has the original plaintext
        row = (
            await db_session.execute(select(AppSettings).where(AppSettings.id == 1))
        ).scalar_one()
        assert row.ai_api_key == "sk-test-1234567xyz"
        assert row.ai_provider == "anthropic"

    async def test_rejects_unknown_field(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, cookies = await _make_admin_and_cookie(db_session)
        await _seed_default_app_settings(db_session)
        res = await client.put(
            "/api/admin/config",
            json={"totally_wrong_field": "whatever"},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 422

    async def test_writes_audit_log_on_change(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        admin, cookies = await _make_admin_and_cookie(db_session)
        await _seed_default_app_settings(db_session)
        res = await client.put(
            "/api/admin/config",
            json={"ai_provider": "anthropic", "ai_temperature": 0.3},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 200
        entries = (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "config_update")
            )
        ).scalars().all()
        assert len(entries) == 1
        entry = entries[0]
        assert entry.admin_user_id == admin.id
        assert entry.target_type == "app_settings"
        assert entry.target_id == "1"
        assert entry.before_json is not None
        assert entry.after_json is not None
        assert entry.before_json["ai_provider"] == "openai"
        assert entry.after_json["ai_provider"] == "anthropic"
        # API key must be masked in both snapshots
        assert "sk-test" not in entry.before_json["ai_api_key"]
        assert "sk-test" not in entry.after_json["ai_api_key"]

    async def test_no_audit_log_when_nothing_changes(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, cookies = await _make_admin_and_cookie(db_session)
        await _seed_default_app_settings(db_session)
        res = await client.put(
            "/api/admin/config",
            json={"ai_provider": "openai"},  # same as current
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 200
        entries = (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "config_update")
            )
        ).all()
        assert len(entries) == 0

    async def test_refreshes_settings_singleton(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """After PUT, the in-memory settings singleton must reflect the
        new values — this is what makes the CSRF middleware pick up a new
        allowed-origins list without restart.
        """
        from flexloop.config import settings

        _, cookies = await _make_admin_and_cookie(db_session)
        await _seed_default_app_settings(db_session)
        res = await client.put(
            "/api/admin/config",
            json={"admin_allowed_origins": ["https://admin.example.com"]},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 200
        assert settings.admin_allowed_origins == ["https://admin.example.com"]
```

- [ ] **Step 2: Run them to confirm failure**

```bash
uv run pytest tests/test_admin_config.py::TestUpdateConfig -v
```

Expected: all 9 fail.

- [ ] **Step 3: Commit**

```bash
git add tests/test_admin_config.py
git commit -m "test(admin): failing tests for PUT /api/admin/config"
```

---

### Task 11: Implement `PUT /api/admin/config`

**Files:**
- Modify: `src/flexloop/admin/routers/config.py`

- [ ] **Step 1: Append the update handler**

```python
@router.put("", response_model=AppSettingsResponse)
async def update_config(
    payload: AppSettingsUpdate,
    db: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(require_admin),
) -> dict:
    row = await _load_row(db)

    before_snapshot = _masked_dict(row)

    updates = payload.model_dump(exclude_unset=True)

    # Special handling for ai_api_key: if the incoming value matches the
    # masked form of the current key, treat it as "no change" — the UI
    # round-tripped the mask back to us. Any OTHER value (including empty
    # string) overwrites.
    if "ai_api_key" in updates:
        incoming = updates["ai_api_key"]
        if incoming == _mask_key(row.ai_api_key):
            del updates["ai_api_key"]

    for field, value in updates.items():
        setattr(row, field, value)

    after_snapshot = _masked_dict(row)

    # Only write an audit entry if SOMETHING actually changed.
    changed_fields = {
        k: after_snapshot[k]
        for k in after_snapshot
        if after_snapshot[k] != before_snapshot[k]
    }
    if changed_fields:
        await write_audit_log(
            db,
            admin_user_id=admin.id,
            action="config_update",
            target_type="app_settings",
            target_id="1",
            before={k: before_snapshot[k] for k in changed_fields},
            after=changed_fields,
        )

    await db.commit()
    # Mutate the in-memory singleton so subsequent requests (and the CSRF
    # middleware) see the new values without a server restart.
    await refresh_settings_from_db(db)

    return AppSettingsResponse(
        ai_provider=row.ai_provider,
        ai_model=row.ai_model,
        ai_api_key=_mask_key(row.ai_api_key),
        ai_base_url=row.ai_base_url,
        ai_temperature=row.ai_temperature,
        ai_max_tokens=row.ai_max_tokens,
        ai_review_frequency=row.ai_review_frequency,
        ai_review_block_weeks=row.ai_review_block_weeks,
        admin_allowed_origins=list(row.admin_allowed_origins or []),
    )
```

- [ ] **Step 2: Run the update tests**

```bash
uv run pytest tests/test_admin_config.py::TestUpdateConfig -v
```

Expected: all 9 pass.

- [ ] **Step 3: Full suite check**

```bash
uv run pytest -q
```

Expected: 317 tests green.

- [ ] **Step 4: Commit**

```bash
git add src/flexloop/admin/routers/config.py
git commit -m "feat(admin): PUT /api/admin/config with audit log + settings refresh"
```

---

### Task 12: Failing tests for `POST /api/admin/config/test-connection`

**Files:**
- Modify: `tests/test_admin_config.py`

The test-connection endpoint calls the AI factory, which we must NOT hit for real in tests. Use monkeypatch to replace `create_adapter` with a fake that returns a controllable `LLMResponse`.

- [ ] **Step 1: Append the test class**

```python
class TestTestConnection:
    async def test_requires_auth(self, client: AsyncClient) -> None:
        res = await client.post(
            "/api/admin/config/test-connection",
            json={},
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 401

    async def test_returns_ok_with_fake_adapter(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from flexloop.ai.base import LLMResponse
        from flexloop.admin.routers import config as config_router

        class _FakeAdapter:
            def __init__(self, *a, **kw):
                pass

            async def generate(self, system_prompt, user_prompt, temperature, max_tokens):
                return LLMResponse(content="Hello!", input_tokens=5, output_tokens=2)

        def _fake_create_adapter(*args, **kwargs):
            return _FakeAdapter()

        monkeypatch.setattr(config_router, "create_adapter", _fake_create_adapter)

        _, cookies = await _make_admin_and_cookie(db_session)
        await _seed_default_app_settings(db_session)
        res = await client.post(
            "/api/admin/config/test-connection",
            json={},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "ok"
        assert body["response_text"] == "Hello!"
        assert body["error"] is None
        assert isinstance(body["latency_ms"], int)
        assert body["latency_ms"] >= 0

    async def test_returns_error_when_adapter_raises(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from flexloop.admin.routers import config as config_router

        class _FailingAdapter:
            def __init__(self, *a, **kw):
                pass

            async def generate(self, *a, **kw):
                raise RuntimeError("boom")

        def _fake_create_adapter(*a, **kw):
            return _FailingAdapter()

        monkeypatch.setattr(config_router, "create_adapter", _fake_create_adapter)

        _, cookies = await _make_admin_and_cookie(db_session)
        await _seed_default_app_settings(db_session)
        res = await client.post(
            "/api/admin/config/test-connection",
            json={},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "error"
        assert body["response_text"] is None
        assert "boom" in body["error"]

    async def test_override_fields_are_used(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that the override payload is passed to create_adapter, not
        the saved config."""
        from flexloop.ai.base import LLMResponse
        from flexloop.admin.routers import config as config_router

        captured: dict = {}

        class _FakeAdapter:
            def __init__(self, *a, **kw):
                pass

            async def generate(self, *a, **kw):
                return LLMResponse(content="ok", input_tokens=1, output_tokens=1)

        def _fake_create_adapter(provider, model, api_key, base_url, **kwargs):
            captured["provider"] = provider
            captured["model"] = model
            captured["api_key"] = api_key
            captured["base_url"] = base_url
            return _FakeAdapter()

        monkeypatch.setattr(config_router, "create_adapter", _fake_create_adapter)

        _, cookies = await _make_admin_and_cookie(db_session)
        await _seed_default_app_settings(db_session)
        res = await client.post(
            "/api/admin/config/test-connection",
            json={
                "provider": "anthropic",
                "model": "claude-test",
                "api_key": "sk-override-abc",
                "base_url": "https://override.example.com",
            },
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 200
        assert captured["provider"] == "anthropic"
        assert captured["model"] == "claude-test"
        assert captured["api_key"] == "sk-override-abc"
        assert captured["base_url"] == "https://override.example.com"

    async def test_does_not_write_audit_log(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from flexloop.ai.base import LLMResponse
        from flexloop.admin.routers import config as config_router

        class _FakeAdapter:
            def __init__(self, *a, **kw):
                pass

            async def generate(self, *a, **kw):
                return LLMResponse(content="ok", input_tokens=1, output_tokens=1)

        monkeypatch.setattr(
            config_router, "create_adapter", lambda *a, **kw: _FakeAdapter()
        )
        _, cookies = await _make_admin_and_cookie(db_session)
        await _seed_default_app_settings(db_session)
        await client.post(
            "/api/admin/config/test-connection",
            json={},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        entries = (
            await db_session.execute(select(AdminAuditLog))
        ).all()
        assert len(entries) == 0
```

- [ ] **Step 2: Run them to confirm failure**

```bash
uv run pytest tests/test_admin_config.py::TestTestConnection -v
```

Expected: all 5 fail.

- [ ] **Step 3: Commit**

```bash
git add tests/test_admin_config.py
git commit -m "test(admin): failing tests for POST /api/admin/config/test-connection"
```

---

### Task 13: Implement `POST /api/admin/config/test-connection`

**Files:**
- Modify: `src/flexloop/admin/routers/config.py`

- [ ] **Step 1: Append the handler**

```python
_TEST_CONNECTION_SYSTEM = "You are a helpful assistant."
_TEST_CONNECTION_USER = "Say hello in one word."
_TEST_CONNECTION_TIMEOUT_SEC = 30.0


@router.post("/test-connection", response_model=TestConnectionResponse)
async def test_connection(
    payload: TestConnectionRequest,
    db: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(require_admin),
) -> TestConnectionResponse:
    """Fire a tiny round-trip to the AI provider and return the result.

    Override fields in the payload are used when present, else the saved
    config is used. The endpoint always returns 200 — failures are
    returned in the ``status`` field so the UI can render them inline.
    """
    row = await _load_row(db)

    provider = payload.provider or row.ai_provider
    model = payload.model or row.ai_model
    api_key = payload.api_key if payload.api_key is not None else row.ai_api_key
    base_url = payload.base_url if payload.base_url is not None else row.ai_base_url
    temperature = (
        payload.temperature if payload.temperature is not None else row.ai_temperature
    )
    max_tokens = payload.max_tokens if payload.max_tokens is not None else 10

    adapter = create_adapter(
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
    )

    start = time.perf_counter()
    try:
        llm_response = await asyncio.wait_for(
            adapter.generate(
                system_prompt=_TEST_CONNECTION_SYSTEM,
                user_prompt=_TEST_CONNECTION_USER,
                temperature=temperature,
                max_tokens=max_tokens,
            ),
            timeout=_TEST_CONNECTION_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        return TestConnectionResponse(
            status="error",
            latency_ms=int(_TEST_CONNECTION_TIMEOUT_SEC * 1000),
            response_text=None,
            error=f"timeout after {int(_TEST_CONNECTION_TIMEOUT_SEC)}s",
        )
    except Exception as e:  # noqa: BLE001 — we want to surface any adapter failure
        latency_ms = int((time.perf_counter() - start) * 1000)
        return TestConnectionResponse(
            status="error",
            latency_ms=latency_ms,
            response_text=None,
            error=str(e),
        )

    latency_ms = int((time.perf_counter() - start) * 1000)
    return TestConnectionResponse(
        status="ok",
        latency_ms=latency_ms,
        response_text=llm_response.content[:200],
        error=None,
    )
```

- [ ] **Step 2: Run the tests**

```bash
uv run pytest tests/test_admin_config.py::TestTestConnection -v
```

Expected: all 5 pass.

- [ ] **Step 3: Full suite**

```bash
uv run pytest -q
```

Expected: 322 tests green (317 + 5 test-connection tests).

- [ ] **Step 4: Commit**

```bash
git add src/flexloop/admin/routers/config.py
git commit -m "feat(admin): POST /api/admin/config/test-connection with fake-adapter tests"
```

---

**End of Chunk 3.** Backend config editor is complete with audit log, hot-reload, and test-connection. Next chunk adds the frontend page.

---

## Chunk 4: Frontend — Config editor page

### Task 14: Regenerate TypeScript types from the updated OpenAPI schema

**Files:**
- Modify: `admin-ui/src/lib/api.types.ts`

Same pattern as phase 3's Chunk 3 Task 14. The backend must be running to dump the schema.

- [ ] **Step 1: Start the backend in the background**

Use `run_in_background: true` on the Bash tool:

```bash
cd /Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase4a
uv run uvicorn flexloop.main:app --port 8000
```

- [ ] **Step 2: Regenerate types**

```bash
cd /Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase4a/admin-ui
sleep 2
npm run codegen
```

Expected: `src/lib/api.types.ts` is rewritten. `git diff` should show new entries for `AppSettingsResponse`, `AppSettingsUpdate`, `TestConnectionRequest`, `TestConnectionResponse`.

- [ ] **Step 3: Stop the backend**

Kill the background uvicorn.

- [ ] **Step 4: Commit**

```bash
cd ..
git add admin-ui/src/lib/api.types.ts
git commit -m "chore(admin-ui): regenerate api.types.ts for config schemas"
```

---

### Task 15: Create `ConfigForm` component

**Files:**
- Create: `admin-ui/src/components/forms/ConfigForm.tsx`

A hand-written rhf + zod form scoped to the editable fields. The sectioned layout uses plain `<h2>` headings and dividers — no Tabs.

- [ ] **Step 1: Create the component**

```tsx
/**
 * Config form — sectioned layout for AppSettings fields.
 *
 * Sections:
 * - AI Provider: provider, model, api_key (masked), base_url
 * - Generation Defaults: temperature, max_tokens
 * - Review Schedule: review_frequency, review_block_weeks
 * - Allowed Origins: admin_allowed_origins (CSV input)
 *
 * The API key field uses type="password" with a reveal toggle (client-side
 * only). The "Rotate" button clears the field so the user can paste a new
 * value. After save, the server returns the masked form which the parent
 * page writes back into the form's defaults.
 */
import { useState } from "react";
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

type Config = components["schemas"]["AppSettingsResponse"];

const schema = z.object({
  ai_provider: z.string().min(1),
  ai_model: z.string().min(1),
  ai_api_key: z.string(),
  ai_base_url: z.string(),
  ai_temperature: z.coerce.number().min(0).max(2),
  ai_max_tokens: z.coerce.number().int().positive(),
  ai_review_frequency: z.string().min(1),
  ai_review_block_weeks: z.coerce.number().int().positive(),
  admin_allowed_origins_csv: z.string(),
});

export type ConfigFormInput = z.input<typeof schema>;
export type ConfigFormValues = z.output<typeof schema>;

type Props = {
  defaultValues: Config;
  onSubmit: (values: ConfigFormValues) => void | Promise<void>;
  isSaving?: boolean;
};

export function ConfigForm({ defaultValues, onSubmit, isSaving = false }: Props) {
  const [revealKey, setRevealKey] = useState(false);

  const { register, handleSubmit, setValue, watch } = useForm<
    ConfigFormInput,
    unknown,
    ConfigFormValues
  >({
    resolver: zodResolver(schema),
    defaultValues: {
      ai_provider: defaultValues.ai_provider,
      ai_model: defaultValues.ai_model,
      ai_api_key: defaultValues.ai_api_key,
      ai_base_url: defaultValues.ai_base_url,
      ai_temperature: defaultValues.ai_temperature,
      ai_max_tokens: defaultValues.ai_max_tokens,
      ai_review_frequency: defaultValues.ai_review_frequency,
      ai_review_block_weeks: defaultValues.ai_review_block_weeks,
      admin_allowed_origins_csv: (defaultValues.admin_allowed_origins ?? []).join(
        ", ",
      ),
    },
  });

  const provider = watch("ai_provider");
  const frequency = watch("ai_review_frequency");

  return (
    <form
      onSubmit={(e) => void handleSubmit((v) => onSubmit(v))(e)}
      className="space-y-8 max-w-2xl"
    >
      {/* AI Provider */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold border-b pb-2">AI Provider</h2>
        <div className="space-y-1.5">
          <Label htmlFor="ai_provider">Provider</Label>
          <Select
            value={provider}
            onValueChange={(v) => setValue("ai_provider", v)}
          >
            <SelectTrigger id="ai_provider">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="openai">OpenAI</SelectItem>
              <SelectItem value="openai-compatible">OpenAI-compatible</SelectItem>
              <SelectItem value="anthropic">Anthropic</SelectItem>
              <SelectItem value="ollama">Ollama</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="ai_model">Model</Label>
          <Input id="ai_model" {...register("ai_model")} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="ai_api_key">API Key</Label>
          <div className="flex gap-2">
            <Input
              id="ai_api_key"
              type={revealKey ? "text" : "password"}
              className="font-mono"
              {...register("ai_api_key")}
            />
            <Button
              type="button"
              variant="outline"
              onClick={() => setRevealKey((r) => !r)}
            >
              {revealKey ? "Hide" : "Reveal"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => setValue("ai_api_key", "")}
            >
              Rotate
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            The key is masked for display. Leave as-is to keep the current key,
            or type a new value to rotate.
          </p>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="ai_base_url">Base URL</Label>
          <Input
            id="ai_base_url"
            placeholder="(optional — leave blank for provider default)"
            {...register("ai_base_url")}
          />
        </div>
      </section>

      {/* Generation Defaults */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold border-b pb-2">Generation Defaults</h2>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="ai_temperature">Temperature</Label>
            <Input
              id="ai_temperature"
              type="number"
              step="0.05"
              {...register("ai_temperature")}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ai_max_tokens">Max tokens</Label>
            <Input
              id="ai_max_tokens"
              type="number"
              {...register("ai_max_tokens")}
            />
          </div>
        </div>
      </section>

      {/* Review Schedule */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold border-b pb-2">Review Schedule</h2>
        <div className="space-y-1.5">
          <Label htmlFor="ai_review_frequency">Frequency</Label>
          <Select
            value={frequency}
            onValueChange={(v) => setValue("ai_review_frequency", v)}
          >
            <SelectTrigger id="ai_review_frequency">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="block">Per block</SelectItem>
              <SelectItem value="weekly">Weekly</SelectItem>
              <SelectItem value="never">Never</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="ai_review_block_weeks">Block length (weeks)</Label>
          <Input
            id="ai_review_block_weeks"
            type="number"
            {...register("ai_review_block_weeks")}
          />
        </div>
      </section>

      {/* Allowed Origins */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold border-b pb-2">Allowed Origins</h2>
        <div className="space-y-1.5">
          <Label htmlFor="admin_allowed_origins_csv">
            Admin allowed origins (comma-separated)
          </Label>
          <Input
            id="admin_allowed_origins_csv"
            placeholder="http://localhost:5173, https://admin.example.com"
            {...register("admin_allowed_origins_csv")}
          />
          <p className="text-xs text-muted-foreground">
            Used by the CSRF middleware. Changes take effect immediately
            after save — no restart required.
          </p>
        </div>
      </section>

      <div className="flex justify-end pt-4 border-t">
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
cd admin-ui && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
cd ..
git add admin-ui/src/components/forms/ConfigForm.tsx
git commit -m "feat(admin-ui): ConfigForm with sectioned layout + masked key reveal/rotate"
```

---

### Task 16: Create `ConfigPage` with test-connection card

**Files:**
- Create: `admin-ui/src/pages/ConfigPage.tsx`

- [ ] **Step 1: Create the page**

```tsx
/**
 * Admin Config page.
 *
 * Top: "Test connection" card — fires POST /api/admin/config/test-connection
 * with the current form values as overrides, shows status + latency +
 * response preview.
 *
 * Middle: ConfigForm — sectioned form for editing AppSettings.
 *
 * Save sends PUT /api/admin/config. Empty ai_api_key field is interpreted
 * as "explicitly clear the key" — the user had to click Rotate and confirm.
 * Unchanged (masked) field is round-tripped as-is and the server leaves
 * the plaintext alone.
 */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { ConfigForm } from "@/components/forms/ConfigForm";
import type { ConfigFormValues } from "@/components/forms/ConfigForm";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import type { components } from "@/lib/api.types";

type Config = components["schemas"]["AppSettingsResponse"];
type ConfigUpdate = components["schemas"]["AppSettingsUpdate"];
type TestResult = components["schemas"]["TestConnectionResponse"];
type TestRequest = components["schemas"]["TestConnectionRequest"];

const CONFIG_KEY = ["admin", "config"];

function formValuesToUpdate(v: ConfigFormValues): ConfigUpdate {
  const origins = v.admin_allowed_origins_csv
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
  return {
    ai_provider: v.ai_provider,
    ai_model: v.ai_model,
    ai_api_key: v.ai_api_key,
    ai_base_url: v.ai_base_url,
    ai_temperature: v.ai_temperature,
    ai_max_tokens: v.ai_max_tokens,
    ai_review_frequency: v.ai_review_frequency,
    ai_review_block_weeks: v.ai_review_block_weeks,
    admin_allowed_origins: origins,
  };
}

export function ConfigPage() {
  const qc = useQueryClient();
  const [testResult, setTestResult] = useState<TestResult | null>(null);

  const configQuery = useQuery({
    queryKey: CONFIG_KEY,
    queryFn: () => api.get<Config>("/api/admin/config"),
  });

  const save = useMutation({
    mutationFn: (input: ConfigUpdate) =>
      api.put<Config>("/api/admin/config", input),
    onSuccess: () => {
      toast.success("Config saved");
      qc.invalidateQueries({ queryKey: CONFIG_KEY });
    },
    onError: (e) => {
      toast.error(e instanceof Error ? e.message : "Save failed");
    },
  });

  const testConnection = useMutation({
    mutationFn: (input: TestRequest) =>
      api.post<TestResult>("/api/admin/config/test-connection", input),
    onSuccess: (data) => {
      setTestResult(data);
    },
    onError: (e) => {
      setTestResult({
        status: "error",
        latency_ms: 0,
        response_text: null,
        error: e instanceof Error ? e.message : "Test failed",
      });
    },
  });

  if (configQuery.isLoading) {
    return <div className="p-6">Loading config…</div>;
  }
  if (configQuery.isError || !configQuery.data) {
    return (
      <div className="p-6 space-y-2">
        <p>Failed to load config.</p>
        <p className="text-sm text-muted-foreground">
          If this is a fresh deployment, make sure the seed migration has run.
        </p>
      </div>
    );
  }

  const config = configQuery.data;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Config</h1>
        <p className="text-sm text-muted-foreground">
          Runtime-mutable settings. Changes take effect immediately —
          no restart required.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Test connection</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center gap-3">
            <Button
              onClick={() =>
                testConnection.mutate({
                  // No overrides — use saved config
                })
              }
              disabled={testConnection.isPending}
            >
              {testConnection.isPending ? "Testing…" : "Test connection"}
            </Button>
            {testResult && (
              <Badge variant={testResult.status === "ok" ? "default" : "destructive"}>
                {testResult.status === "ok" ? "OK" : "Error"}
              </Badge>
            )}
            {testResult && (
              <span className="text-sm text-muted-foreground tabular-nums">
                {testResult.latency_ms} ms
              </span>
            )}
          </div>
          {testResult?.status === "ok" && testResult.response_text && (
            <pre className="text-xs bg-muted p-2 rounded overflow-x-auto">
              {testResult.response_text}
            </pre>
          )}
          {testResult?.status === "error" && testResult.error && (
            <pre className="text-xs bg-red-500/10 text-red-700 dark:text-red-400 p-2 rounded overflow-x-auto">
              {testResult.error}
            </pre>
          )}
        </CardContent>
      </Card>

      <ConfigForm
        defaultValues={config}
        isSaving={save.isPending}
        onSubmit={async (v) => {
          await save.mutateAsync(formValuesToUpdate(v));
        }}
      />
    </div>
  );
}
```

- [ ] **Step 2: Verify it compiles**

```bash
cd admin-ui && npx tsc --noEmit
```

Expected: no errors. If `Card*` exports aren't where expected, read `admin-ui/src/components/ui/card.tsx` and adjust imports.

- [ ] **Step 3: Commit**

```bash
cd ..
git add admin-ui/src/pages/ConfigPage.tsx
git commit -m "feat(admin-ui): ConfigPage with test-connection card + sectioned form"
```

---

### Task 17: Wire up the route and enable the sidebar item

**Files:**
- Modify: `admin-ui/src/App.tsx`
- Modify: `admin-ui/src/components/AppSidebar.tsx`

- [ ] **Step 1: Add the route in App.tsx**

Add the import near the other page imports:

```tsx
import { ConfigPage } from "@/pages/ConfigPage";
```

Add the route inside the authenticated layout, near the other `/ai/*` routes:

```tsx
<Route path="ai/config" element={<ConfigPage />} />
```

- [ ] **Step 2: Enable the Config sidebar item**

Open `admin-ui/src/components/AppSidebar.tsx`. Find:

```tsx
{ label: "Config", to: "/ai/config", icon: Settings, disabled: true },
```

Remove `disabled: true`:

```tsx
{ label: "Config", to: "/ai/config", icon: Settings },
```

- [ ] **Step 3: Verify the build**

```bash
cd admin-ui && npx tsc --noEmit && npm run build
```

Expected: both green. Bundle size may grow slightly with the new page.

- [ ] **Step 4: Commit**

```bash
cd ..
git add admin-ui/src/App.tsx admin-ui/src/components/AppSidebar.tsx
git commit -m "feat(admin-ui): wire /ai/config route and enable sidebar item"
```

---

**End of Chunk 4.** Config editor frontend is shipped. Next chunk handles smoke test + merge.

---

## Chunk 5: Smoke test and merge

### Task 18: Write the smoke test checklist

**Files:**
- Create: `docs/admin-dashboard-phase4a-smoke-test.md` (at parent FlexLoop level, matching phase 1/2/3 location)

- [ ] **Step 1: Create the checklist**

```markdown
# Phase 4a (Config editor + audit log) smoke test

Manual checklist plus automated subset via Playwright.

## Environment setup

- [ ] Backend running: `uv run uvicorn flexloop.main:app --port 8000`
- [ ] Admin UI built: `cd admin-ui && npm run build`
- [ ] Seed migration has run (verify: `sqlite3 flexloop.db "SELECT COUNT(*) FROM app_settings"` returns 1)
- [ ] Logged in as admin at http://localhost:8000/admin

## Config page

- [ ] Navigate to /admin/ai/config — sidebar item enabled, page loads
- [ ] Page shows "Config" header + "Test connection" card + sectioned form
- [ ] Form pre-populates with current settings (ai_provider, ai_model, etc.)
- [ ] ai_api_key field shows masked value (bullets + last 3 chars), not plaintext
- [ ] Click "Reveal" — field becomes type=text and shows whatever is currently in the input; click "Hide" — reverts
- [ ] Click "Rotate" — field clears to empty
- [ ] Type a new value in the API key field, click Save — toast "Config saved"
- [ ] Re-fetch (refresh page): ai_api_key is masked again. Verify DB via SQLite: the plaintext is actually stored.
- [ ] Leave the masked key as-is (don't touch it), change ai_provider only, Save — DB still has the original plaintext (masked roundtrip doesn't overwrite)

## Test connection

- [ ] Click "Test connection" with a valid API key — shows "OK" badge + latency + response preview (e.g. "Hello")
- [ ] Set ai_api_key to a garbage value (temporarily), Save, then Test connection — shows "Error" badge + latency + error message
- [ ] (Don't forget to restore the real key)

## Audit log

- [ ] Make a config change via the UI
- [ ] Query DB: `sqlite3 flexloop.db "SELECT action, target_type, target_id, before_json, after_json FROM admin_audit_log ORDER BY id DESC LIMIT 1"`
- [ ] Verify: action="config_update", target_type="app_settings", target_id="1", before_json and after_json show only the changed fields, api_key is masked (not plaintext) in both

## CSRF hot-reload

- [ ] Add a new origin to "Allowed Origins" (CSV), Save
- [ ] From another browser/curl with that new Origin header, hit a protected endpoint — should succeed (was previously rejected)
- [ ] Remove the new origin, Save — subsequent requests with that Origin should 403

## Regression checks

- [ ] iOS-facing endpoints still work: `curl http://localhost:8000/api/plans?user_id=1`
- [ ] Phase 3 Plans page still loads at /admin/plans
- [ ] Phase 2 Workouts page still loads

## Automated

- [ ] `uv run pytest -q` — full suite green (expected 322 tests)
- [ ] `cd admin-ui && npm run build` — succeeds
- [ ] Optional: run the automated Playwright smoke script at `/tmp/smoke_phase4a.py` (see plan 4a execution notes)
```

- [ ] **Step 2: Commit the checklist**

```bash
cd /Users/flyingchickens/Projects/FlexLoop
git add docs/admin-dashboard-phase4a-smoke-test.md
git commit -m "docs(admin): phase 4a smoke test checklist"
cd /Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase4a
```

(The checklist lives in the parent FlexLoop repo's docs/, matching the phase 1/2/3 location.)

---

### Task 19: Write + execute automated Playwright smoke test

The smoke script follows the phase 3 pattern: seed a fresh DB, start the backend via `with_server.py`, run a headless chromium script that exercises the critical path. Keep the script at `/tmp/smoke_phase4a.py` — it's not committed, just a verification tool.

- [ ] **Step 1: Reuse the playwright venv from phase 3 if it still exists, else recreate**

```bash
if [ ! -x /tmp/phase3-playwright-venv/bin/python3 ]; then
  python3 -m venv /tmp/phase4a-playwright-venv
  /tmp/phase4a-playwright-venv/bin/pip install playwright
  /tmp/phase4a-playwright-venv/bin/playwright install chromium
  ln -s /tmp/phase4a-playwright-venv /tmp/phase3-playwright-venv
fi
```

(The symlink keeps the same path convention.)

- [ ] **Step 2: Create `/tmp/seed_phase4a_smoke.py`** that creates an admin user + a seeded `app_settings` row.

Details left to the executor; mirror `/tmp/seed_phase3_smoke.py` from phase 3 but add an `AppSettings` row with id=1 and sensible defaults (empty API key is fine — test-connection will use the fake adapter).

- [ ] **Step 3: Create `/tmp/smoke_phase4a.py`** covering:
  1. Login
  2. Navigate to /ai/config
  3. Verify form pre-populates with seeded values
  4. Verify API key field shows the masked form (bullets + last 3 chars), not plaintext
  5. Change ai_temperature to 0.5, click Save, verify toast
  6. Refresh page, verify ai_temperature is now 0.5
  7. (Skip test-connection — it needs a real API key or a mock, and the headless test can't easily monkeypatch the server)
  8. Verify an audit log row was created by hitting a small helper endpoint OR by skipping (plan tests already cover this)

- [ ] **Step 4: Run the smoke script**

```bash
cd /Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase4a
rm -f /tmp/flexloop-phase4a-smoke.db
DATABASE_URL='sqlite+aiosqlite:////tmp/flexloop-phase4a-smoke.db' \
  uv run python /tmp/seed_phase4a_smoke.py
DATABASE_URL='sqlite+aiosqlite:////tmp/flexloop-phase4a-smoke.db' \
  python3 /Users/flyingchickens/.claude/plugins/cache/anthropic-agent-skills/example-skills/b0cbd3df1533/skills/webapp-testing/scripts/with_server.py \
  --server 'uv run uvicorn flexloop.main:app --port 8000' \
  --port 8000 --timeout 60 \
  -- /tmp/phase3-playwright-venv/bin/python3 /tmp/smoke_phase4a.py
```

Expected: ALL SMOKE TESTS PASSED.

- [ ] **Step 5: Mark the checklist as executed**

Prepend a line to `docs/admin-dashboard-phase4a-smoke-test.md`:

```markdown
> **Automated Playwright smoke executed 2026-MM-DD — all checks ✅.**
```

Commit the update (to the parent FlexLoop repo's docs).

---

### Task 20: Merge `feat/admin-dashboard-phase4a-config` to main

- [ ] **Step 1: Verify clean + commit count**

```bash
cd /Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase4a
git status
git log --oneline main..HEAD | wc -l
```

Expected: clean, ~17+ commits.

- [ ] **Step 2: Fast-forward merge from the flexloop-server root**

```bash
cd /Users/flyingchickens/Projects/FlexLoop/flexloop-server
git checkout main
git merge --ff-only feat/admin-dashboard-phase4a-config
```

- [ ] **Step 3: Run full suite on main**

```bash
uv run pytest -q
```

Expected: 322 tests green.

- [ ] **Step 4: Push main**

```bash
git push origin main
```

- [ ] **Step 5: Bump parent submodule pointer**

```bash
cd /Users/flyingchickens/Projects/FlexLoop
git add flexloop-server
git commit -m "chore: bump flexloop-server to admin dashboard phase 4a"
```

- [ ] **Step 6: Clean up worktree and feature branch**

```bash
cd /Users/flyingchickens/Projects/FlexLoop/flexloop-server
git worktree remove /Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase4a
git branch -d feat/admin-dashboard-phase4a-config
```

- [ ] **Step 7: Update auto-memory status file**

Edit `/Users/flyingchickens/.claude/projects/-Users-flyingchickens-Projects-FlexLoop/memory/project_admin_dashboard_status.md`:
- Mark phase 4a as COMPLETE with today's date
- Move phase 4b (Prompt editor) into "next up"

---

**End of Chunk 5.** Plan 4a is shipped: config editor, audit log helper, runtime DB-backed settings, CSRF hot-reload. Next sub-plan: 4b (Prompt editor).

---

## Summary

**Backend deliverables:**
- `src/flexloop/admin/audit.py` — reusable `write_audit_log` helper
- `src/flexloop/admin/routers/config.py` — 3 endpoints (GET, PUT, test-connection)
- `src/flexloop/config.py` — `refresh_settings_from_db` + `admin_allowed_origins` field
- `src/flexloop/db/engine.py` — calls refresh on startup
- `src/flexloop/main.py` — swaps CSRF middleware source, registers config router
- `alembic/versions/<new>_seed_app_settings.py` — idempotent row seed
- 3 test files (~24 new tests total): `test_admin_audit.py`, `test_admin_config.py`, `test_runtime_settings.py`

**Frontend deliverables:**
- `admin-ui/src/pages/ConfigPage.tsx` — sectioned form + test-connection card
- `admin-ui/src/components/forms/ConfigForm.tsx` — rhf+zod form
- `admin-ui/src/App.tsx` + `AppSidebar.tsx` — new route + enabled sidebar item
- `admin-ui/src/lib/api.types.ts` — regenerated

**Docs:** `docs/admin-dashboard-phase4a-smoke-test.md` (parent FlexLoop repo)

**End state:** The operator can view and edit runtime AI config through the admin UI, test the connection without saving, see audit log entries for every change, and update the allowed-origins list without restarting the server. Phase 4b (Prompt editor) is the next sub-plan and will build on the audit helper established here.
