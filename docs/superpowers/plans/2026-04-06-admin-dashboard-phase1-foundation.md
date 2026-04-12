# Admin Dashboard — Phase 1 (Foundation) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the foundation slice of the admin dashboard — database schema, auth (login/logout/sessions), the React SPA shell with a working sidebar, a health-first dashboard page, and a health detail page. End state: you can `npm run build`, start the server, hit `/admin`, log in, see a working dashboard and health page. Nothing else exists yet.

**Architecture:** New `flexloop.admin` Python package inside the existing server package; new `admin-ui/` Vite+React+TS SPA inside `flexloop-server/` that builds to `src/flexloop/static/admin/`. Same-origin deploy (FastAPI serves both the JSON API under `/api/admin/*` and the static SPA bundle under `/admin/*`). Auth via bcrypt + opaque server-side session tokens in `admin_sessions` table.

**Tech Stack:** Python 3.12 + FastAPI + SQLAlchemy + Alembic + aiosqlite + bcrypt (backend); Vite + React 18 + TypeScript + Tailwind CSS + shadcn/ui + TanStack Query + React Router + react-hook-form + zod (frontend).

**Spec reference:** `docs/superpowers/specs/2026-04-06-admin-dashboard-design.md`. Read §1-§8 and §13-§14 before starting.

**Phases 2-5**: out of scope for this plan. They will get their own plan files written after Phase 1 ships. The spec covers what's coming.

---

## File Structure

New files created in this phase:

**Backend — migrations and models:**
```
flexloop-server/
├── alembic/versions/<hash>_admin_dashboard_phase1.py     migration
├── src/flexloop/models/
│   ├── admin_user.py              NEW
│   ├── admin_session.py           NEW
│   ├── admin_audit_log.py         NEW
│   ├── app_settings.py            NEW
│   └── model_pricing.py           NEW
```

**Backend — admin module:**
```
flexloop-server/src/flexloop/admin/
├── __init__.py                    NEW
├── auth.py                        NEW — bcrypt, session CRUD, require_admin dependency
├── csrf.py                        NEW — Origin header check middleware
├── audit.py                       NEW — audit log helpers
├── log_handler.py                 NEW — RingBufferHandler + rotating JSONL writer
├── pricing.py                     NEW — static PRICING dict (stub in this phase)
├── bootstrap.py                   NEW — CLI: create-admin, reset-admin-password
└── routers/
    ├── __init__.py                NEW
    ├── auth.py                    NEW — /login, /logout, /me, /change-password, /sessions
    └── health.py                  NEW — /health endpoint
```

**Backend — modified:**
```
flexloop-server/
├── pyproject.toml                 add bcrypt, python-multipart deps
├── src/flexloop/
│   ├── main.py                    install log handler, mount admin routers, mount static
│   └── models/__init__.py         register new models with Base
```

**Frontend — entirely new:**
```
flexloop-server/admin-ui/
├── package.json                   NEW
├── package-lock.json              NEW (generated)
├── tsconfig.json                  NEW
├── tsconfig.node.json             NEW
├── vite.config.ts                 NEW
├── tailwind.config.ts             NEW
├── postcss.config.js              NEW
├── index.html                     NEW
├── components.json                NEW — shadcn/ui config
├── .gitignore                     NEW
└── src/
    ├── main.tsx                   NEW — React entry
    ├── App.tsx                    NEW — router setup
    ├── index.css                  NEW — Tailwind directives + shadcn CSS vars
    ├── vite-env.d.ts              NEW
    ├── lib/
    │   ├── api.ts                 NEW — fetch wrapper + base URL
    │   ├── query.ts               NEW — QueryClient setup
    │   └── utils.ts               NEW — cn helper from shadcn
    ├── hooks/
    │   └── useAuth.ts             NEW — login, logout, me queries
    ├── components/
    │   ├── ui/                    NEW — shadcn/ui generated components
    │   ├── AuthGate.tsx           NEW — redirect-to-login wrapper
    │   ├── AppShell.tsx           NEW — sidebar layout
    │   └── AppSidebar.tsx         NEW — nav items list
    └── pages/
        ├── LoginPage.tsx          NEW
        ├── DashboardPage.tsx      NEW
        ├── HealthPage.tsx         NEW
        ├── ChangePasswordPage.tsx NEW
        └── SessionsPage.tsx       NEW
```

**Tests:**
```
flexloop-server/tests/
├── test_admin_auth.py             NEW — bootstrap CLI, auth service, auth router
├── test_admin_health.py           NEW
└── test_admin_log_handler.py      NEW
```

---

## Chunk 1: Backend Foundation — Models & Migration

### Task 1: Add Python dependencies

**Files:**
- Modify: `flexloop-server/pyproject.toml`

- [ ] **Step 1: Edit pyproject.toml**

Add to the `dependencies` list in `[project]`:

```toml
    "bcrypt>=4.0.0",
    "python-multipart>=0.0.9",
```

Full context (where to add — after existing `greenlet` line):

```toml
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "sqlalchemy>=2.0.0",
    "alembic>=1.13.0",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
    "openai>=1.50.0",
    "anthropic>=0.40.0",
    "httpx>=0.27.0",
    "aiosqlite>=0.20.0",
    "greenlet>=3.0.0",
    "bcrypt>=4.0.0",
    "python-multipart>=0.0.9",
]
```

- [ ] **Step 2: Run uv sync to install**

```bash
cd flexloop-server
uv sync
```

Expected: both packages install without errors. `bcrypt` and `python-multipart` appear in the output.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore(admin): add bcrypt and python-multipart deps"
```

---

### Task 2: Create AdminUser model

**Files:**
- Create: `flexloop-server/src/flexloop/models/admin_user.py`

- [ ] **Step 1: Write the failing test**

Create `flexloop-server/tests/test_admin_auth.py` with this initial content (we'll add more tests to it in later tasks):

```python
import pytest
from sqlalchemy import select

from flexloop.models.admin_user import AdminUser


async def test_admin_user_can_be_created(db_session):
    user = AdminUser(
        username="testadmin",
        password_hash="$2b$12$fakehash",
    )
    db_session.add(user)
    await db_session.flush()
    result = await db_session.execute(select(AdminUser).where(AdminUser.username == "testadmin"))
    loaded = result.scalar_one()
    assert loaded.id is not None
    assert loaded.username == "testadmin"
    assert loaded.is_active is True
    assert loaded.last_login_at is None
    assert loaded.created_at is not None
```

- [ ] **Step 2: Run the test and verify it fails**

```bash
cd flexloop-server
uv run pytest tests/test_admin_auth.py::test_admin_user_can_be_created -v
```

Expected: `ImportError` or `ModuleNotFoundError` for `flexloop.models.admin_user`.

- [ ] **Step 3: Create the model**

Create `flexloop-server/src/flexloop/models/admin_user.py`:

```python
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from flexloop.db.base import Base


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
```

- [ ] **Step 4: Register the model in models/__init__.py**

Edit `flexloop-server/src/flexloop/models/__init__.py` — add the import and export:

```python
from flexloop.models.admin_user import AdminUser
```

And add `"AdminUser"` to the `__all__` list (alphabetical is fine).

- [ ] **Step 5: Re-run the test**

```bash
uv run pytest tests/test_admin_auth.py::test_admin_user_can_be_created -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/flexloop/models/admin_user.py src/flexloop/models/__init__.py tests/test_admin_auth.py
git commit -m "feat(admin): add AdminUser model with test"
```

---

### Task 3: Create AdminSession model

**Files:**
- Create: `flexloop-server/src/flexloop/models/admin_session.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_admin_auth.py`:

```python
from datetime import datetime, timedelta
from flexloop.models.admin_session import AdminSession


async def test_admin_session_can_be_created(db_session):
    user = AdminUser(username="testadmin", password_hash="x")
    db_session.add(user)
    await db_session.flush()

    session = AdminSession(
        id="abc123deadbeef",
        admin_user_id=user.id,
        expires_at=datetime.utcnow() + timedelta(days=14),
    )
    db_session.add(session)
    await db_session.flush()

    result = await db_session.execute(
        select(AdminSession).where(AdminSession.id == "abc123deadbeef")
    )
    loaded = result.scalar_one()
    assert loaded.admin_user_id == user.id
    assert loaded.created_at is not None
    assert loaded.last_seen_at is not None
    assert loaded.expires_at > datetime.utcnow()
```

- [ ] **Step 2: Run and verify failure**

```bash
uv run pytest tests/test_admin_auth.py::test_admin_session_can_be_created -v
```

Expected: `ModuleNotFoundError: No module named 'flexloop.models.admin_session'`.

- [ ] **Step 3: Create the model**

Create `flexloop-server/src/flexloop/models/admin_session.py`:

```python
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from flexloop.db.base import Base


class AdminSession(Base):
    __tablename__ = "admin_sessions"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    admin_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
```

- [ ] **Step 4: Register in models/__init__.py**

Add `from flexloop.models.admin_session import AdminSession` and add to `__all__`.

- [ ] **Step 5: Re-run the test**

```bash
uv run pytest tests/test_admin_auth.py::test_admin_session_can_be_created -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/flexloop/models/admin_session.py src/flexloop/models/__init__.py tests/test_admin_auth.py
git commit -m "feat(admin): add AdminSession model with test"
```

---

### Task 4: Create AdminAuditLog, AppSettings, and ModelPricing models

**Files:**
- Create: `flexloop-server/src/flexloop/models/admin_audit_log.py`
- Create: `flexloop-server/src/flexloop/models/app_settings.py`
- Create: `flexloop-server/src/flexloop/models/model_pricing.py`

These three are bundled because they're structurally similar and none is used by code in Phase 1 beyond existing in the schema. They'll be exercised by later phases. We only need a minimal smoke test that they can be created.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_admin_auth.py`:

```python
from flexloop.models.admin_audit_log import AdminAuditLog
from flexloop.models.app_settings import AppSettings
from flexloop.models.model_pricing import ModelPricing


async def test_admin_audit_log_can_be_created(db_session):
    entry = AdminAuditLog(
        admin_user_id=None,
        action="config.update",
        target_type="app_settings",
        target_id="1",
        before_json={"ai_model": "old"},
        after_json={"ai_model": "new"},
    )
    db_session.add(entry)
    await db_session.flush()
    assert entry.id is not None


async def test_app_settings_can_be_created(db_session):
    row = AppSettings(
        id=1,
        ai_provider="openai",
        ai_model="gpt-4o-mini",
        ai_api_key="sk-test",
        ai_base_url="",
        ai_temperature=0.7,
        ai_max_tokens=2000,
        ai_review_frequency="block",
        ai_review_block_weeks=6,
        admin_allowed_origins=["http://localhost:5173"],
    )
    db_session.add(row)
    await db_session.flush()
    assert row.id == 1
    assert row.admin_allowed_origins == ["http://localhost:5173"]


async def test_model_pricing_can_be_created(db_session):
    row = ModelPricing(
        model_name="custom-proxy-model",
        input_per_million=0.2,
        output_per_million=0.6,
    )
    db_session.add(row)
    await db_session.flush()
    assert row.model_name == "custom-proxy-model"
```

- [ ] **Step 2: Run and verify failure**

```bash
uv run pytest tests/test_admin_auth.py -v
```

Expected: three new tests fail with `ModuleNotFoundError`.

- [ ] **Step 3: Create admin_audit_log.py**

Create `flexloop-server/src/flexloop/models/admin_audit_log.py`:

```python
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from flexloop.db.base import Base


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    admin_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    before_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
```

- [ ] **Step 4: Create app_settings.py**

Create `flexloop-server/src/flexloop/models/app_settings.py`:

```python
from sqlalchemy import JSON, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from flexloop.db.base import Base


class AppSettings(Base):
    """Single-row table holding runtime-mutable application settings.

    Always loaded as id=1. Created/updated via flexloop.admin.config endpoints.
    """
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # always 1
    ai_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    ai_model: Mapped[str] = mapped_column(String(128), nullable=False)
    ai_api_key: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    ai_base_url: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    ai_temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    ai_max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=2000)
    ai_review_frequency: Mapped[str] = mapped_column(String(32), nullable=False, default="block")
    ai_review_block_weeks: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    admin_allowed_origins: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
```

- [ ] **Step 5: Create model_pricing.py**

Create `flexloop-server/src/flexloop/models/model_pricing.py`:

```python
from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column

from flexloop.db.base import Base


class ModelPricing(Base):
    """Per-model AI cost overrides. Takes precedence over the static PRICING dict.

    Populated via the admin UI when a proxied or custom model isn't in the
    default pricing table.
    """
    __tablename__ = "model_pricing"

    model_name: Mapped[str] = mapped_column(String(128), primary_key=True)
    input_per_million: Mapped[float] = mapped_column(Float, nullable=False)
    output_per_million: Mapped[float] = mapped_column(Float, nullable=False)
    cache_read_per_million: Mapped[float | None] = mapped_column(Float, nullable=True)
    cache_write_per_million: Mapped[float | None] = mapped_column(Float, nullable=True)
```

- [ ] **Step 6: Register all three in models/__init__.py**

Add the three imports and extend `__all__`:

```python
from flexloop.models.admin_audit_log import AdminAuditLog
from flexloop.models.admin_user import AdminUser
from flexloop.models.admin_session import AdminSession
from flexloop.models.app_settings import AppSettings
from flexloop.models.model_pricing import ModelPricing
```

- [ ] **Step 7: Re-run tests**

```bash
uv run pytest tests/test_admin_auth.py -v
```

Expected: all tests PASS.

- [ ] **Step 8: Commit**

```bash
git add src/flexloop/models/admin_audit_log.py \
        src/flexloop/models/app_settings.py \
        src/flexloop/models/model_pricing.py \
        src/flexloop/models/__init__.py \
        tests/test_admin_auth.py
git commit -m "feat(admin): add audit log, app_settings, model_pricing models"
```

---

### Task 5: Generate the Alembic migration

**Files:**
- Modify: `flexloop-server/alembic/env.py`
- Create: `flexloop-server/alembic/versions/<hash>_admin_dashboard_phase1.py`

- [ ] **Step 1: Make alembic autogenerate see the new models**

The existing `alembic/env.py` only imports `Base` — it doesn't import `flexloop.models`, so `Base.metadata` has zero registered tables at autogenerate time and the command would emit an empty migration. Add one line to fix this.

Edit `flexloop-server/alembic/env.py`. Find the line:

```python
from flexloop.db.base import Base
```

Change to:

```python
from flexloop.db.base import Base
import flexloop.models  # noqa: F401 — register all models with Base.metadata
```

- [ ] **Step 2: Verify tests still pass after the env.py edit**

```bash
uv run pytest -q
```

Expected: all existing tests pass. The env.py import change only affects alembic runs, not app/test behavior, but this catches circular-import regressions.

- [ ] **Step 3: Auto-generate the migration**

```bash
cd flexloop-server
uv run alembic revision --autogenerate -m "admin dashboard phase 1"
```

Expected: new file appears in `alembic/versions/`. Read it to confirm it creates all five tables (`admin_users`, `admin_sessions`, `admin_audit_log`, `app_settings`, `model_pricing`). If it's empty, Step 1 wasn't saved.

- [ ] **Step 4: Add a data migration step for seeding app_settings from .env**

Open the new migration file. Inside the `upgrade()` function, AFTER the `op.create_table("app_settings", ...)` block, add an `op.bulk_insert` that seeds the single row using the current environment values:

```python
def upgrade() -> None:
    # ... auto-generated create_table calls above ...

    # Seed the single app_settings row from current .env defaults.
    # This runs once per deployment; subsequent changes happen via the admin UI.
    from sqlalchemy import table, column, String, Integer, Float, JSON
    import os

    app_settings_table = table(
        "app_settings",
        column("id", Integer),
        column("ai_provider", String),
        column("ai_model", String),
        column("ai_api_key", String),
        column("ai_base_url", String),
        column("ai_temperature", Float),
        column("ai_max_tokens", Integer),
        column("ai_review_frequency", String),
        column("ai_review_block_weeks", Integer),
        column("admin_allowed_origins", JSON),
    )

    op.bulk_insert(
        app_settings_table,
        [{
            "id": 1,
            "ai_provider": os.environ.get("AI_PROVIDER", "openai"),
            "ai_model": os.environ.get("AI_MODEL", "gpt-4o-mini"),
            "ai_api_key": os.environ.get("AI_API_KEY", ""),
            "ai_base_url": os.environ.get("AI_BASE_URL", ""),
            "ai_temperature": float(os.environ.get("AI_TEMPERATURE", "0.7")),
            "ai_max_tokens": int(os.environ.get("AI_MAX_TOKENS", "2000")),
            "ai_review_frequency": os.environ.get("AI_REVIEW_FREQUENCY", "block"),
            "ai_review_block_weeks": int(os.environ.get("AI_REVIEW_BLOCK_WEEKS", "6")),
            "admin_allowed_origins": ["http://localhost:5173", "http://localhost:8000"],
        }],
    )
```

Also make sure the migration correctly reads from `.env` during migration — alembic uses its own config path, which doesn't auto-load `.env`. Load it explicitly at the top of the migration:

```python
# at top of migration file, after revision metadata
from pathlib import Path
from dotenv import load_dotenv
# Load .env relative to the project root (alembic.ini's parent)
load_dotenv(Path(__file__).resolve().parents[2] / ".env")
```

Note: `python-dotenv` is already a transitive dep (via `pydantic-settings`), so no new install needed.

- [ ] **Step 5: Check the downgrade function drops the tables in reverse order**

The autogen should handle this, but verify `downgrade()` drops `model_pricing`, `app_settings`, `admin_audit_log`, `admin_sessions`, `admin_users` (reverse of create).

- [ ] **Step 6: Apply the migration to the local dev DB**

```bash
uv run alembic upgrade head
```

Expected: "Running upgrade ... -> <new_hash>, admin dashboard phase 1". No errors.

- [ ] **Step 7: Verify the tables exist with sqlite3**

```bash
sqlite3 flexloop.db ".tables" | grep -E "(admin_users|admin_sessions|admin_audit_log|app_settings|model_pricing)"
```

Expected: all five tables listed.

- [ ] **Step 8: Verify the seed row was inserted**

```bash
sqlite3 flexloop.db "SELECT * FROM app_settings;"
```

Expected: one row with the current AI settings from your `.env`.

- [ ] **Step 9: Test downgrade cleanly**

```bash
uv run alembic downgrade -1
sqlite3 flexloop.db ".tables" | grep -c admin
```

Expected: 0 (all admin tables dropped). Then re-upgrade:

```bash
uv run alembic upgrade head
```

- [ ] **Step 10: Run the full test suite as a safety net**

```bash
uv run pytest -q
```

Expected: all tests still pass. This catches the case where a new model conflicts with the autouse `Base.metadata.create_all` test fixture.

- [ ] **Step 11: Commit**

```bash
git add alembic/env.py alembic/versions/
git commit -m "feat(admin): alembic migration for phase 1 tables + app_settings seed"
```

---

## Chunk 2: Backend — Auth Service, Bootstrap CLI, Auth Router

### Task 6: Create admin package skeleton

**Files:**
- Create: `flexloop-server/src/flexloop/admin/__init__.py`
- Create: `flexloop-server/src/flexloop/admin/routers/__init__.py`

- [ ] **Step 1: Create empty package files**

```bash
mkdir -p src/flexloop/admin/routers
touch src/flexloop/admin/__init__.py
touch src/flexloop/admin/routers/__init__.py
```

- [ ] **Step 2: Commit**

```bash
git add src/flexloop/admin/
git commit -m "chore(admin): package skeleton"
```

---

### Task 7: Auth service — password hashing and session token helpers

**Files:**
- Create: `flexloop-server/src/flexloop/admin/auth.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_admin_auth.py`:

```python
from flexloop.admin.auth import (
    hash_password,
    verify_password,
    create_session,
    lookup_session,
    revoke_session,
    require_admin,
)


def test_hash_and_verify_password_roundtrip():
    h = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", h) is True
    assert verify_password("wrong password", h) is False


async def test_create_and_lookup_session(db_session):
    user = AdminUser(username="u1", password_hash=hash_password("pw"))
    db_session.add(user)
    await db_session.flush()

    token = await create_session(db_session, admin_user_id=user.id, user_agent="test-ua", ip="127.0.0.1")
    assert isinstance(token, str)
    assert len(token) == 64  # 32 bytes hex

    loaded = await lookup_session(db_session, token)
    assert loaded is not None
    assert loaded.admin_user_id == user.id
    assert loaded.user_agent == "test-ua"


async def test_lookup_session_returns_none_for_unknown_token(db_session):
    assert await lookup_session(db_session, "nonexistent") is None


async def test_revoke_session(db_session):
    user = AdminUser(username="u2", password_hash=hash_password("pw"))
    db_session.add(user)
    await db_session.flush()
    token = await create_session(db_session, admin_user_id=user.id)

    await revoke_session(db_session, token)
    assert await lookup_session(db_session, token) is None


async def test_lookup_session_rejects_expired(db_session):
    from datetime import datetime, timedelta
    user = AdminUser(username="u3", password_hash=hash_password("pw"))
    db_session.add(user)
    await db_session.flush()

    # Manually create an expired session
    sess = AdminSession(
        id="expired_token",
        admin_user_id=user.id,
        expires_at=datetime.utcnow() - timedelta(seconds=1),
    )
    db_session.add(sess)
    await db_session.flush()

    assert await lookup_session(db_session, "expired_token") is None


async def test_lookup_session_bumps_last_seen_and_expiry(db_session):
    from datetime import datetime, timedelta
    user = AdminUser(username="u4", password_hash=hash_password("pw"))
    db_session.add(user)
    await db_session.flush()
    token = await create_session(db_session, admin_user_id=user.id)

    result = await db_session.execute(select(AdminSession).where(AdminSession.id == token))
    before = result.scalar_one()
    original_expiry = before.expires_at
    original_last_seen = before.last_seen_at

    # Wait a moment then look up again
    import asyncio
    await asyncio.sleep(0.01)
    await lookup_session(db_session, token)

    result = await db_session.execute(select(AdminSession).where(AdminSession.id == token))
    after = result.scalar_one()
    assert after.last_seen_at > original_last_seen
    assert after.expires_at > original_expiry
```

- [ ] **Step 2: Run tests and verify failure**

```bash
uv run pytest tests/test_admin_auth.py -v -k "password or session"
```

Expected: `ImportError: cannot import name 'hash_password' from 'flexloop.admin.auth'`.

- [ ] **Step 3: Implement auth.py**

Create `flexloop-server/src/flexloop/admin/auth.py`:

```python
"""Admin authentication primitives: bcrypt hashing and opaque session tokens.

Sessions are DB-keyed opaque random tokens stored in admin_sessions. There is
no signing — the lookup IS the validation. The cookie value is the token.
"""
import secrets
from datetime import datetime, timedelta

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.db.engine import get_session
from flexloop.models.admin_session import AdminSession
from flexloop.models.admin_user import AdminUser

SESSION_DURATION = timedelta(days=14)
SESSION_COOKIE_NAME = "flexloop_admin_session"


def hash_password(password: str) -> str:
    """Hash a password with bcrypt. Cost factor 12 is the bcrypt default."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


async def create_session(
    db: AsyncSession,
    admin_user_id: int,
    user_agent: str | None = None,
    ip: str | None = None,
) -> str:
    """Create a new session row. Returns the opaque token to set as the cookie value."""
    token = secrets.token_hex(32)  # 64 hex chars
    now = datetime.utcnow()
    session = AdminSession(
        id=token,
        admin_user_id=admin_user_id,
        created_at=now,
        last_seen_at=now,
        expires_at=now + SESSION_DURATION,
        user_agent=user_agent,
        ip_address=ip,
    )
    db.add(session)
    await db.flush()
    return token


async def lookup_session(db: AsyncSession, token: str) -> AdminSession | None:
    """Look up a session by token. Bumps last_seen_at and expires_at on hit.

    Returns None if the token doesn't exist, the session has expired, or the
    associated admin user is inactive.
    """
    result = await db.execute(select(AdminSession).where(AdminSession.id == token))
    session = result.scalar_one_or_none()
    if session is None:
        return None

    now = datetime.utcnow()
    if session.expires_at < now:
        return None

    # Verify the associated user is still active
    user_result = await db.execute(
        select(AdminUser).where(AdminUser.id == session.admin_user_id)
    )
    user = user_result.scalar_one_or_none()
    if user is None or not user.is_active:
        return None

    # Bump last_seen_at and roll the expiry forward (rolling 14-day window)
    session.last_seen_at = now
    session.expires_at = now + SESSION_DURATION
    await db.flush()
    return session


async def revoke_session(db: AsyncSession, token: str) -> None:
    await db.execute(delete(AdminSession).where(AdminSession.id == token))
    await db.flush()


async def revoke_all_sessions(db: AsyncSession, admin_user_id: int) -> int:
    """Delete every session for a given admin. Returns count removed."""
    result = await db.execute(
        delete(AdminSession).where(AdminSession.admin_user_id == admin_user_id)
    )
    await db.flush()
    return result.rowcount or 0


async def require_admin(
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> AdminUser:
    """FastAPI dependency that enforces an active admin session.

    Used by every admin endpoint except /api/admin/auth/login.
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated"
        )
    session = await lookup_session(db, token)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="session expired"
        )
    result = await db.execute(select(AdminUser).where(AdminUser.id == session.admin_user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="user inactive"
        )
    return user
```

- [ ] **Step 4: Re-run the tests**

```bash
uv run pytest tests/test_admin_auth.py -v -k "password or session"
```

Expected: all password/session tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/flexloop/admin/auth.py tests/test_admin_auth.py
git commit -m "feat(admin): bcrypt + opaque session token auth primitives"
```

---

### Task 8: Bootstrap CLI — create-admin and reset-admin-password

**Files:**
- Create: `flexloop-server/src/flexloop/admin/bootstrap.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_admin_auth.py`:

```python
from flexloop.admin.bootstrap import create_admin_user, reset_admin_password


async def test_create_admin_user(db_session):
    user = await create_admin_user(db_session, "newadmin", "mypassword123")
    assert user.id is not None
    assert user.username == "newadmin"
    assert verify_password("mypassword123", user.password_hash)


async def test_create_admin_user_rejects_duplicate(db_session):
    await create_admin_user(db_session, "dup", "pw1")
    with pytest.raises(ValueError, match="already exists"):
        await create_admin_user(db_session, "dup", "pw2")


async def test_reset_admin_password(db_session):
    await create_admin_user(db_session, "resetme", "oldpw")
    await reset_admin_password(db_session, "resetme", "newpw")

    result = await db_session.execute(select(AdminUser).where(AdminUser.username == "resetme"))
    user = result.scalar_one()
    assert verify_password("newpw", user.password_hash)
    assert not verify_password("oldpw", user.password_hash)


async def test_reset_admin_password_rejects_unknown(db_session):
    with pytest.raises(ValueError, match="not found"):
        await reset_admin_password(db_session, "nobody", "pw")
```

- [ ] **Step 2: Run and verify failure**

```bash
uv run pytest tests/test_admin_auth.py -v -k "create_admin_user or reset_admin_password"
```

Expected: ImportError.

- [ ] **Step 3: Implement bootstrap.py**

Create `flexloop-server/src/flexloop/admin/bootstrap.py`:

```python
"""Admin bootstrap CLI — create the first admin and reset passwords.

Usage:
    uv run python -m flexloop.admin.bootstrap create-admin <username>
    uv run python -m flexloop.admin.bootstrap reset-admin-password <username>

Both commands prompt for a password interactively (using getpass for no echo).
"""
import asyncio
import getpass
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import hash_password
from flexloop.db.engine import async_session
from flexloop.models.admin_user import AdminUser


async def create_admin_user(db: AsyncSession, username: str, password: str) -> AdminUser:
    """Create a new admin user. Raises ValueError if username exists."""
    result = await db.execute(select(AdminUser).where(AdminUser.username == username))
    if result.scalar_one_or_none() is not None:
        raise ValueError(f"admin user {username!r} already exists")
    user = AdminUser(username=username, password_hash=hash_password(password))
    db.add(user)
    await db.flush()
    return user


async def reset_admin_password(db: AsyncSession, username: str, new_password: str) -> None:
    """Reset an existing admin's password. Raises ValueError if username unknown."""
    result = await db.execute(select(AdminUser).where(AdminUser.username == username))
    user = result.scalar_one_or_none()
    if user is None:
        raise ValueError(f"admin user {username!r} not found")
    user.password_hash = hash_password(new_password)
    await db.flush()


def _prompt_password() -> str:
    while True:
        pw = getpass.getpass("Password: ")
        if len(pw) < 8:
            print("Password must be at least 8 characters. Try again.")
            continue
        confirm = getpass.getpass("Confirm: ")
        if pw != confirm:
            print("Passwords don't match. Try again.")
            continue
        return pw


async def _cli_create_admin(username: str) -> None:
    password = _prompt_password()
    async with async_session() as db:
        try:
            user = await create_admin_user(db, username, password)
            await db.commit()
            print(f"Created admin user {user.username!r} (id={user.id}).")
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


async def _cli_reset_admin_password(username: str) -> None:
    password = _prompt_password()
    async with async_session() as db:
        try:
            await reset_admin_password(db, username, password)
            await db.commit()
            print(f"Password reset for {username!r}.")
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage:\n  python -m flexloop.admin.bootstrap create-admin <username>")
        print("  python -m flexloop.admin.bootstrap reset-admin-password <username>")
        sys.exit(2)

    command, username = sys.argv[1], sys.argv[2]
    if command == "create-admin":
        asyncio.run(_cli_create_admin(username))
    elif command == "reset-admin-password":
        asyncio.run(_cli_reset_admin_password(username))
    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Re-run tests**

```bash
uv run pytest tests/test_admin_auth.py -v -k "create_admin_user or reset_admin_password"
```

Expected: all four tests PASS.

- [ ] **Step 5: Manual smoke test of the CLI**

```bash
uv run python -m flexloop.admin.bootstrap create-admin manualtest
# enter password when prompted, then the same again
```

Expected: "Created admin user 'manualtest' (id=N)." prints. Verify:

```bash
sqlite3 flexloop.db "SELECT id, username, is_active FROM admin_users WHERE username='manualtest';"
```

Clean up after:

```bash
sqlite3 flexloop.db "DELETE FROM admin_users WHERE username='manualtest';"
```

- [ ] **Step 6: Commit**

```bash
git add src/flexloop/admin/bootstrap.py tests/test_admin_auth.py
git commit -m "feat(admin): bootstrap CLI for create-admin and reset-admin-password"
```

---

### Task 9: CSRF Origin-header middleware

**Files:**
- Create: `flexloop-server/src/flexloop/admin/csrf.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_admin_auth.py`:

```python
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from flexloop.admin.csrf import OriginCheckMiddleware

ALLOWED = ["http://localhost:5173", "http://localhost:8000"]


async def _build_app() -> FastAPI:
    a = FastAPI()
    a.add_middleware(OriginCheckMiddleware, allowed_origins_getter=lambda: ALLOWED)

    @a.get("/api/admin/test")
    async def get_handler():
        return {"ok": True}

    @a.post("/api/admin/test")
    async def post_handler():
        return {"ok": True}

    @a.get("/api/something-else")
    async def other_handler():
        return {"ok": True}

    return a


async def test_get_requests_bypass_origin_check():
    a = await _build_app()
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        r = await c.get("/api/admin/test")
        assert r.status_code == 200


async def test_post_with_allowed_origin_succeeds():
    a = await _build_app()
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        r = await c.post("/api/admin/test", headers={"Origin": "http://localhost:5173"})
        assert r.status_code == 200


async def test_post_with_disallowed_origin_fails():
    a = await _build_app()
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        r = await c.post("/api/admin/test", headers={"Origin": "http://evil.example.com"})
        assert r.status_code == 403


async def test_post_without_origin_fails():
    a = await _build_app()
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        r = await c.post("/api/admin/test")
        assert r.status_code == 403


async def test_non_admin_routes_bypass_origin_check():
    a = await _build_app()
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        r = await c.get("/api/something-else")
        assert r.status_code == 200
```

- [ ] **Step 2: Run and verify failure**

```bash
uv run pytest tests/test_admin_auth.py -v -k "origin"
```

Expected: ImportError.

- [ ] **Step 3: Implement csrf.py**

Create `flexloop-server/src/flexloop/admin/csrf.py`:

```python
"""CSRF protection for admin endpoints via Origin header check.

For state-changing methods on /api/admin/* paths, the request's Origin header
must match one of the configured allowed origins. GETs and non-admin routes
are not checked (they're idempotent or outside our concern).

Combined with SameSite=Strict on the session cookie (set in auth router),
this gives belt-and-braces CSRF protection without needing signed tokens.
"""
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

STATE_CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
PROTECTED_PREFIX = "/api/admin"


class OriginCheckMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        allowed_origins_getter: Callable[[], list[str]],
    ):
        super().__init__(app)
        self._get_allowed = allowed_origins_getter

    async def dispatch(self, request: Request, call_next):
        # Skip if this isn't a protected path or a state-changing method
        if not request.url.path.startswith(PROTECTED_PREFIX):
            return await call_next(request)
        if request.method not in STATE_CHANGING_METHODS:
            return await call_next(request)

        origin = request.headers.get("origin")
        if origin is None or origin not in self._get_allowed():
            return JSONResponse(
                status_code=403,
                content={"detail": "origin check failed"},
            )
        return await call_next(request)
```

**Note on `allowed_origins_getter`**: we pass a callable instead of a static list so that later (in Phase 4) the middleware can pick up runtime changes to `app_settings.admin_allowed_origins` without requiring a server restart. For Phase 1, the callable returns a fixed list.

- [ ] **Step 4: Re-run tests**

```bash
uv run pytest tests/test_admin_auth.py -v -k "origin"
```

Expected: all five tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/flexloop/admin/csrf.py tests/test_admin_auth.py
git commit -m "feat(admin): CSRF Origin header middleware"
```

---

### Task 10: Auth router — login, logout, me, change-password, sessions

**Files:**
- Modify: `flexloop-server/tests/conftest.py`
- Create: `flexloop-server/src/flexloop/admin/routers/auth.py`

- [ ] **Step 1: Update the test client to use HTTPS (required for Secure cookies)**

The auth router sets the session cookie with `Secure=True` (correct for production). But httpx's `AsyncClient` won't *send* a Secure cookie back on subsequent `http://` requests, which would break every integration test that depends on being logged in.

The fix is a one-line change in `tests/conftest.py`: switch the client fixture's `base_url` from `http://test` to `https://test`. httpx still hits the in-process ASGI app — the `https://` is just metadata to unlock cookie-sending.

Edit `flexloop-server/tests/conftest.py`, find this block:

```python
@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
```

Change `http://test` to `https://test`:

```python
@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        yield ac
```

- [ ] **Step 2: Verify existing tests still pass after the scheme change**

```bash
uv run pytest -q
```

Expected: all tests pass. This is a no-op for tests that don't inspect the scheme; it's a prereq for the auth tests we're about to add.

- [ ] **Step 3: Write failing integration tests**

Append to `tests/test_admin_auth.py`:

```python
# ---- Auth router integration tests ----

@pytest.fixture
async def seeded_admin(db_session):
    """Create a test admin user. Returns (user, plaintext_password)."""
    from flexloop.admin.bootstrap import create_admin_user
    password = "testpw12345"
    user = await create_admin_user(db_session, "routertest", password)
    await db_session.commit()
    return user, password


async def test_login_success(client, seeded_admin):
    user, password = seeded_admin
    r = await client.post(
        "/api/admin/auth/login",
        json={"username": user.username, "password": password},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["username"] == user.username
    assert "expires_at" in body
    # Cookie should be set
    assert "flexloop_admin_session" in r.cookies


async def test_login_wrong_password(client, seeded_admin):
    user, _ = seeded_admin
    r = await client.post(
        "/api/admin/auth/login",
        json={"username": user.username, "password": "wrong"},
    )
    assert r.status_code == 401


async def test_login_unknown_user(client):
    r = await client.post(
        "/api/admin/auth/login",
        json={"username": "ghost", "password": "anything"},
    )
    assert r.status_code == 401


async def test_me_without_cookie(client):
    r = await client.get("/api/admin/auth/me")
    assert r.status_code == 401


async def test_login_then_me(client, seeded_admin):
    user, password = seeded_admin
    login = await client.post(
        "/api/admin/auth/login",
        json={"username": user.username, "password": password},
    )
    assert login.status_code == 200

    me = await client.get("/api/admin/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == user.username


async def test_logout_clears_session(client, seeded_admin):
    user, password = seeded_admin
    await client.post(
        "/api/admin/auth/login",
        json={"username": user.username, "password": password},
    )
    # Logout endpoint requires Origin header (state-changing)
    r = await client.post(
        "/api/admin/auth/logout",
        headers={"Origin": "http://localhost:5173"},
    )
    assert r.status_code == 200

    me = await client.get("/api/admin/auth/me")
    assert me.status_code == 401


async def test_change_password_success(client, seeded_admin):
    user, password = seeded_admin
    await client.post(
        "/api/admin/auth/login",
        json={"username": user.username, "password": password},
    )
    r = await client.post(
        "/api/admin/auth/change-password",
        json={"current_password": password, "new_password": "newpw67890"},
        headers={"Origin": "http://localhost:5173"},
    )
    assert r.status_code == 200

    # Old password no longer works
    r2 = await client.post(
        "/api/admin/auth/login",
        json={"username": user.username, "password": password},
    )
    assert r2.status_code == 401


async def test_change_password_wrong_current(client, seeded_admin):
    user, password = seeded_admin
    await client.post(
        "/api/admin/auth/login",
        json={"username": user.username, "password": password},
    )
    r = await client.post(
        "/api/admin/auth/change-password",
        json={"current_password": "wrong", "new_password": "newpw67890"},
        headers={"Origin": "http://localhost:5173"},
    )
    assert r.status_code == 400


async def test_list_and_revoke_sessions(client, seeded_admin):
    user, password = seeded_admin
    await client.post(
        "/api/admin/auth/login",
        json={"username": user.username, "password": password},
    )
    r = await client.get("/api/admin/auth/sessions")
    assert r.status_code == 200
    sessions = r.json()
    assert len(sessions) == 1
    sess_id = sessions[0]["id"]

    # Revoke it
    r2 = await client.delete(
        f"/api/admin/auth/sessions/{sess_id}",
        headers={"Origin": "http://localhost:5173"},
    )
    assert r2.status_code == 200

    # me should now be 401
    me = await client.get("/api/admin/auth/me")
    assert me.status_code == 401
```

**Important for these tests**: the `client` fixture in `conftest.py` already wires up the app. But the CSRF middleware isn't mounted yet — we need to add it in `main.py` when we mount the auth router. Add a note: the CSRF check requires `Origin` header, which the tests supply.

Also update `conftest.py` if needed so the Origin header is accepted in tests — the Origin `http://localhost:5173` is in the allowed list we'll configure.

- [ ] **Step 4: Run and verify failure**

```bash
uv run pytest tests/test_admin_auth.py -v -k "login or logout or me or change_password or sessions_"
```

Expected: all new tests 404 (router not mounted yet).

- [ ] **Step 5: Implement the auth router**

Create `flexloop-server/src/flexloop/admin/routers/auth.py`:

```python
"""Admin auth router: /api/admin/auth/*"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import (
    SESSION_COOKIE_NAME,
    SESSION_DURATION,
    create_session,
    hash_password,
    require_admin,
    revoke_session,
    verify_password,
)
from flexloop.db.engine import get_session
from flexloop.models.admin_session import AdminSession
from flexloop.models.admin_user import AdminUser

router = APIRouter(prefix="/api/admin/auth", tags=["admin:auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class LoginResponse(BaseModel):
    ok: bool
    username: str
    expires_at: datetime


class MeResponse(BaseModel):
    username: str
    expires_at: datetime


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=256)


class SessionInfo(BaseModel):
    id: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    user_agent: str | None
    ip_address: str | None
    is_current: bool


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=int(SESSION_DURATION.total_seconds()),
        httponly=True,
        secure=True,
        samesite="strict",
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")


@router.post("/login", response_model=LoginResponse)
async def login(
    data: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(select(AdminUser).where(AdminUser.username == data.username))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(data.password, user.password_hash):
        # Generic error message — do not reveal whether the user exists
        raise HTTPException(status_code=401, detail="invalid credentials")

    token = await create_session(
        db,
        admin_user_id=user.id,
        user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client else None,
    )
    user.last_login_at = datetime.utcnow()
    await db.commit()

    _set_session_cookie(response, token)
    return LoginResponse(
        ok=True,
        username=user.username,
        expires_at=datetime.utcnow() + SESSION_DURATION,
    )


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_session),
):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        await revoke_session(db, token)
        await db.commit()
    _clear_session_cookie(response)
    return {"ok": True}


@router.get("/me", response_model=MeResponse)
async def me(
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: AdminUser = Depends(require_admin),
):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    result = await db.execute(select(AdminSession).where(AdminSession.id == token))
    session = result.scalar_one()
    return MeResponse(username=user.username, expires_at=session.expires_at)


@router.post("/change-password")
async def change_password(
    data: ChangePasswordRequest,
    db: AsyncSession = Depends(get_session),
    user: AdminUser = Depends(require_admin),
):
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="current password incorrect")
    user.password_hash = hash_password(data.new_password)
    await db.commit()
    return {"ok": True}


@router.get("/sessions", response_model=list[SessionInfo])
async def list_sessions(
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: AdminUser = Depends(require_admin),
):
    current_token = request.cookies.get(SESSION_COOKIE_NAME)
    result = await db.execute(
        select(AdminSession)
        .where(AdminSession.admin_user_id == user.id)
        .order_by(AdminSession.created_at.desc())
    )
    sessions = result.scalars().all()
    return [
        SessionInfo(
            id=s.id,
            created_at=s.created_at,
            last_seen_at=s.last_seen_at,
            expires_at=s.expires_at,
            user_agent=s.user_agent,
            ip_address=s.ip_address,
            is_current=(s.id == current_token),
        )
        for s in sessions
    ]


@router.delete("/sessions/{session_id}")
async def revoke_specific_session(
    session_id: str,
    db: AsyncSession = Depends(get_session),
    user: AdminUser = Depends(require_admin),
):
    # Make sure the session belongs to the current admin
    result = await db.execute(
        select(AdminSession).where(
            AdminSession.id == session_id,
            AdminSession.admin_user_id == user.id,
        )
    )
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="session not found")
    await revoke_session(db, session_id)
    await db.commit()
    return {"ok": True}
```

- [ ] **Step 6: Mount the router + CSRF middleware in main.py**

Edit `flexloop-server/src/flexloop/main.py`. Add imports and mounts:

```python
# near the top of imports
from flexloop.admin.csrf import OriginCheckMiddleware
from flexloop.admin.routers.auth import router as admin_auth_router

# ... existing code ...

app = FastAPI(
    title="FlexLoop API",
    description="AI-powered fitness training companion",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CSRF middleware BEFORE routers so it runs on every /api/admin/* request
# For Phase 1: fixed allowed-origins list. Phase 4 will replace this callable
# with one that reads from app_settings.admin_allowed_origins.
_PHASE1_ALLOWED_ORIGINS = ["http://localhost:5173", "http://localhost:8000"]
app.add_middleware(
    OriginCheckMiddleware,
    allowed_origins_getter=lambda: _PHASE1_ALLOWED_ORIGINS,
)

app.include_router(profiles_router)
# ... existing routers ...
app.include_router(admin_auth_router)
```

- [ ] **Step 7: Re-run the full auth test suite**

```bash
uv run pytest tests/test_admin_auth.py -v
```

Expected: all tests PASS. Count should be ~20 tests.

- [ ] **Step 8: Commit**

```bash
git add src/flexloop/admin/routers/auth.py src/flexloop/main.py tests/test_admin_auth.py tests/conftest.py
git commit -m "feat(admin): auth router with login/logout/me/change-password/sessions"
```

---

## Chunk 3: Backend — Log Handler, Health Router

### Task 11: RingBufferHandler for in-memory logging

**Files:**
- Create: `flexloop-server/src/flexloop/admin/log_handler.py`
- Create: `flexloop-server/tests/test_admin_log_handler.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_admin_log_handler.py`:

```python
import logging

import pytest

from flexloop.admin.log_handler import RingBufferHandler


def test_handler_captures_records():
    handler = RingBufferHandler(capacity=100)
    logger = logging.getLogger("test.ringbuffer")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    logger.info("hello world")
    logger.warning("danger")

    records = handler.get_records()
    assert len(records) == 2
    assert records[0]["level"] == "INFO"
    assert records[0]["message"] == "hello world"
    assert records[1]["level"] == "WARNING"
    assert records[1]["message"] == "danger"
    assert records[0]["logger"] == "test.ringbuffer"
    assert "timestamp" in records[0]

    logger.removeHandler(handler)


def test_handler_respects_capacity():
    handler = RingBufferHandler(capacity=3)
    logger = logging.getLogger("test.ringbuffer_cap")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    for i in range(5):
        logger.info(f"msg {i}")

    records = handler.get_records()
    assert len(records) == 3
    assert records[0]["message"] == "msg 2"
    assert records[2]["message"] == "msg 4"

    logger.removeHandler(handler)


def test_handler_filters_by_level():
    handler = RingBufferHandler(capacity=100)
    logger = logging.getLogger("test.ringbuffer_filter")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    logger.debug("d")
    logger.info("i")
    logger.warning("w")
    logger.error("e")

    warning_up = handler.get_records(min_level="WARNING")
    assert [r["message"] for r in warning_up] == ["w", "e"]

    logger.removeHandler(handler)


def test_handler_filters_by_search_substring():
    handler = RingBufferHandler(capacity=100)
    logger = logging.getLogger("test.ringbuffer_search")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    logger.info("found needle in haystack")
    logger.info("just haystack")
    logger.info("also a needle")

    hits = handler.get_records(search="needle")
    assert len(hits) == 2

    logger.removeHandler(handler)


def test_handler_captures_exception_info():
    handler = RingBufferHandler(capacity=100)
    logger = logging.getLogger("test.ringbuffer_exc")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    try:
        raise ValueError("boom")
    except ValueError:
        logger.exception("failure")

    records = handler.get_records()
    assert len(records) == 1
    assert "ValueError" in records[0]["exception"]
    assert "boom" in records[0]["exception"]

    logger.removeHandler(handler)
```

- [ ] **Step 2: Run and verify failure**

```bash
uv run pytest tests/test_admin_log_handler.py -v
```

Expected: `ModuleNotFoundError: No module named 'flexloop.admin.log_handler'`.

- [ ] **Step 3: Implement log_handler.py**

Create `flexloop-server/src/flexloop/admin/log_handler.py`:

```python
"""In-memory ring buffer log handler for the admin Log Viewer.

Keeps the last N records in a deque for instant live-tail queries. A future
phase (5) will add a rotating JSONL file sink for longer history.
"""
import logging
import threading
import traceback
from collections import deque
from datetime import datetime
from typing import Any

LEVEL_RANK = {
    "DEBUG": 10,
    "INFO": 20,
    "WARNING": 30,
    "ERROR": 40,
    "CRITICAL": 50,
}


class RingBufferHandler(logging.Handler):
    """Stores the most recent log records in a bounded deque.

    Thread-safe. Records are dicts, not LogRecord objects, so they're safe to
    serialize to JSON directly.
    """

    def __init__(self, capacity: int = 10_000) -> None:
        super().__init__()
        self._buffer: deque[dict[str, Any]] = deque(maxlen=capacity)
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry: dict[str, Any] = {
                "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "exception": None,
            }
            if record.exc_info:
                entry["exception"] = "".join(traceback.format_exception(*record.exc_info))
            with self._lock:
                self._buffer.append(entry)
        except Exception:  # noqa: BLE001
            # Don't let a logging failure crash the app
            self.handleError(record)

    def get_records(
        self,
        min_level: str = "DEBUG",
        search: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        threshold = LEVEL_RANK.get(min_level.upper(), 0)
        with self._lock:
            snapshot = list(self._buffer)

        filtered = [
            r for r in snapshot
            if LEVEL_RANK.get(r["level"], 0) >= threshold
            and (search is None or search.lower() in r["message"].lower())
        ]
        if limit is not None:
            filtered = filtered[-limit:]
        return filtered

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()


# Process-wide singleton installed in main.py. Other modules import this
# directly (e.g., the health endpoint reads from it for recent_errors).
admin_ring_buffer = RingBufferHandler(capacity=10_000)
```

- [ ] **Step 4: Re-run tests**

```bash
uv run pytest tests/test_admin_log_handler.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Install the handler in main.py**

Edit `flexloop-server/src/flexloop/main.py`. The handler must be installed **above the `from flexloop.*` imports** — specifically, above `from flexloop.db.engine import init_db` and all the router imports — so that early-startup log records (model registration, DB init, router import side effects) flow into the ring buffer. Only stdlib imports may appear above it.

```python
# At the very top of main.py, above all flexloop imports:
import logging
from flexloop.admin.log_handler import admin_ring_buffer

# Attach to the root logger so everything flows through it
logging.getLogger().addHandler(admin_ring_buffer)
logging.getLogger().setLevel(logging.INFO)

# Then the rest of the existing imports...
from contextlib import asynccontextmanager
from fastapi import FastAPI
# ...
```

Note: because the handler is attached to the root logger, the singleton ring buffer will capture log records during `pytest` runs too (test logging propagates to root). That's fine — the tests in `test_admin_log_handler.py` use their own `RingBufferHandler` instance attached to a namespaced logger, not the singleton, so they're isolated.

- [ ] **Step 6: Smoke test the handler is installed**

Start the server briefly:

```bash
uv run uvicorn flexloop.main:app --host 127.0.0.1 --port 8001 &
SERVER_PID=$!
sleep 2
kill $SERVER_PID
```

Then in a Python REPL:

```python
# Not directly testable from a running server without an endpoint; verified
# later by the health endpoint which uses admin_ring_buffer.get_records().
```

(Skip this smoke test step for now — the health endpoint in Task 12 is the real verification.)

- [ ] **Step 7: Commit**

```bash
git add src/flexloop/admin/log_handler.py src/flexloop/main.py tests/test_admin_log_handler.py
git commit -m "feat(admin): RingBufferHandler + install in main.py"
```

---

### Task 12: Health router — /api/admin/health

**Files:**
- Create: `flexloop-server/src/flexloop/admin/routers/health.py`
- Create: `flexloop-server/tests/test_admin_health.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_admin_health.py`:

```python
import pytest


@pytest.fixture
async def logged_in_client(client):
    """Create an admin and log in. Returns a client with the session cookie set."""
    from flexloop.admin.bootstrap import create_admin_user
    from flexloop.models.admin_user import AdminUser
    from tests.conftest import test_session_factory

    async with test_session_factory() as db:
        await create_admin_user(db, "healthtester", "testpw12345")
        await db.commit()

    r = await client.post(
        "/api/admin/auth/login",
        json={"username": "healthtester", "password": "testpw12345"},
    )
    assert r.status_code == 200
    return client


async def test_health_requires_auth(client):
    r = await client.get("/api/admin/health")
    assert r.status_code == 401


async def test_health_returns_structured_payload(logged_in_client):
    r = await logged_in_client.get("/api/admin/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("healthy", "degraded", "down")
    assert "checked_at" in body
    assert "components" in body
    assert "database" in body["components"]
    assert body["components"]["database"]["status"] == "healthy"
    assert "ms" in body["components"]["database"]
    assert "table_row_counts" in body["components"]["database"]
    assert "system" in body
    assert "python" in body["system"]
    assert "recent_errors" in body
    assert isinstance(body["recent_errors"], list)
```

- [ ] **Step 2: Run and verify failure**

```bash
uv run pytest tests/test_admin_health.py -v
```

Expected: 404 — router not mounted.

- [ ] **Step 3: Implement health.py**

Create `flexloop-server/src/flexloop/admin/routers/health.py`:

```python
"""Admin health endpoint: /api/admin/health.

Runs a handful of quick checks (DB reachability, row counts, system info,
recent errors from the ring buffer) and returns a structured payload for
the dashboard health card and the dedicated health page.

Phase 1 scope: DB, system info, recent errors, table row counts. Later
phases will add AI provider check, disk/memory, backups, migrations status.
"""
import os
import platform
import sys
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import require_admin
from flexloop.admin.log_handler import admin_ring_buffer
from flexloop.db.engine import get_session

router = APIRouter(prefix="/api/admin", tags=["admin:health"])


_PROCESS_START = time.time()


# List of models to count rows for on the health page. Using model classes
# would require imports; plain table names are enough for row counts.
_COUNTABLE_TABLES = [
    "users",
    "plans",
    "plan_days",
    "workout_sessions",
    "workout_sets",
    "measurements",
    "personal_records",
    "exercises",
    "ai_usage",
    "admin_users",
    "admin_sessions",
]


async def _check_database(db: AsyncSession) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        await db.execute(text("SELECT 1"))
        ms = (time.perf_counter() - start) * 1000
    except Exception as e:  # noqa: BLE001
        return {"status": "down", "error": str(e), "ms": 0}

    row_counts: dict[str, int] = {}
    for tbl in _COUNTABLE_TABLES:
        try:
            result = await db.execute(text(f"SELECT COUNT(*) FROM {tbl}"))
            row_counts[tbl] = result.scalar_one()
        except Exception:  # noqa: BLE001
            # Table may not exist yet on a fresh DB — skip silently
            continue

    db_size_bytes = 0
    try:
        # Best-effort for SQLite; other DBs will fall through
        from flexloop.config import settings as app_settings
        url = app_settings.database_url
        if url.startswith("sqlite"):
            path = url.split(":///")[-1]
            if os.path.exists(path):
                db_size_bytes = os.path.getsize(path)
    except Exception:  # noqa: BLE001
        pass

    return {
        "status": "healthy",
        "ms": round(ms, 2),
        "db_size_bytes": db_size_bytes,
        "table_row_counts": row_counts,
    }


def _recent_errors(limit: int = 20) -> list[dict[str, Any]]:
    return admin_ring_buffer.get_records(min_level="WARNING", limit=limit)


def _system_info() -> dict[str, Any]:
    import fastapi
    import uvicorn

    return {
        "python": sys.version.split()[0],
        "fastapi": fastapi.__version__,
        "uvicorn": uvicorn.__version__,
        "os": f"{platform.system()} {platform.release()}",
        "hostname": platform.node(),
        "uptime_seconds": int(time.time() - _PROCESS_START),
    }


@router.get("/health")
async def admin_health(
    db: AsyncSession = Depends(get_session),
    _user=Depends(require_admin),
):
    database = await _check_database(db)
    recent_errors = _recent_errors()
    system = _system_info()

    status = "healthy" if database["status"] == "healthy" else "degraded"

    return {
        "status": status,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "components": {
            "database": database,
            # Phase 4 will add ai_provider component
            # Phase 5 will add disk, memory, backups, migrations
        },
        "recent_errors": recent_errors,
        "system": system,
    }
```

- [ ] **Step 4: Mount the router in main.py**

Edit `src/flexloop/main.py`, add import and include:

```python
from flexloop.admin.routers.health import router as admin_health_router
# ...
app.include_router(admin_health_router)
```

- [ ] **Step 5: Re-run tests**

```bash
uv run pytest tests/test_admin_health.py -v
```

Expected: both tests PASS.

- [ ] **Step 6: Run the full backend test suite to catch regressions**

```bash
uv run pytest -q
```

Expected: all tests pass (including the existing ~30 test files).

- [ ] **Step 7: Commit**

```bash
git add src/flexloop/admin/routers/health.py src/flexloop/main.py tests/test_admin_health.py
git commit -m "feat(admin): health router with DB, system info, recent errors"
```

---

## Chunk 4: Frontend — Project Scaffold, Auth, Routing

### Task 13: Initialize the Vite + React + TS + Tailwind project

**Files:**
- Create: `flexloop-server/admin-ui/` (entire directory tree)

- [ ] **Step 1: Scaffold with Vite**

```bash
cd flexloop-server
npm create vite@latest admin-ui -- --template react-ts
cd admin-ui
npm install
```

Expected: `admin-ui/` contains a working Vite + React + TypeScript starter.

- [ ] **Step 2: Install frontend dependencies**

```bash
npm install react-router-dom @tanstack/react-query react-hook-form zod @hookform/resolvers
npm install -D tailwindcss postcss autoprefixer @types/node
```

- [ ] **Step 3: Initialize Tailwind**

```bash
npx tailwindcss init -p
```

This creates `tailwind.config.ts` and `postcss.config.js`.

- [ ] **Step 4: Configure Tailwind content globs**

Edit `admin-ui/tailwind.config.ts`:

```ts
import type { Config } from "tailwindcss";

export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {},
  },
  plugins: [],
} satisfies Config;
```

- [ ] **Step 5: Add Tailwind directives to src/index.css**

Replace `admin-ui/src/index.css` with:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --background: 0 0% 100%;
    --foreground: 240 10% 3.9%;
    --card: 0 0% 100%;
    --card-foreground: 240 10% 3.9%;
    --popover: 0 0% 100%;
    --popover-foreground: 240 10% 3.9%;
    --primary: 240 5.9% 10%;
    --primary-foreground: 0 0% 98%;
    --secondary: 240 4.8% 95.9%;
    --secondary-foreground: 240 5.9% 10%;
    --muted: 240 4.8% 95.9%;
    --muted-foreground: 240 3.8% 46.1%;
    --accent: 240 4.8% 95.9%;
    --accent-foreground: 240 5.9% 10%;
    --destructive: 0 84.2% 60.2%;
    --destructive-foreground: 0 0% 98%;
    --border: 240 5.9% 90%;
    --input: 240 5.9% 90%;
    --ring: 240 5.9% 10%;
    --radius: 0.5rem;
  }

  .dark {
    --background: 240 10% 3.9%;
    --foreground: 0 0% 98%;
    --card: 240 10% 3.9%;
    --card-foreground: 0 0% 98%;
    --popover: 240 10% 3.9%;
    --popover-foreground: 0 0% 98%;
    --primary: 0 0% 98%;
    --primary-foreground: 240 5.9% 10%;
    --secondary: 240 3.7% 15.9%;
    --secondary-foreground: 0 0% 98%;
    --muted: 240 3.7% 15.9%;
    --muted-foreground: 240 5% 64.9%;
    --accent: 240 3.7% 15.9%;
    --accent-foreground: 0 0% 98%;
    --destructive: 0 62.8% 30.6%;
    --destructive-foreground: 0 0% 98%;
    --border: 240 3.7% 15.9%;
    --input: 240 3.7% 15.9%;
    --ring: 240 4.9% 83.9%;
  }
}

@layer base {
  * { @apply border-border; }
  body {
    @apply bg-background text-foreground;
    font-feature-settings: "rlig" 1, "calt" 1;
  }
}
```

- [ ] **Step 6: Configure Vite with API proxy and path alias**

Replace `admin-ui/vite.config.ts`:

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  base: "/admin/",  // app is served under /admin/ in production
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "../src/flexloop/static/admin",
    emptyOutDir: true,
  },
});
```

- [ ] **Step 7: Update tsconfig.json with the alias**

Edit `admin-ui/tsconfig.json` — add `baseUrl` and `paths` to `compilerOptions`:

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

Also install the node types if npm didn't pull them in:

```bash
npm install -D @types/node
```

- [ ] **Step 8: Add .gitignore for the admin-ui directory**

Create `admin-ui/.gitignore`:

```
node_modules
dist
*.local
.DS_Store
```

- [ ] **Step 9: Also gitignore the static output in the server .gitignore**

Edit (or create) `flexloop-server/.gitignore` to include:

```
src/flexloop/static/admin/
```

- [ ] **Step 10: Smoke test — npm run dev**

```bash
npm run dev
```

Expected: Vite starts on `http://localhost:5173/admin/`, you can open it in a browser and see the default Vite starter page. Press `q` then Enter (or Ctrl+C) to stop.

- [ ] **Step 11: Commit**

```bash
cd ..
git add admin-ui/
# Add the .gitignore for flexloop-server if you created it
git add .gitignore 2>/dev/null || true
git commit -m "feat(admin-ui): init Vite + React + TS + Tailwind project"
```

(Note: `src/flexloop/static/admin/` is gitignored, so don't `git add` it — the built bundle is regenerated on every deploy.)

---

### Task 14: Install and configure shadcn/ui

**Files:**
- Create: `admin-ui/components.json`
- Create: `admin-ui/src/lib/utils.ts`
- Create: Several files under `admin-ui/src/components/ui/`

- [ ] **Step 1: Init shadcn/ui**

```bash
cd flexloop-server/admin-ui
npx shadcn@latest init
```

Answer the prompts:
- Style: Default
- Base color: Slate
- CSS variables: Yes

This creates `components.json` and installs `class-variance-authority`, `clsx`, `tailwind-merge`, `lucide-react`.

- [ ] **Step 2: Install the core components we need for Phase 1**

```bash
npx shadcn@latest add button card input label form sheet dialog sonner separator avatar dropdown-menu sidebar
```

- [ ] **Step 3: Verify components landed in src/components/ui/**

```bash
ls src/components/ui/
```

Expected: `button.tsx`, `card.tsx`, `input.tsx`, `label.tsx`, `form.tsx`, `sheet.tsx`, `dialog.tsx`, `sonner.tsx`, `separator.tsx`, `avatar.tsx`, `dropdown-menu.tsx`, `sidebar.tsx` and their deps.

- [ ] **Step 4: Commit**

```bash
cd ..
git add admin-ui/
git commit -m "feat(admin-ui): add shadcn/ui components for phase 1"
```

---

### Task 15: API client, TanStack Query, and useAuth hook

**Files:**
- Create: `admin-ui/src/lib/api.ts`
- Create: `admin-ui/src/lib/query.ts`
- Create: `admin-ui/src/hooks/useAuth.ts`

- [ ] **Step 1: Create api.ts**

Create `flexloop-server/admin-ui/src/lib/api.ts`:

```ts
/**
 * Thin fetch wrapper for the admin API.
 *
 * In dev, Vite proxies /api → http://127.0.0.1:8000. In prod the SPA is
 * served same-origin from FastAPI so no base URL is needed. Cookies are
 * sent automatically via credentials: "include".
 */

export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(`${status}: ${detail}`);
  }
}

type RequestOptions = {
  method?: string;
  body?: unknown;
  params?: Record<string, string | number | undefined>;
};

async function apiFetch<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, params } = opts;
  let url = path.startsWith("/") ? path : `/${path}`;

  if (params) {
    const search = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined) search.set(k, String(v));
    }
    const qs = search.toString();
    if (qs) url += `?${qs}`;
  }

  const headers: Record<string, string> = {};
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  const res = await fetch(url, {
    method,
    headers,
    credentials: "include",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const err = await res.json();
      detail = typeof err.detail === "string" ? err.detail : detail;
    } catch {}
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string, params?: RequestOptions["params"]) =>
    apiFetch<T>(path, { params }),
  post: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, { method: "POST", body }),
  put: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, { method: "PUT", body }),
  delete: <T>(path: string) => apiFetch<T>(path, { method: "DELETE" }),
};
```

- [ ] **Step 2: Create query.ts**

Create `admin-ui/src/lib/query.ts`:

```ts
import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) => {
        // Don't retry on 401 — the AuthGate will redirect
        if (error instanceof Error && error.message.startsWith("401:")) return false;
        return failureCount < 2;
      },
      staleTime: 30_000,
      refetchOnWindowFocus: true,
    },
  },
});
```

- [ ] **Step 3: Create useAuth hook**

Create `admin-ui/src/hooks/useAuth.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";

export type MeResponse = {
  username: string;
  expires_at: string;
};

export type LoginResponse = {
  ok: boolean;
  username: string;
  expires_at: string;
};

const ME_KEY = ["admin", "auth", "me"] as const;

export function useMe() {
  return useQuery({
    queryKey: ME_KEY,
    queryFn: () => api.get<MeResponse>("/api/admin/auth/me"),
    retry: false,
    refetchOnMount: "always",
  });
}

export function useLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (creds: { username: string; password: string }) =>
      api.post<LoginResponse>("/api/admin/auth/login", creds),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ME_KEY });
    },
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post("/api/admin/auth/logout"),
    onSuccess: () => {
      qc.setQueryData(ME_KEY, null);
      qc.invalidateQueries({ queryKey: ME_KEY });
    },
  });
}

export function isAuthError(err: unknown): boolean {
  return err instanceof ApiError && err.status === 401;
}
```

- [ ] **Step 4: Commit**

```bash
cd ..
git add admin-ui/src/lib admin-ui/src/hooks
git commit -m "feat(admin-ui): api client, TanStack Query, useAuth hook"
```

---

### Task 16: Login page + AuthGate

**Files:**
- Create: `admin-ui/src/pages/LoginPage.tsx`
- Create: `admin-ui/src/components/AuthGate.tsx`

- [ ] **Step 1: Create LoginPage.tsx**

Create `admin-ui/src/pages/LoginPage.tsx`:

```tsx
import { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useLogin } from "@/hooks/useAuth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

export function LoginPage() {
  const login = useLogin();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const from = (location.state as { from?: string })?.from ?? "/";

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await login.mutateAsync({ username, password });
      navigate(from, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>FlexLoop Admin</CardTitle>
          <CardDescription>Sign in to continue</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="username">Username</Label>
              <Input
                id="username"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            {error && (
              <p className="text-sm text-destructive" role="alert">{error}</p>
            )}
            <Button type="submit" className="w-full" disabled={login.isPending}>
              {login.isPending ? "Signing in..." : "Sign in"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
```

- [ ] **Step 2: Create AuthGate.tsx**

Create `admin-ui/src/components/AuthGate.tsx`:

```tsx
import { Navigate, useLocation } from "react-router-dom";
import { useMe } from "@/hooks/useAuth";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const me = useMe();
  const location = useLocation();

  if (me.isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-muted-foreground">
        Loading...
      </div>
    );
  }

  if (me.isError) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }

  return <>{children}</>;
}
```

- [ ] **Step 3: Commit**

```bash
cd ..
git add admin-ui/src/pages/LoginPage.tsx admin-ui/src/components/AuthGate.tsx
git commit -m "feat(admin-ui): login page and AuthGate wrapper"
```

---

### Task 17: App shell with sidebar navigation

**Files:**
- Create: `admin-ui/src/components/AppShell.tsx`
- Create: `admin-ui/src/components/AppSidebar.tsx`

- [ ] **Step 1: Create AppSidebar.tsx**

Create `admin-ui/src/components/AppSidebar.tsx`:

```tsx
import { NavLink } from "react-router-dom";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import {
  LayoutDashboard,
  Users,
  ClipboardList,
  Dumbbell,
  Ruler,
  Trophy,
  Library,
  Settings,
  FileText,
  FlaskConical,
  BarChart3,
  HardDriveDownload,
  ScrollText,
  Wrench,
  Activity,
} from "lucide-react";

type Item = { label: string; to: string; icon: React.ComponentType<{ className?: string }>; disabled?: boolean };
type Group = { label?: string; items: Item[] };

// Phase 1 enables Dashboard and Health. Everything else is visible but disabled
// so the final IA is visible from day one.
const groups: Group[] = [
  {
    items: [
      { label: "Dashboard", to: "/", icon: LayoutDashboard },
      { label: "Health", to: "/health", icon: Activity },
    ],
  },
  {
    label: "User Data",
    items: [
      { label: "Users", to: "/users", icon: Users, disabled: true },
      { label: "Plans", to: "/plans", icon: ClipboardList, disabled: true },
      { label: "Workouts", to: "/workouts", icon: Dumbbell, disabled: true },
      { label: "Measurements", to: "/measurements", icon: Ruler, disabled: true },
      { label: "Personal Records", to: "/prs", icon: Trophy, disabled: true },
    ],
  },
  {
    label: "Catalog",
    items: [{ label: "Exercises", to: "/exercises", icon: Library, disabled: true }],
  },
  {
    label: "AI",
    items: [
      { label: "Config", to: "/ai/config", icon: Settings, disabled: true },
      { label: "Prompts", to: "/ai/prompts", icon: FileText, disabled: true },
      { label: "Playground", to: "/ai/playground", icon: FlaskConical, disabled: true },
      { label: "Usage", to: "/ai/usage", icon: BarChart3, disabled: true },
    ],
  },
  {
    label: "Operations",
    items: [
      { label: "Backup & Restore", to: "/ops/backup", icon: HardDriveDownload, disabled: true },
      { label: "Logs", to: "/ops/logs", icon: ScrollText, disabled: true },
      { label: "Triggers", to: "/ops/triggers", icon: Wrench, disabled: true },
    ],
  },
];

export function AppSidebar() {
  return (
    <Sidebar>
      <SidebarHeader>
        <div className="px-2 py-3 font-semibold">FlexLoop Admin</div>
      </SidebarHeader>
      <SidebarContent>
        {groups.map((group, gi) => (
          <SidebarGroup key={gi}>
            {group.label && <SidebarGroupLabel>{group.label}</SidebarGroupLabel>}
            <SidebarGroupContent>
              <SidebarMenu>
                {group.items.map((item) => (
                  <SidebarMenuItem key={item.to}>
                    <SidebarMenuButton asChild disabled={item.disabled}>
                      {item.disabled ? (
                        <span className="opacity-40 cursor-not-allowed flex items-center gap-2">
                          <item.icon className="h-4 w-4" />
                          {item.label}
                        </span>
                      ) : (
                        <NavLink
                          to={item.to}
                          end
                          className={({ isActive }) =>
                            isActive ? "font-medium" : ""
                          }
                        >
                          <item.icon className="h-4 w-4" />
                          {item.label}
                        </NavLink>
                      )}
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ))}
      </SidebarContent>
    </Sidebar>
  );
}
```

- [ ] **Step 2: Create AppShell.tsx**

Create `admin-ui/src/components/AppShell.tsx`:

```tsx
import { Outlet, useNavigate } from "react-router-dom";
import {
  SidebarProvider,
  SidebarInset,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { AppSidebar } from "./AppSidebar";
import { useMe, useLogout } from "@/hooks/useAuth";
import { Separator } from "@/components/ui/separator";

export function AppShell() {
  const me = useMe();
  const logout = useLogout();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout.mutateAsync();
    navigate("/login", { replace: true });
  };

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <header className="flex h-14 items-center gap-2 border-b px-4">
          <SidebarTrigger />
          <Separator orientation="vertical" className="h-4" />
          <div className="ml-auto">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button className="flex items-center gap-2 rounded-md p-1 hover:bg-accent">
                  <Avatar className="h-7 w-7">
                    <AvatarFallback>
                      {me.data?.username.slice(0, 2).toUpperCase() ?? "?"}
                    </AvatarFallback>
                  </Avatar>
                  <span className="text-sm">{me.data?.username ?? ""}</span>
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onSelect={() => navigate("/account/password")}>
                  Change password
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => navigate("/account/sessions")}>
                  Active sessions
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onSelect={handleLogout}>
                  Sign out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>
        <main className="flex-1 p-6">
          <Outlet />
        </main>
      </SidebarInset>
    </SidebarProvider>
  );
}
```

- [ ] **Step 3: Commit**

```bash
cd ..
git add admin-ui/src/components/AppShell.tsx admin-ui/src/components/AppSidebar.tsx
git commit -m "feat(admin-ui): app shell with sidebar and user menu"
```

---

## Chunk 5: Frontend — Dashboard, Health, Account Pages, Integration

### Task 18: Dashboard landing page (health-first)

**Files:**
- Create: `admin-ui/src/hooks/useHealth.ts`
- Create: `admin-ui/src/pages/DashboardPage.tsx`

- [ ] **Step 1: Create useHealth hook**

Create `admin-ui/src/hooks/useHealth.ts`:

```ts
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export type HealthComponentDB = {
  status: "healthy" | "degraded" | "down";
  ms?: number;
  db_size_bytes?: number;
  table_row_counts?: Record<string, number>;
  error?: string;
};

export type HealthResponse = {
  status: "healthy" | "degraded" | "down";
  checked_at: string;
  components: {
    database: HealthComponentDB;
  };
  recent_errors: Array<{
    timestamp: string;
    level: string;
    logger: string;
    message: string;
    exception: string | null;
  }>;
  system: {
    python: string;
    fastapi: string;
    uvicorn: string;
    os: string;
    hostname: string;
    uptime_seconds: number;
  };
};

export function useHealth() {
  return useQuery({
    queryKey: ["admin", "health"],
    queryFn: () => api.get<HealthResponse>("/api/admin/health"),
    refetchInterval: 30_000,
    staleTime: 20_000,
  });
}
```

- [ ] **Step 2: Create DashboardPage.tsx**

Create `admin-ui/src/pages/DashboardPage.tsx`:

```tsx
import { useHealth } from "@/hooks/useHealth";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

function formatBytes(bytes: number | undefined): string {
  if (!bytes) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  let n = bytes;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i++;
  }
  return `${n.toFixed(n >= 10 ? 0 : 1)} ${units[i]}`;
}

function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

export function DashboardPage() {
  const health = useHealth();

  if (health.isLoading) {
    return <div className="text-muted-foreground">Loading...</div>;
  }
  if (health.isError || !health.data) {
    return <div className="text-destructive">Failed to load health data.</div>;
  }

  const h = health.data;
  const statusColor =
    h.status === "healthy"
      ? "text-green-500"
      : h.status === "degraded"
      ? "text-yellow-500"
      : "text-red-500";

  const rowCounts = h.components.database.table_row_counts ?? {};

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Dashboard</h1>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle>
            <span className={`${statusColor} mr-2`}>●</span>
            System {h.status}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div>
              <div className="text-muted-foreground text-xs uppercase">Uptime</div>
              <div className="font-medium">{formatUptime(h.system.uptime_seconds)}</div>
            </div>
            <div>
              <div className="text-muted-foreground text-xs uppercase">DB size</div>
              <div className="font-medium">
                {formatBytes(h.components.database.db_size_bytes)}
              </div>
            </div>
            <div>
              <div className="text-muted-foreground text-xs uppercase">Recent errors</div>
              <div className="font-medium">{h.recent_errors.length}</div>
            </div>
            <div>
              <div className="text-muted-foreground text-xs uppercase">Python</div>
              <div className="font-medium">{h.system.python}</div>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Users" value={rowCounts.users ?? 0} />
        <StatCard label="Workouts" value={rowCounts.workout_sessions ?? 0} />
        <StatCard label="Plans" value={rowCounts.plans ?? 0} />
        <StatCard label="Exercises" value={rowCounts.exercises ?? 0} />
      </div>

      {h.recent_errors.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Recent errors</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2 text-sm">
              {h.recent_errors.slice(0, 5).map((e, i) => (
                <li key={i} className="flex gap-3">
                  <span className="text-muted-foreground">{e.timestamp.slice(11, 19)}</span>
                  <span className="font-medium uppercase">{e.level}</span>
                  <span className="truncate">{e.message}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="text-muted-foreground text-xs uppercase">{label}</div>
        <div className="text-2xl font-semibold">{value}</div>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 3: Commit**

```bash
cd ..
git add admin-ui/src/hooks/useHealth.ts admin-ui/src/pages/DashboardPage.tsx
git commit -m "feat(admin-ui): dashboard landing page (health-first)"
```

---

### Task 19: Health detail page

**Files:**
- Create: `admin-ui/src/pages/HealthPage.tsx`

- [ ] **Step 1: Create HealthPage.tsx**

Create `admin-ui/src/pages/HealthPage.tsx`:

```tsx
import { useHealth } from "@/hooks/useHealth";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useQueryClient } from "@tanstack/react-query";

export function HealthPage() {
  const health = useHealth();
  const qc = useQueryClient();

  const refresh = () => qc.invalidateQueries({ queryKey: ["admin", "health"] });

  if (health.isLoading) return <div>Loading...</div>;
  if (health.isError || !health.data)
    return <div className="text-destructive">Failed to load health data.</div>;

  const h = health.data;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Health</h1>
        <Button onClick={refresh} variant="outline" size="sm">
          Re-check now
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Database</CardTitle>
        </CardHeader>
        <CardContent>
          <KV label="Status" value={h.components.database.status} />
          <KV label="Query latency" value={`${h.components.database.ms ?? 0} ms`} />
          <KV
            label="Size"
            value={`${((h.components.database.db_size_bytes ?? 0) / 1024).toFixed(1)} KB`}
          />
          <div className="mt-3">
            <div className="text-xs uppercase text-muted-foreground mb-1">Table row counts</div>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-sm">
              {Object.entries(h.components.database.table_row_counts ?? {}).map(([k, v]) => (
                <div key={k} className="flex justify-between border-b py-1">
                  <span className="text-muted-foreground">{k}</span>
                  <span>{v}</span>
                </div>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>System</CardTitle>
        </CardHeader>
        <CardContent>
          <KV label="Python" value={h.system.python} />
          <KV label="FastAPI" value={h.system.fastapi} />
          <KV label="Uvicorn" value={h.system.uvicorn} />
          <KV label="OS" value={h.system.os} />
          <KV label="Hostname" value={h.system.hostname} />
          <KV label="Uptime" value={`${h.system.uptime_seconds} s`} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Recent errors ({h.recent_errors.length})</CardTitle>
        </CardHeader>
        <CardContent>
          {h.recent_errors.length === 0 && (
            <div className="text-sm text-muted-foreground">None.</div>
          )}
          <ul className="space-y-3 text-sm">
            {h.recent_errors.map((e, i) => (
              <li key={i} className="border-l-2 border-destructive pl-3">
                <div className="font-mono text-xs text-muted-foreground">
                  {e.timestamp} · {e.level} · {e.logger}
                </div>
                <div>{e.message}</div>
                {e.exception && (
                  <pre className="mt-1 text-xs overflow-x-auto bg-muted p-2 rounded">
                    {e.exception}
                  </pre>
                )}
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}

function KV({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between border-b py-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
cd ..
git add admin-ui/src/pages/HealthPage.tsx
git commit -m "feat(admin-ui): health detail page"
```

---

### Task 20: Change password and sessions pages

**Files:**
- Create: `admin-ui/src/pages/ChangePasswordPage.tsx`
- Create: `admin-ui/src/pages/SessionsPage.tsx`
- Create: `admin-ui/src/hooks/useSessions.ts`

- [ ] **Step 1: Create useSessions hook**

Create `admin-ui/src/hooks/useSessions.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

export type SessionInfo = {
  id: string;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  user_agent: string | null;
  ip_address: string | null;
  is_current: boolean;
};

const KEY = ["admin", "auth", "sessions"] as const;

export function useSessions() {
  return useQuery({
    queryKey: KEY,
    queryFn: () => api.get<SessionInfo[]>("/api/admin/auth/sessions"),
  });
}

export function useRevokeSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/admin/auth/sessions/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}
```

- [ ] **Step 2: Create ChangePasswordPage.tsx**

Create `admin-ui/src/pages/ChangePasswordPage.tsx`:

```tsx
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function ChangePasswordPage() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  const change = useMutation({
    mutationFn: (vars: { current_password: string; new_password: string }) =>
      api.post("/api/admin/auth/change-password", vars),
    onSuccess: () => {
      setMsg("Password changed successfully.");
      setCurrent("");
      setNext("");
      setConfirm("");
    },
    onError: (e: Error) => setMsg(e.message),
  });

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setMsg(null);
    if (next !== confirm) {
      setMsg("New password and confirmation do not match.");
      return;
    }
    if (next.length < 8) {
      setMsg("New password must be at least 8 characters.");
      return;
    }
    change.mutate({ current_password: current, new_password: next });
  };

  return (
    <div className="max-w-md space-y-6">
      <h1 className="text-2xl font-semibold">Change password</h1>
      <Card>
        <CardHeader>
          <CardTitle>Update your password</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="current">Current password</Label>
              <Input
                id="current"
                type="password"
                value={current}
                onChange={(e) => setCurrent(e.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="new">New password</Label>
              <Input
                id="new"
                type="password"
                value={next}
                onChange={(e) => setNext(e.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="confirm">Confirm new password</Label>
              <Input
                id="confirm"
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                required
              />
            </div>
            {msg && <p className="text-sm">{msg}</p>}
            <Button type="submit" disabled={change.isPending}>
              {change.isPending ? "Updating..." : "Update password"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
```

- [ ] **Step 3: Create SessionsPage.tsx**

Create `admin-ui/src/pages/SessionsPage.tsx`:

```tsx
import { useSessions, useRevokeSession } from "@/hooks/useSessions";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function SessionsPage() {
  const sessions = useSessions();
  const revoke = useRevokeSession();

  if (sessions.isLoading) return <div>Loading...</div>;
  if (sessions.isError || !sessions.data) return <div>Failed to load sessions.</div>;

  return (
    <div className="max-w-2xl space-y-6">
      <h1 className="text-2xl font-semibold">Active sessions</h1>
      <Card>
        <CardHeader>
          <CardTitle>Your sessions ({sessions.data.length})</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="divide-y">
            {sessions.data.map((s) => (
              <li key={s.id} className="py-3 flex items-center justify-between">
                <div className="text-sm">
                  <div className="font-medium">
                    {s.user_agent ?? "Unknown client"}
                    {s.is_current && (
                      <span className="ml-2 text-xs text-green-500">(current)</span>
                    )}
                  </div>
                  <div className="text-muted-foreground text-xs">
                    {s.ip_address ?? "unknown IP"} · created{" "}
                    {new Date(s.created_at).toLocaleString()} · expires{" "}
                    {new Date(s.expires_at).toLocaleString()}
                  </div>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={revoke.isPending}
                  onClick={() => revoke.mutate(s.id)}
                >
                  Revoke
                </Button>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
```

- [ ] **Step 4: Commit**

```bash
cd ..
git add admin-ui/src/hooks/useSessions.ts \
        admin-ui/src/pages/ChangePasswordPage.tsx \
        admin-ui/src/pages/SessionsPage.tsx
git commit -m "feat(admin-ui): change password and active sessions pages"
```

---

### Task 21: Wire up routing in App.tsx and main.tsx

**Files:**
- Modify: `admin-ui/src/App.tsx`
- Modify: `admin-ui/src/main.tsx`

- [ ] **Step 1: Replace App.tsx**

Replace `admin-ui/src/App.tsx`:

```tsx
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient } from "@/lib/query";
import { Toaster } from "@/components/ui/sonner";

import { AuthGate } from "@/components/AuthGate";
import { AppShell } from "@/components/AppShell";
import { LoginPage } from "@/pages/LoginPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { HealthPage } from "@/pages/HealthPage";
import { ChangePasswordPage } from "@/pages/ChangePasswordPage";
import { SessionsPage } from "@/pages/SessionsPage";

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter basename="/admin">
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/"
            element={
              <AuthGate>
                <AppShell />
              </AuthGate>
            }
          >
            <Route index element={<DashboardPage />} />
            <Route path="health" element={<HealthPage />} />
            <Route path="account/password" element={<ChangePasswordPage />} />
            <Route path="account/sessions" element={<SessionsPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
      <Toaster />
    </QueryClientProvider>
  );
}
```

- [ ] **Step 2: Replace main.tsx**

Replace `admin-ui/src/main.tsx`:

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import "./index.css";

// Apply dark mode by default (the admin tool is utilitarian; see spec §12.1)
document.documentElement.classList.add("dark");

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

- [ ] **Step 3: Verify the app builds cleanly**

```bash
cd admin-ui
npm run build
```

Expected: bundle is written to `../src/flexloop/static/admin/` with no TypeScript errors. The final line looks like "built in N.Ns".

- [ ] **Step 4: Commit**

```bash
cd ..
git add admin-ui/src/App.tsx admin-ui/src/main.tsx
git commit -m "feat(admin-ui): wire up routing with AuthGate and AppShell"
```

---

### Task 22: Mount the static SPA bundle in main.py with SPA fallback

**Files:**
- Modify: `flexloop-server/src/flexloop/main.py`

- [ ] **Step 1: Add static file mount + SPA fallback**

Edit `flexloop-server/src/flexloop/main.py`. Add this near the bottom, after all routers are included:

```python
from pathlib import Path
from fastapi import HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Mount the built admin SPA bundle at /admin/*.
# In dev, you'd run `npm run dev` separately and the Vite dev server proxies
# to this FastAPI process. In prod, the bundle is prebuilt into static/admin.
_STATIC_ADMIN = Path(__file__).parent / "static" / "admin"
_ADMIN_INDEX = _STATIC_ADMIN / "index.html"

if _STATIC_ADMIN.exists():
    # Serve built assets (JS, CSS, images) at /admin/assets/...
    app.mount(
        "/admin/assets",
        StaticFiles(directory=_STATIC_ADMIN / "assets"),
        name="admin_assets",
    )

    @app.get("/admin")
    async def admin_root():
        if not _ADMIN_INDEX.exists():
            raise HTTPException(status_code=404, detail="admin UI not built")
        return FileResponse(_ADMIN_INDEX)

    @app.get("/admin/{path:path}")
    async def admin_spa_fallback(path: str):
        """Serve index.html for any /admin/* path (SPA client-side routing).

        This must come AFTER /admin/assets mount so asset URLs don't get
        caught by the fallback. FastAPI evaluates mounts before route
        handlers, so the ordering is fine either way in practice.
        """
        if not _ADMIN_INDEX.exists():
            raise HTTPException(status_code=404, detail="admin UI not built")
        return FileResponse(_ADMIN_INDEX)
```

Make sure the imports `Path`, `HTTPException`, `FileResponse`, `StaticFiles` are present — add them to the imports block at the top of main.py if not (FastAPI's `HTTPException` may already be imported).

- [ ] **Step 2: Rebuild the SPA and start the server**

```bash
cd admin-ui
npm run build
cd ..
uv run uvicorn flexloop.main:app --reload --port 8000
```

- [ ] **Step 3: Manual smoke test the SPA is served**

In a browser, open `http://localhost:8000/admin`. Expected: the login page appears. Try logging in with the credentials you created via the bootstrap CLI earlier. If you haven't created an admin yet, stop the server and run:

```bash
uv run python -m flexloop.admin.bootstrap create-admin smoketester
# enter password twice
```

Then restart the server and log in. You should see the Dashboard with DB/system info.

- [ ] **Step 4: Verify the sidebar nav works**

Click "Health" in the sidebar. The health detail page should load. Click the user avatar in the top right → "Change password" and "Active sessions" — both pages should render. Click "Sign out"; you should be redirected to `/admin/login`.

- [ ] **Step 5: Verify the iOS-facing API still works (regression check)**

While the server is still running:

```bash
curl -s http://localhost:8000/api/health
```

Expected: `{"status":"ok","version":"1.0.0"}`.

- [ ] **Step 6: Commit**

```bash
git add src/flexloop/main.py
git commit -m "feat(admin): mount SPA static bundle at /admin with SPA fallback"
```

---

### Task 23: Final regression test + Phase 1 completion

- [ ] **Step 1: Run the full backend test suite**

```bash
cd flexloop-server
uv run pytest
```

Expected: all tests pass (existing tests + new `test_admin_auth.py`, `test_admin_health.py`, `test_admin_log_handler.py`).

- [ ] **Step 2: Rebuild the frontend one final time**

```bash
cd admin-ui
npm run build
cd ..
```

Expected: clean build with no errors. Check the build output size — `dist/` should be reasonable (under 1 MB gzipped).

- [ ] **Step 3: Verify acceptance criteria from spec §17 (Phase 1 scope only)**

Manually check:
- [ ] `cd flexloop-server && uv sync && cd admin-ui && npm ci && npm run build` works end-to-end on a fresh clone
- [ ] `uv run python -m flexloop.admin.bootstrap create-admin <username>` creates a user
- [ ] Starting `uv run uvicorn flexloop.main:app --port 8000` and visiting `http://localhost:8000/admin` shows the login page
- [ ] Login works with the credentials created via bootstrap
- [ ] Dashboard page shows health summary + row count stats
- [ ] Health page shows DB info, system info, and recent errors section
- [ ] Change password works end-to-end (old password no longer valid after change)
- [ ] Active sessions shows the current session and allows revoking (revocation logs out)
- [ ] iOS API `/api/health` still returns 200
- [ ] Existing routes (e.g., `/api/users/{id}`) still work

- [ ] **Step 4: Final commit marking Phase 1 complete**

```bash
git add -A
git commit --allow-empty -m "milestone: admin dashboard phase 1 (foundation) complete

Phase 1 deliverables:
- 5 new DB tables (admin_users, admin_sessions, admin_audit_log,
  app_settings, model_pricing) with alembic migration
- Admin package skeleton with auth module, bootstrap CLI, CSRF
  middleware, and ring-buffer log handler
- Auth router: /login, /logout, /me, /change-password, /sessions
- Health router with DB + system + recent errors
- React SPA shell: login page, AuthGate, sidebar nav, user menu,
  Dashboard (health-first), Health detail, Change password, Sessions
- Same-origin deploy via static mount at /admin/* with SPA fallback

Next: Phase 2 (boring CRUD pages) — separate plan."
```

- [ ] **Step 5: Stop here and hand off**

Phase 1 is done. Phase 2 (boring CRUD) needs its own plan file. Do NOT start Phase 2 from this plan.

---

## Summary

**What this plan delivers:** A working, deployable admin dashboard skeleton. You can log in, see system health, change your password, and revoke sessions. Every other sidebar item is visible but disabled — users can see the roadmap.

**What this plan deliberately does NOT deliver:**
- Data CRUD pages (Phase 2)
- Plan editor (Phase 3)
- AI tools — config, prompts, playground, usage (Phase 4)
- Operations — backup, logs, triggers (Phase 5)

**When you're ready for Phase 2**, ask me to write its plan. Phase 2 will introduce the shared `useList/useCreate/...` hooks, the generic CRUD helpers on the backend, and the first six "boring" resource pages.
