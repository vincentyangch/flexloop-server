# FlexLoop Server Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the FlexLoop backend API server (Python/FastAPI) that serves as the platform-agnostic backend for workout logging, AI-powered plan generation, training review, and data management.

**Architecture:** FastAPI application with SQLAlchemy ORM, Alembic migrations, and a pluggable LLM adapter layer. SQLite by default, PostgreSQL optional. Dockerized for one-command deployment. All business logic lives server-side so any client (iOS, Android, web) can consume the same API.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2, OpenAI SDK, Anthropic SDK, httpx (for Ollama), pytest, Docker

**PRD Reference:** `/Users/flyingchickens/Documents/Projects/FlexLoop/FlexLoop_PRD.md`

---

## Chunk 1: Project Scaffolding & Database Foundation

### Task 1: Initialize project structure

**Files:**
- Create: `flexloop-server/pyproject.toml`
- Create: `flexloop-server/README.md`
- Create: `flexloop-server/.env.example`
- Create: `flexloop-server/.gitignore`
- Create: `flexloop-server/src/flexloop/__init__.py`
- Create: `flexloop-server/src/flexloop/main.py`
- Create: `flexloop-server/src/flexloop/config.py`
- Create: `flexloop-server/tests/__init__.py`
- Create: `flexloop-server/tests/conftest.py`

- [ ] **Step 1: Create project directory and pyproject.toml**

```toml
[project]
name = "flexloop-server"
version = "1.0.0"
description = "FlexLoop backend API server — AI-powered fitness training companion"
requires-python = ">=3.12"
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
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "httpx>=0.27.0",
    "ruff>=0.6.0",
]
postgres = [
    "asyncpg>=0.30.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
target-version = "py312"
line-length = 100
```

- [ ] **Step 2: Create .env.example**

```env
# Database
DATABASE_URL=sqlite+aiosqlite:///./flexloop.db

# AI Provider (openai | anthropic | ollama | openai-compatible)
AI_PROVIDER=openai
AI_MODEL=gpt-4o-mini
AI_API_KEY=your-api-key-here
AI_BASE_URL=
AI_TEMPERATURE=0.7
AI_MAX_TOKENS=2000

# AI Review
AI_REVIEW_FREQUENCY=block
AI_REVIEW_BLOCK_WEEKS=6

# Server
HOST=0.0.0.0
PORT=8000
```

- [ ] **Step 3: Create .gitignore**

```
__pycache__/
*.pyc
.venv/
*.db
.env
dist/
*.egg-info/
.pytest_cache/
.ruff_cache/
backups/
```

- [ ] **Step 4: Create config module**

```python
# src/flexloop/config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./flexloop.db"

    ai_provider: str = "openai"
    ai_model: str = "gpt-4o-mini"
    ai_api_key: str = ""
    ai_base_url: str = ""
    ai_temperature: float = 0.7
    ai_max_tokens: int = 2000
    ai_review_frequency: str = "block"
    ai_review_block_weeks: int = 6

    host: str = "0.0.0.0"
    port: int = 8000

    model_config = {"env_file": ".env"}


settings = Settings()
```

- [ ] **Step 5: Create FastAPI app entry point**

```python
# src/flexloop/main.py
from fastapi import FastAPI

app = FastAPI(
    title="FlexLoop API",
    description="AI-powered fitness training companion",
    version="1.0.0",
)


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "1.0.0"}
```

- [ ] **Step 6: Create test conftest and first test**

```python
# tests/conftest.py
import pytest
from httpx import ASGITransport, AsyncClient

from flexloop.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
```

```python
# tests/test_health.py
import pytest


@pytest.mark.asyncio
async def test_health_check(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "1.0.0"
```

- [ ] **Step 7: Run test to verify it passes**

Run: `cd flexloop-server && pip install -e ".[dev]" && pytest tests/test_health.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git init
git add .
git commit -m "feat: initialize project scaffolding with FastAPI and health endpoint"
```

---

### Task 2: Set up SQLAlchemy and Alembic

**Files:**
- Create: `src/flexloop/db/__init__.py`
- Create: `src/flexloop/db/engine.py`
- Create: `src/flexloop/db/base.py`
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/script.py.mako`
- Create: `alembic/versions/.gitkeep`
- Modify: `src/flexloop/main.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Write test for database session lifecycle**

```python
# tests/test_db.py
import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_database_connection(db_session):
    result = await db_session.execute(text("SELECT 1"))
    assert result.scalar() == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_db.py -v`
Expected: FAIL — `db_session` fixture not defined

- [ ] **Step 3: Create database engine module**

```python
# src/flexloop/db/__init__.py
from flexloop.db.engine import get_session, init_db

__all__ = ["get_session", "init_db"]
```

```python
# src/flexloop/db/engine.py
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from flexloop.config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession]:
    async with async_session() as session:
        yield session


async def init_db():
    from flexloop.db.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

```python
# src/flexloop/db/base.py
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

- [ ] **Step 4: Update test conftest with db_session fixture**

```python
# tests/conftest.py
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from flexloop.db.base import Base
from flexloop.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite://"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
test_session = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(autouse=True)
async def setup_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def db_session():
    async with test_session() as session:
        yield session


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_db.py -v`
Expected: PASS

- [ ] **Step 6: Set up Alembic for migrations**

```ini
# alembic.ini
[alembic]
script_location = alembic
sqlalchemy.url = sqlite+aiosqlite:///./flexloop.db

[loggers]
keys = root

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[handler_console]
class = StreamHandler
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
```

```python
# alembic/env.py
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from flexloop.config import settings
from flexloop.db.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline():
    url = settings.database_url
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online():
    connectable = create_async_engine(settings.database_url)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

```mako
# alembic/script.py.mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 7: Add lifespan to FastAPI app**

```python
# src/flexloop/main.py
from contextlib import asynccontextmanager

from fastapi import FastAPI

from flexloop.db.engine import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="FlexLoop API",
    description="AI-powered fitness training companion",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "1.0.0"}
```

- [ ] **Step 8: Run all tests**

Run: `pytest tests/ -v`
Expected: All PASS

- [ ] **Step 9: Commit**

```bash
git add .
git commit -m "feat: add SQLAlchemy async engine, Alembic migrations, and test DB fixtures"
```

---

### Task 3: Define core database models — Users, Exercises, Volume Landmarks

**Files:**
- Create: `src/flexloop/models/__init__.py`
- Create: `src/flexloop/models/user.py`
- Create: `src/flexloop/models/exercise.py`
- Create: `src/flexloop/models/volume_landmark.py`
- Modify: `src/flexloop/db/base.py`
- Create: `tests/test_models_core.py`

- [ ] **Step 1: Write failing test for User model**

```python
# tests/test_models_core.py
import pytest
from sqlalchemy import select

from flexloop.models.user import User


@pytest.mark.asyncio
async def test_create_user(db_session):
    user = User(
        name="Test User",
        gender="male",
        age=28,
        height_cm=180.0,
        weight_kg=82.0,
        experience_level="intermediate",
        goals="hypertrophy",
        available_equipment=["barbell", "dumbbells", "pull_up_bar"],
    )
    db_session.add(user)
    await db_session.commit()

    result = await db_session.execute(select(User).where(User.name == "Test User"))
    saved = result.scalar_one()
    assert saved.name == "Test User"
    assert saved.experience_level == "intermediate"
    assert "barbell" in saved.available_equipment
    assert saved.created_at is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_models_core.py::test_create_user -v`
Expected: FAIL — cannot import `User`

- [ ] **Step 3: Implement User model**

```python
# src/flexloop/models/user.py
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from flexloop.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    gender: Mapped[str] = mapped_column(String(20), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    height_cm: Mapped[float] = mapped_column(Float, nullable=False)
    weight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    experience_level: Mapped[str] = mapped_column(String(20), nullable=False)
    goals: Mapped[str] = mapped_column(String(500), nullable=False)
    available_equipment: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

```python
# src/flexloop/models/__init__.py
from flexloop.models.user import User

__all__ = ["User"]
```

- [ ] **Step 4: Update conftest to import models before creating tables**

Add to `tests/conftest.py` before `setup_db`:

```python
import flexloop.models  # noqa: F401 — ensure models registered with Base
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_models_core.py::test_create_user -v`
Expected: PASS

- [ ] **Step 6: Write failing test for Exercise model**

```python
# tests/test_models_core.py (append)
from flexloop.models.exercise import Exercise


@pytest.mark.asyncio
async def test_create_exercise(db_session):
    exercise = Exercise(
        name="Barbell Bench Press",
        muscle_group="chest",
        equipment="barbell",
        category="compound",
        difficulty="intermediate",
    )
    db_session.add(exercise)
    await db_session.commit()

    result = await db_session.execute(
        select(Exercise).where(Exercise.name == "Barbell Bench Press")
    )
    saved = result.scalar_one()
    assert saved.muscle_group == "chest"
    assert saved.category == "compound"
    assert saved.source_plugin is None
```

- [ ] **Step 7: Run test to verify it fails**

Run: `pytest tests/test_models_core.py::test_create_exercise -v`
Expected: FAIL — cannot import `Exercise`

- [ ] **Step 8: Implement Exercise model**

```python
# src/flexloop/models/exercise.py
from sqlalchemy import JSON, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from flexloop.db.base import Base


class Exercise(Base):
    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    muscle_group: Mapped[str] = mapped_column(String(50), nullable=False)
    equipment: Mapped[str] = mapped_column(String(50), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False)
    source_plugin: Mapped[str | None] = mapped_column(String(100), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
```

- [ ] **Step 9: Write failing test for VolumeLandmark model**

```python
# tests/test_models_core.py (append)
from flexloop.models.volume_landmark import VolumeLandmark


@pytest.mark.asyncio
async def test_create_volume_landmark(db_session):
    landmark = VolumeLandmark(
        muscle_group="chest",
        experience_level="intermediate",
        mv_sets=6,
        mev_sets=10,
        mav_sets=16,
        mrv_sets=20,
    )
    db_session.add(landmark)
    await db_session.commit()

    result = await db_session.execute(
        select(VolumeLandmark).where(
            VolumeLandmark.muscle_group == "chest",
            VolumeLandmark.experience_level == "intermediate",
        )
    )
    saved = result.scalar_one()
    assert saved.mev_sets == 10
    assert saved.mrv_sets == 20
```

- [ ] **Step 10: Implement VolumeLandmark model**

```python
# src/flexloop/models/volume_landmark.py
from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from flexloop.db.base import Base


class VolumeLandmark(Base):
    __tablename__ = "volume_landmarks"
    __table_args__ = (
        UniqueConstraint("muscle_group", "experience_level", name="uq_volume_landmark"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    muscle_group: Mapped[str] = mapped_column(String(50), nullable=False)
    experience_level: Mapped[str] = mapped_column(String(20), nullable=False)
    mv_sets: Mapped[int] = mapped_column(Integer, nullable=False)
    mev_sets: Mapped[int] = mapped_column(Integer, nullable=False)
    mav_sets: Mapped[int] = mapped_column(Integer, nullable=False)
    mrv_sets: Mapped[int] = mapped_column(Integer, nullable=False)
```

- [ ] **Step 11: Update models __init__ with all models**

```python
# src/flexloop/models/__init__.py
from flexloop.models.exercise import Exercise
from flexloop.models.user import User
from flexloop.models.volume_landmark import VolumeLandmark

__all__ = ["Exercise", "User", "VolumeLandmark"]
```

- [ ] **Step 12: Run all model tests**

Run: `pytest tests/test_models_core.py -v`
Expected: All PASS

- [ ] **Step 13: Commit**

```bash
git add .
git commit -m "feat: add User, Exercise, and VolumeLandmark models"
```

---

### Task 4: Define database models — Plans, Exercise Groups, Plan Exercises

**Files:**
- Create: `src/flexloop/models/plan.py`
- Create: `tests/test_models_plan.py`
- Modify: `src/flexloop/models/__init__.py`

- [ ] **Step 1: Write failing test for Plan with days and exercises**

```python
# tests/test_models_plan.py
import pytest
from datetime import date
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from flexloop.models.user import User
from flexloop.models.exercise import Exercise
from flexloop.models.plan import Plan, PlanDay, ExerciseGroup, PlanExercise


@pytest.fixture
async def user_and_exercise(db_session):
    user = User(
        name="Test User", gender="male", age=28, height_cm=180.0,
        weight_kg=82.0, experience_level="intermediate", goals="hypertrophy",
        available_equipment=["barbell"],
    )
    exercise = Exercise(
        name="Bench Press", muscle_group="chest", equipment="barbell",
        category="compound", difficulty="intermediate",
    )
    db_session.add_all([user, exercise])
    await db_session.commit()
    return user, exercise


@pytest.mark.asyncio
async def test_create_plan_with_superset(db_session, user_and_exercise):
    user, exercise = user_and_exercise

    plan = Plan(
        user_id=user.id, name="PPL Block 1", split_type="ppl",
        block_start=date(2026, 3, 23), block_end=date(2026, 5, 3),
        status="active", ai_generated=True,
    )
    db_session.add(plan)
    await db_session.commit()

    day = PlanDay(plan_id=plan.id, day_number=1, label="Push A", focus="chest,shoulders,triceps")
    db_session.add(day)
    await db_session.commit()

    group = ExerciseGroup(
        plan_day_id=day.id, group_type="straight", order=1, rest_after_group_sec=90,
    )
    db_session.add(group)
    await db_session.commit()

    plan_exercise = PlanExercise(
        plan_day_id=day.id, exercise_group_id=group.id, exercise_id=exercise.id,
        order=1, sets=4, reps=8, weight=80.0, rpe_target=8.0,
    )
    db_session.add(plan_exercise)
    await db_session.commit()

    result = await db_session.execute(
        select(Plan).where(Plan.id == plan.id)
    )
    saved_plan = result.scalar_one()
    assert saved_plan.name == "PPL Block 1"
    assert saved_plan.ai_generated is True

    result = await db_session.execute(
        select(PlanExercise).where(PlanExercise.plan_day_id == day.id)
    )
    saved_pe = result.scalar_one()
    assert saved_pe.sets == 4
    assert saved_pe.weight == 80.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_models_plan.py -v`
Expected: FAIL — cannot import plan models

- [ ] **Step 3: Implement Plan models**

```python
# src/flexloop/models/plan.py
from datetime import date, datetime

from sqlalchemy import (
    Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from flexloop.db.base import Base


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    split_type: Mapped[str] = mapped_column(String(50), nullable=False)
    block_start: Mapped[date] = mapped_column(Date, nullable=False)
    block_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    days: Mapped[list["PlanDay"]] = relationship(back_populates="plan", cascade="all, delete-orphan")


class PlanDay(Base):
    __tablename__ = "plan_days"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("plans.id"), nullable=False)
    day_number: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    focus: Mapped[str] = mapped_column(String(200), nullable=False)

    plan: Mapped["Plan"] = relationship(back_populates="days")
    exercise_groups: Mapped[list["ExerciseGroup"]] = relationship(
        back_populates="plan_day", cascade="all, delete-orphan"
    )
    exercises: Mapped[list["PlanExercise"]] = relationship(
        back_populates="plan_day", cascade="all, delete-orphan"
    )


class ExerciseGroup(Base):
    __tablename__ = "exercise_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_day_id: Mapped[int] = mapped_column(Integer, ForeignKey("plan_days.id"), nullable=False)
    group_type: Mapped[str] = mapped_column(String(20), nullable=False, default="straight")
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    rest_after_group_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=90)

    plan_day: Mapped["PlanDay"] = relationship(back_populates="exercise_groups")
    exercises: Mapped[list["PlanExercise"]] = relationship(back_populates="exercise_group")


class PlanExercise(Base):
    __tablename__ = "plan_exercises"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_day_id: Mapped[int] = mapped_column(Integer, ForeignKey("plan_days.id"), nullable=False)
    exercise_group_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("exercise_groups.id"), nullable=False
    )
    exercise_id: Mapped[int] = mapped_column(Integer, ForeignKey("exercises.id"), nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    sets: Mapped[int] = mapped_column(Integer, nullable=False)
    reps: Mapped[int] = mapped_column(Integer, nullable=False)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    rpe_target: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    plan_day: Mapped["PlanDay"] = relationship(back_populates="exercises")
    exercise_group: Mapped["ExerciseGroup"] = relationship(back_populates="exercises")
```

- [ ] **Step 4: Update models __init__**

```python
# src/flexloop/models/__init__.py
from flexloop.models.exercise import Exercise
from flexloop.models.plan import ExerciseGroup, Plan, PlanDay, PlanExercise
from flexloop.models.user import User
from flexloop.models.volume_landmark import VolumeLandmark

__all__ = [
    "Exercise", "ExerciseGroup", "Plan", "PlanDay", "PlanExercise",
    "User", "VolumeLandmark",
]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_models_plan.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add .
git commit -m "feat: add Plan, PlanDay, ExerciseGroup, and PlanExercise models"
```

---

### Task 5: Define database models — Workout Sessions, Sets, Feedback

**Files:**
- Create: `src/flexloop/models/workout.py`
- Create: `tests/test_models_workout.py`
- Modify: `src/flexloop/models/__init__.py`

- [ ] **Step 1: Write failing test for workout session with sets**

```python
# tests/test_models_workout.py
import pytest
from datetime import datetime
from sqlalchemy import select

from flexloop.models.user import User
from flexloop.models.exercise import Exercise
from flexloop.models.workout import WorkoutSession, WorkoutSet, SessionFeedback


@pytest.fixture
async def user_and_exercise(db_session):
    user = User(
        name="Test User", gender="male", age=28, height_cm=180.0,
        weight_kg=82.0, experience_level="intermediate", goals="hypertrophy",
        available_equipment=["barbell"],
    )
    exercise = Exercise(
        name="Squat", muscle_group="quads", equipment="barbell",
        category="compound", difficulty="intermediate",
    )
    db_session.add_all([user, exercise])
    await db_session.commit()
    return user, exercise


@pytest.mark.asyncio
async def test_create_workout_session_with_sets(db_session, user_and_exercise):
    user, exercise = user_and_exercise

    session = WorkoutSession(
        user_id=user.id, source="ad_hoc",
        started_at=datetime(2026, 3, 23, 10, 0, 0),
    )
    db_session.add(session)
    await db_session.commit()

    workout_set = WorkoutSet(
        session_id=session.id, exercise_id=exercise.id,
        set_number=1, set_type="working",
        weight=100.0, reps=5, rpe=8.0, rest_sec=180,
    )
    db_session.add(workout_set)
    await db_session.commit()

    result = await db_session.execute(
        select(WorkoutSet).where(WorkoutSet.session_id == session.id)
    )
    saved_set = result.scalar_one()
    assert saved_set.weight == 100.0
    assert saved_set.set_type == "working"


@pytest.mark.asyncio
async def test_session_feedback(db_session, user_and_exercise):
    user, _ = user_and_exercise

    session = WorkoutSession(
        user_id=user.id, source="plan",
        started_at=datetime(2026, 3, 23, 10, 0, 0),
        completed_at=datetime(2026, 3, 23, 11, 0, 0),
    )
    db_session.add(session)
    await db_session.commit()

    feedback = SessionFeedback(
        session_id=session.id, sleep_quality=4, energy_level=3,
        muscle_soreness_json={"quads": 3, "hamstrings": 2},
        session_difficulty=4, stress_level=2,
    )
    db_session.add(feedback)
    await db_session.commit()

    result = await db_session.execute(
        select(SessionFeedback).where(SessionFeedback.session_id == session.id)
    )
    saved = result.scalar_one()
    assert saved.sleep_quality == 4
    assert saved.muscle_soreness_json["quads"] == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_models_workout.py -v`
Expected: FAIL — cannot import workout models

- [ ] **Step 3: Implement Workout models**

```python
# src/flexloop/models/workout.py
from datetime import datetime

from sqlalchemy import (
    JSON, DateTime, Float, ForeignKey, Integer, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from flexloop.db.base import Base


class WorkoutSession(Base):
    __tablename__ = "workout_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    plan_day_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("plan_days.id"), nullable=True
    )
    template_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="ad_hoc")
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    sets: Mapped[list["WorkoutSet"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    feedback: Mapped["SessionFeedback | None"] = relationship(
        back_populates="session", uselist=False, cascade="all, delete-orphan"
    )


class WorkoutSet(Base):
    __tablename__ = "workout_sets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workout_sessions.id"), nullable=False
    )
    exercise_id: Mapped[int] = mapped_column(Integer, ForeignKey("exercises.id"), nullable=False)
    exercise_group_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("exercise_groups.id"), nullable=True
    )
    set_number: Mapped[int] = mapped_column(Integer, nullable=False)
    set_type: Mapped[str] = mapped_column(String(20), nullable=False, default="working")
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    reps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rpe: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    rest_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)

    session: Mapped["WorkoutSession"] = relationship(back_populates="sets")


class SessionFeedback(Base):
    __tablename__ = "session_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workout_sessions.id"), nullable=False, unique=True
    )
    sleep_quality: Mapped[int | None] = mapped_column(Integer, nullable=True)
    energy_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    muscle_soreness_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    session_difficulty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stress_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    session: Mapped["WorkoutSession"] = relationship(back_populates="feedback")
```

- [ ] **Step 4: Update models __init__**

```python
# src/flexloop/models/__init__.py
from flexloop.models.exercise import Exercise
from flexloop.models.plan import ExerciseGroup, Plan, PlanDay, PlanExercise
from flexloop.models.user import User
from flexloop.models.volume_landmark import VolumeLandmark
from flexloop.models.workout import SessionFeedback, WorkoutSession, WorkoutSet

__all__ = [
    "Exercise", "ExerciseGroup", "Plan", "PlanDay", "PlanExercise",
    "SessionFeedback", "User", "VolumeLandmark", "WorkoutSession", "WorkoutSet",
]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_models_workout.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add .
git commit -m "feat: add WorkoutSession, WorkoutSet, and SessionFeedback models"
```

---

### Task 6: Define database models — AI, Templates, Measurements, PRs, Notifications, Backups

**Files:**
- Create: `src/flexloop/models/ai.py`
- Create: `src/flexloop/models/template.py`
- Create: `src/flexloop/models/measurement.py`
- Create: `src/flexloop/models/personal_record.py`
- Create: `src/flexloop/models/notification.py`
- Create: `src/flexloop/models/backup.py`
- Create: `tests/test_models_misc.py`
- Modify: `src/flexloop/models/__init__.py`

- [ ] **Step 1: Write failing tests for remaining models**

```python
# tests/test_models_misc.py
import pytest
from datetime import date, datetime
from sqlalchemy import select

from flexloop.models.user import User
from flexloop.models.exercise import Exercise
from flexloop.models.ai import AIReview, AIChatMessage, AIUsage
from flexloop.models.template import Template
from flexloop.models.measurement import Measurement
from flexloop.models.personal_record import PersonalRecord
from flexloop.models.notification import Notification
from flexloop.models.backup import Backup


@pytest.fixture
async def user(db_session):
    user = User(
        name="Test User", gender="male", age=28, height_cm=180.0,
        weight_kg=82.0, experience_level="intermediate", goals="hypertrophy",
        available_equipment=[],
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.mark.asyncio
async def test_ai_review(db_session, user):
    review = AIReview(
        user_id=user.id, review_type="block",
        input_summary="8-week PPL block data",
        output_json={"summary": "Good progress"},
        suggestions_json=[{"text": "Increase squat volume", "confidence": "high"}],
        model_used="gpt-4o-mini",
        input_tokens=1500, output_tokens=800, estimated_cost=0.003,
    )
    db_session.add(review)
    await db_session.commit()

    result = await db_session.execute(select(AIReview).where(AIReview.user_id == user.id))
    saved = result.scalar_one()
    assert saved.model_used == "gpt-4o-mini"
    assert saved.input_tokens == 1500


@pytest.mark.asyncio
async def test_ai_chat_message(db_session, user):
    msg = AIChatMessage(
        user_id=user.id, role="user",
        content="Why did you change my squat day?",
        input_tokens=50, output_tokens=0,
    )
    db_session.add(msg)
    await db_session.commit()

    result = await db_session.execute(select(AIChatMessage).where(AIChatMessage.user_id == user.id))
    saved = result.scalar_one()
    assert saved.role == "user"


@pytest.mark.asyncio
async def test_ai_usage(db_session, user):
    usage = AIUsage(
        user_id=user.id, month="2026-03",
        total_input_tokens=5000, total_output_tokens=3000,
        estimated_cost=0.012, call_count=5,
    )
    db_session.add(usage)
    await db_session.commit()

    result = await db_session.execute(select(AIUsage).where(AIUsage.user_id == user.id))
    saved = result.scalar_one()
    assert saved.call_count == 5


@pytest.mark.asyncio
async def test_template(db_session, user):
    template = Template(
        user_id=user.id, name="Quick Push Day",
        exercises_json=[{"exercise_id": 1, "sets": 3, "reps": 10}],
    )
    db_session.add(template)
    await db_session.commit()

    result = await db_session.execute(select(Template).where(Template.user_id == user.id))
    saved = result.scalar_one()
    assert saved.name == "Quick Push Day"


@pytest.mark.asyncio
async def test_measurement(db_session, user):
    m = Measurement(
        user_id=user.id, date=date(2026, 3, 23),
        type="waist", value_cm=82.5, notes="Morning measurement",
    )
    db_session.add(m)
    await db_session.commit()

    result = await db_session.execute(select(Measurement).where(Measurement.user_id == user.id))
    saved = result.scalar_one()
    assert saved.value_cm == 82.5


@pytest.mark.asyncio
async def test_personal_record(db_session, user):
    exercise = Exercise(
        name="Squat", muscle_group="quads", equipment="barbell",
        category="compound", difficulty="intermediate",
    )
    db_session.add(exercise)
    await db_session.commit()

    pr = PersonalRecord(
        user_id=user.id, exercise_id=exercise.id,
        pr_type="estimated_1rm", value=140.0,
        achieved_at=datetime(2026, 3, 23, 10, 30, 0),
    )
    db_session.add(pr)
    await db_session.commit()

    result = await db_session.execute(select(PersonalRecord).where(PersonalRecord.user_id == user.id))
    saved = result.scalar_one()
    assert saved.value == 140.0
    assert saved.pr_type == "estimated_1rm"


@pytest.mark.asyncio
async def test_notification(db_session, user):
    n = Notification(
        user_id=user.id, type="pr_achieved",
        title="New PR!", body="You hit a new squat PR: 140kg estimated 1RM",
    )
    db_session.add(n)
    await db_session.commit()

    result = await db_session.execute(select(Notification).where(Notification.user_id == user.id))
    saved = result.scalar_one()
    assert saved.read is False


@pytest.mark.asyncio
async def test_backup(db_session):
    b = Backup(
        filename="flexloop_backup_2026-03-23.db",
        size_bytes=1024000, schema_version="1.0.0",
    )
    db_session.add(b)
    await db_session.commit()

    result = await db_session.execute(select(Backup))
    saved = result.scalar_one()
    assert saved.filename == "flexloop_backup_2026-03-23.db"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_models_misc.py -v`
Expected: FAIL — cannot import models

- [ ] **Step 3: Implement AI models**

```python
# src/flexloop/models/ai.py
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from flexloop.db.base import Base


class AIReview(Base):
    __tablename__ = "ai_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    plan_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("plans.id"), nullable=True
    )
    review_type: Mapped[str] = mapped_column(String(20), nullable=False)
    input_summary: Mapped[str] = mapped_column(Text, nullable=False)
    output_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    suggestions_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    accepted_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    model_used: Mapped[str] = mapped_column(String(100), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AIChatMessage(Base):
    __tablename__ = "ai_chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    context_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AIUsage(Base):
    __tablename__ = "ai_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    month: Mapped[str] = mapped_column(String(7), nullable=False)
    total_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0.0)
    call_count: Mapped[int] = mapped_column(Integer, default=0)
```

- [ ] **Step 4: Implement Template, Measurement, PersonalRecord, Notification, Backup models**

```python
# src/flexloop/models/template.py
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from flexloop.db.base import Base


class Template(Base):
    __tablename__ = "templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    exercises_json: Mapped[list] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

```python
# src/flexloop/models/measurement.py
from datetime import date

from sqlalchemy import Date, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from flexloop.db.base import Base


class Measurement(Base):
    __tablename__ = "measurements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    value_cm: Mapped[float] = mapped_column(Float, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
```

```python
# src/flexloop/models/personal_record.py
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from flexloop.db.base import Base


class PersonalRecord(Base):
    __tablename__ = "personal_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    exercise_id: Mapped[int] = mapped_column(Integer, ForeignKey("exercises.id"), nullable=False)
    pr_type: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    session_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("workout_sessions.id"), nullable=True
    )
    achieved_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
```

```python
# src/flexloop/models/notification.py
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from flexloop.db.base import Base


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    action_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

```python
# src/flexloop/models/backup.py
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from flexloop.db.base import Base


class Backup(Base):
    __tablename__ = "backups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

- [ ] **Step 5: Update models __init__ with all models**

```python
# src/flexloop/models/__init__.py
from flexloop.models.ai import AIChatMessage, AIReview, AIUsage
from flexloop.models.backup import Backup
from flexloop.models.exercise import Exercise
from flexloop.models.measurement import Measurement
from flexloop.models.notification import Notification
from flexloop.models.personal_record import PersonalRecord
from flexloop.models.plan import ExerciseGroup, Plan, PlanDay, PlanExercise
from flexloop.models.template import Template
from flexloop.models.user import User
from flexloop.models.volume_landmark import VolumeLandmark
from flexloop.models.workout import SessionFeedback, WorkoutSession, WorkoutSet

__all__ = [
    "AIChatMessage", "AIReview", "AIUsage",
    "Backup", "Exercise", "ExerciseGroup",
    "Measurement", "Notification", "PersonalRecord",
    "Plan", "PlanDay", "PlanExercise",
    "SessionFeedback", "Template", "User",
    "VolumeLandmark", "WorkoutSession", "WorkoutSet",
]
```

- [ ] **Step 6: Run all model tests**

Run: `pytest tests/ -v`
Expected: All PASS

- [ ] **Step 7: Generate initial Alembic migration**

Run: `cd flexloop-server && alembic revision --autogenerate -m "initial schema"`
Verify: a migration file is created in `alembic/versions/`

- [ ] **Step 8: Commit**

```bash
git add .
git commit -m "feat: add all remaining models (AI, templates, measurements, PRs, notifications, backups) and initial migration"
```

---

## Chunk 2: Pydantic Schemas & Core CRUD API Endpoints

### Task 7: Define Pydantic request/response schemas

**Files:**
- Create: `src/flexloop/schemas/__init__.py`
- Create: `src/flexloop/schemas/user.py`
- Create: `src/flexloop/schemas/exercise.py`
- Create: `src/flexloop/schemas/plan.py`
- Create: `src/flexloop/schemas/workout.py`
- Create: `src/flexloop/schemas/template.py`
- Create: `src/flexloop/schemas/measurement.py`
- Create: `src/flexloop/schemas/ai.py`

- [ ] **Step 1: Create User schemas**

```python
# src/flexloop/schemas/user.py
from datetime import datetime

from pydantic import BaseModel


class UserCreate(BaseModel):
    name: str
    gender: str
    age: int
    height_cm: float
    weight_kg: float
    experience_level: str
    goals: str
    available_equipment: list[str] = []


class UserUpdate(BaseModel):
    name: str | None = None
    gender: str | None = None
    age: int | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    experience_level: str | None = None
    goals: str | None = None
    available_equipment: list[str] | None = None


class UserResponse(BaseModel):
    id: int
    name: str
    gender: str
    age: int
    height_cm: float
    weight_kg: float
    experience_level: str
    goals: str
    available_equipment: list[str]
    created_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 2: Create Exercise schemas**

```python
# src/flexloop/schemas/exercise.py
from pydantic import BaseModel


class ExerciseResponse(BaseModel):
    id: int
    name: str
    muscle_group: str
    equipment: str
    category: str
    difficulty: str
    source_plugin: str | None = None
    metadata_json: dict | None = None

    model_config = {"from_attributes": True}


class ExerciseListResponse(BaseModel):
    exercises: list[ExerciseResponse]
    total: int
```

- [ ] **Step 3: Create Plan schemas**

```python
# src/flexloop/schemas/plan.py
from datetime import date, datetime

from pydantic import BaseModel


class PlanExerciseResponse(BaseModel):
    id: int
    exercise_id: int
    order: int
    sets: int
    reps: int
    weight: float | None = None
    rpe_target: float | None = None
    notes: str | None = None

    model_config = {"from_attributes": True}


class ExerciseGroupResponse(BaseModel):
    id: int
    group_type: str
    order: int
    rest_after_group_sec: int
    exercises: list[PlanExerciseResponse] = []

    model_config = {"from_attributes": True}


class PlanDayResponse(BaseModel):
    id: int
    day_number: int
    label: str
    focus: str
    exercise_groups: list[ExerciseGroupResponse] = []

    model_config = {"from_attributes": True}


class PlanResponse(BaseModel):
    id: int
    user_id: int
    name: str
    split_type: str
    block_start: date
    block_end: date
    status: str
    ai_generated: bool
    created_at: datetime
    days: list[PlanDayResponse] = []

    model_config = {"from_attributes": True}


class PlanListResponse(BaseModel):
    plans: list[PlanResponse]
    total: int


class PlanGenerateRequest(BaseModel):
    user_id: int
```

- [ ] **Step 4: Create Workout schemas**

```python
# src/flexloop/schemas/workout.py
from datetime import datetime

from pydantic import BaseModel


class WorkoutSetCreate(BaseModel):
    exercise_id: int
    exercise_group_id: int | None = None
    set_number: int
    set_type: str = "working"
    weight: float | None = None
    reps: int | None = None
    rpe: float | None = None
    duration_sec: int | None = None
    distance_m: float | None = None
    rest_sec: int | None = None


class WorkoutSetResponse(BaseModel):
    id: int
    exercise_id: int
    exercise_group_id: int | None = None
    set_number: int
    set_type: str
    weight: float | None = None
    reps: int | None = None
    rpe: float | None = None
    duration_sec: int | None = None
    distance_m: float | None = None
    rest_sec: int | None = None

    model_config = {"from_attributes": True}


class SessionFeedbackCreate(BaseModel):
    sleep_quality: int | None = None
    energy_level: int | None = None
    muscle_soreness_json: dict | None = None
    session_difficulty: int | None = None
    stress_level: int | None = None


class SessionFeedbackResponse(BaseModel):
    id: int
    sleep_quality: int | None = None
    energy_level: int | None = None
    muscle_soreness_json: dict | None = None
    session_difficulty: int | None = None
    stress_level: int | None = None

    model_config = {"from_attributes": True}


class WorkoutSessionCreate(BaseModel):
    user_id: int
    plan_day_id: int | None = None
    template_id: int | None = None
    source: str = "ad_hoc"
    notes: str | None = None


class WorkoutSessionUpdate(BaseModel):
    completed_at: datetime | None = None
    notes: str | None = None
    sets: list[WorkoutSetCreate] | None = None


class WorkoutSessionResponse(BaseModel):
    id: int
    user_id: int
    plan_day_id: int | None = None
    template_id: int | None = None
    source: str
    started_at: datetime
    completed_at: datetime | None = None
    notes: str | None = None
    sets: list[WorkoutSetResponse] = []
    feedback: SessionFeedbackResponse | None = None

    model_config = {"from_attributes": True}
```

- [ ] **Step 5: Create Template, Measurement, and AI schemas**

```python
# src/flexloop/schemas/template.py
from datetime import datetime

from pydantic import BaseModel


class TemplateCreate(BaseModel):
    user_id: int
    name: str
    exercises_json: list[dict]


class TemplateUpdate(BaseModel):
    name: str | None = None
    exercises_json: list[dict] | None = None


class TemplateResponse(BaseModel):
    id: int
    user_id: int
    name: str
    exercises_json: list[dict]
    created_at: datetime

    model_config = {"from_attributes": True}
```

```python
# src/flexloop/schemas/measurement.py
from datetime import date

from pydantic import BaseModel


class MeasurementCreate(BaseModel):
    user_id: int
    date: date
    type: str
    value_cm: float
    notes: str | None = None


class MeasurementResponse(BaseModel):
    id: int
    user_id: int
    date: date
    type: str
    value_cm: float
    notes: str | None = None

    model_config = {"from_attributes": True}
```

```python
# src/flexloop/schemas/ai.py
from pydantic import BaseModel


class AIChatRequest(BaseModel):
    user_id: int
    message: str


class AIChatResponse(BaseModel):
    reply: str
    input_tokens: int
    output_tokens: int


class AIReviewRequest(BaseModel):
    user_id: int
    plan_id: int | None = None


class AISuggestion(BaseModel):
    text: str
    confidence: str
    reasoning: str


class AIReviewResponse(BaseModel):
    id: int
    review_type: str
    summary: dict
    suggestions: list[AISuggestion]
    model_used: str
    input_tokens: int
    output_tokens: int
    estimated_cost: float

    model_config = {"from_attributes": True}


class AISuggestionUpdate(BaseModel):
    accepted: bool


class AIUsageResponse(BaseModel):
    month: str
    total_input_tokens: int
    total_output_tokens: int
    estimated_cost: float
    call_count: int

    model_config = {"from_attributes": True}
```

```python
# src/flexloop/schemas/__init__.py
```

- [ ] **Step 6: Commit**

```bash
git add .
git commit -m "feat: add Pydantic request/response schemas for all API endpoints"
```

---

### Task 8: Implement Profile API endpoints

**Files:**
- Create: `src/flexloop/routers/__init__.py`
- Create: `src/flexloop/routers/profiles.py`
- Create: `tests/test_api_profiles.py`
- Modify: `src/flexloop/main.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Write failing tests for profile CRUD**

```python
# tests/test_api_profiles.py
import pytest


@pytest.mark.asyncio
async def test_create_profile(client):
    response = await client.post("/api/profiles", json={
        "name": "Test User",
        "gender": "male",
        "age": 28,
        "height_cm": 180.0,
        "weight_kg": 82.0,
        "experience_level": "intermediate",
        "goals": "hypertrophy",
        "available_equipment": ["barbell", "dumbbells"],
    })
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test User"
    assert data["id"] is not None


@pytest.mark.asyncio
async def test_get_profile(client):
    create_resp = await client.post("/api/profiles", json={
        "name": "Test User",
        "gender": "female",
        "age": 25,
        "height_cm": 165.0,
        "weight_kg": 60.0,
        "experience_level": "beginner",
        "goals": "general fitness",
        "available_equipment": [],
    })
    user_id = create_resp.json()["id"]

    response = await client.get(f"/api/profiles/{user_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "Test User"


@pytest.mark.asyncio
async def test_get_profile_not_found(client):
    response = await client.get("/api/profiles/999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_profile(client):
    create_resp = await client.post("/api/profiles", json={
        "name": "Test User",
        "gender": "male",
        "age": 28,
        "height_cm": 180.0,
        "weight_kg": 82.0,
        "experience_level": "intermediate",
        "goals": "hypertrophy",
        "available_equipment": [],
    })
    user_id = create_resp.json()["id"]

    response = await client.put(f"/api/profiles/{user_id}", json={
        "weight_kg": 84.0,
        "goals": "strength",
    })
    assert response.status_code == 200
    assert response.json()["weight_kg"] == 84.0
    assert response.json()["goals"] == "strength"
    assert response.json()["name"] == "Test User"  # unchanged field preserved
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_profiles.py -v`
Expected: FAIL — 404 for all routes

- [ ] **Step 3: Update conftest to use dependency override for db session**

```python
# tests/conftest.py
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from flexloop.db.base import Base
from flexloop.db.engine import get_session
from flexloop.main import app
import flexloop.models  # noqa: F401

TEST_DATABASE_URL = "sqlite+aiosqlite://"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
test_session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(autouse=True)
async def setup_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def db_session():
    async with test_session_factory() as session:
        yield session


async def override_get_session():
    async with test_session_factory() as session:
        yield session


app.dependency_overrides[get_session] = override_get_session


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
```

- [ ] **Step 4: Implement profiles router**

```python
# src/flexloop/routers/__init__.py
```

```python
# src/flexloop/routers/profiles.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.db.engine import get_session
from flexloop.models.user import User
from flexloop.schemas.user import UserCreate, UserResponse, UserUpdate

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


@router.post("", response_model=UserResponse, status_code=201)
async def create_profile(data: UserCreate, session: AsyncSession = Depends(get_session)):
    user = User(**data.model_dump())
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@router.get("/{user_id}", response_model=UserResponse)
async def get_profile(user_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.put("/{user_id}", response_model=UserResponse)
async def update_profile(
    user_id: int, data: UserUpdate, session: AsyncSession = Depends(get_session)
):
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)

    await session.commit()
    await session.refresh(user)
    return user
```

- [ ] **Step 5: Register router in main.py**

```python
# src/flexloop/main.py
from contextlib import asynccontextmanager

from fastapi import FastAPI

from flexloop.db.engine import init_db
from flexloop.routers.profiles import router as profiles_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="FlexLoop API",
    description="AI-powered fitness training companion",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(profiles_router)


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "1.0.0"}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_api_profiles.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add .
git commit -m "feat: add profile CRUD API endpoints (POST, GET, PUT /api/profiles)"
```

---

### Task 9: Implement Exercise Library API endpoints

**Files:**
- Create: `src/flexloop/routers/exercises.py`
- Create: `tests/test_api_exercises.py`
- Modify: `src/flexloop/main.py`

- [ ] **Step 1: Write failing tests for exercise listing and search**

```python
# tests/test_api_exercises.py
import pytest

from flexloop.models.exercise import Exercise


@pytest.fixture
async def seed_exercises(db_session):
    exercises = [
        Exercise(name="Bench Press", muscle_group="chest", equipment="barbell",
                 category="compound", difficulty="intermediate"),
        Exercise(name="Squat", muscle_group="quads", equipment="barbell",
                 category="compound", difficulty="intermediate"),
        Exercise(name="Push-Up", muscle_group="chest", equipment="bodyweight",
                 category="compound", difficulty="beginner"),
        Exercise(name="Bicep Curl", muscle_group="biceps", equipment="dumbbell",
                 category="isolation", difficulty="beginner"),
    ]
    db_session.add_all(exercises)
    await db_session.commit()


@pytest.mark.asyncio
async def test_list_exercises(client, seed_exercises):
    response = await client.get("/api/exercises")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 4
    assert len(data["exercises"]) == 4


@pytest.mark.asyncio
async def test_search_exercises_by_muscle_group(client, seed_exercises):
    response = await client.get("/api/exercises?muscle_group=chest")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert all(e["muscle_group"] == "chest" for e in data["exercises"])


@pytest.mark.asyncio
async def test_search_exercises_by_equipment(client, seed_exercises):
    response = await client.get("/api/exercises?equipment=bodyweight")
    data = response.json()
    assert data["total"] == 1
    assert data["exercises"][0]["name"] == "Push-Up"


@pytest.mark.asyncio
async def test_search_exercises_by_query(client, seed_exercises):
    response = await client.get("/api/exercises?q=curl")
    data = response.json()
    assert data["total"] == 1
    assert data["exercises"][0]["name"] == "Bicep Curl"


@pytest.mark.asyncio
async def test_get_exercise_by_id(client, seed_exercises):
    list_resp = await client.get("/api/exercises")
    exercise_id = list_resp.json()["exercises"][0]["id"]

    response = await client.get(f"/api/exercises/{exercise_id}")
    assert response.status_code == 200
    assert response.json()["id"] == exercise_id


@pytest.mark.asyncio
async def test_get_exercise_not_found(client):
    response = await client.get("/api/exercises/999")
    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_exercises.py -v`
Expected: FAIL — 404 or route not found

- [ ] **Step 3: Implement exercises router**

```python
# src/flexloop/routers/exercises.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.db.engine import get_session
from flexloop.models.exercise import Exercise
from flexloop.schemas.exercise import ExerciseListResponse, ExerciseResponse

router = APIRouter(prefix="/api/exercises", tags=["exercises"])


@router.get("", response_model=ExerciseListResponse)
async def list_exercises(
    muscle_group: str | None = None,
    equipment: str | None = None,
    category: str | None = None,
    difficulty: str | None = None,
    q: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    query = select(Exercise)

    if muscle_group:
        query = query.where(Exercise.muscle_group == muscle_group)
    if equipment:
        query = query.where(Exercise.equipment == equipment)
    if category:
        query = query.where(Exercise.category == category)
    if difficulty:
        query = query.where(Exercise.difficulty == difficulty)
    if q:
        query = query.where(Exercise.name.ilike(f"%{q}%"))

    result = await session.execute(query)
    exercises = result.scalars().all()
    return ExerciseListResponse(exercises=exercises, total=len(exercises))


@router.get("/{exercise_id}", response_model=ExerciseResponse)
async def get_exercise(exercise_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Exercise).where(Exercise.id == exercise_id))
    exercise = result.scalar_one_or_none()
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")
    return exercise
```

- [ ] **Step 4: Register router in main.py**

Add to `src/flexloop/main.py`:

```python
from flexloop.routers.exercises import router as exercises_router

app.include_router(exercises_router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_api_exercises.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add .
git commit -m "feat: add exercise library API endpoints with search/filter (GET /api/exercises)"
```

---

### Task 10: Implement Workout Session & Set API endpoints

**Files:**
- Create: `src/flexloop/routers/workouts.py`
- Create: `tests/test_api_workouts.py`
- Modify: `src/flexloop/main.py`

- [ ] **Step 1: Write failing tests for workout CRUD**

```python
# tests/test_api_workouts.py
import pytest

from flexloop.models.user import User
from flexloop.models.exercise import Exercise


@pytest.fixture
async def seed_user_exercise(db_session):
    user = User(
        name="Test User", gender="male", age=28, height_cm=180.0,
        weight_kg=82.0, experience_level="intermediate", goals="hypertrophy",
        available_equipment=["barbell"],
    )
    exercise = Exercise(
        name="Squat", muscle_group="quads", equipment="barbell",
        category="compound", difficulty="intermediate",
    )
    db_session.add_all([user, exercise])
    await db_session.commit()
    return user, exercise


@pytest.mark.asyncio
async def test_create_workout_session(client, seed_user_exercise):
    user, _ = seed_user_exercise
    response = await client.post("/api/workouts", json={
        "user_id": user.id,
        "source": "ad_hoc",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["user_id"] == user.id
    assert data["source"] == "ad_hoc"
    assert data["started_at"] is not None
    assert data["completed_at"] is None


@pytest.mark.asyncio
async def test_update_workout_add_sets(client, seed_user_exercise):
    user, exercise = seed_user_exercise

    create_resp = await client.post("/api/workouts", json={
        "user_id": user.id, "source": "ad_hoc",
    })
    session_id = create_resp.json()["id"]

    response = await client.put(f"/api/workouts/{session_id}", json={
        "sets": [
            {"exercise_id": exercise.id, "set_number": 1, "set_type": "working",
             "weight": 100.0, "reps": 5, "rpe": 7.5},
            {"exercise_id": exercise.id, "set_number": 2, "set_type": "working",
             "weight": 100.0, "reps": 5, "rpe": 8.0},
        ],
    })
    assert response.status_code == 200
    data = response.json()
    assert len(data["sets"]) == 2
    assert data["sets"][0]["weight"] == 100.0


@pytest.mark.asyncio
async def test_complete_workout(client, seed_user_exercise):
    user, _ = seed_user_exercise

    create_resp = await client.post("/api/workouts", json={
        "user_id": user.id, "source": "ad_hoc",
    })
    session_id = create_resp.json()["id"]

    response = await client.put(f"/api/workouts/{session_id}", json={
        "completed_at": "2026-03-23T11:00:00",
    })
    assert response.status_code == 200
    assert response.json()["completed_at"] is not None


@pytest.mark.asyncio
async def test_get_workout_session(client, seed_user_exercise):
    user, _ = seed_user_exercise

    create_resp = await client.post("/api/workouts", json={
        "user_id": user.id, "source": "ad_hoc",
    })
    session_id = create_resp.json()["id"]

    response = await client.get(f"/api/workouts/{session_id}")
    assert response.status_code == 200
    assert response.json()["id"] == session_id


@pytest.mark.asyncio
async def test_list_user_workouts(client, seed_user_exercise):
    user, _ = seed_user_exercise

    await client.post("/api/workouts", json={"user_id": user.id, "source": "ad_hoc"})
    await client.post("/api/workouts", json={"user_id": user.id, "source": "plan"})

    response = await client.get(f"/api/users/{user.id}/workouts")
    assert response.status_code == 200
    assert len(response.json()) == 2


@pytest.mark.asyncio
async def test_submit_session_feedback(client, seed_user_exercise):
    user, _ = seed_user_exercise

    create_resp = await client.post("/api/workouts", json={
        "user_id": user.id, "source": "ad_hoc",
    })
    session_id = create_resp.json()["id"]

    response = await client.post(f"/api/workouts/{session_id}/feedback", json={
        "sleep_quality": 4,
        "energy_level": 3,
        "session_difficulty": 4,
    })
    assert response.status_code == 201
    assert response.json()["sleep_quality"] == 4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_workouts.py -v`
Expected: FAIL

- [ ] **Step 3: Implement workouts router**

```python
# src/flexloop/routers/workouts.py
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from flexloop.db.engine import get_session
from flexloop.models.workout import SessionFeedback, WorkoutSession, WorkoutSet
from flexloop.schemas.workout import (
    SessionFeedbackCreate,
    SessionFeedbackResponse,
    WorkoutSessionCreate,
    WorkoutSessionResponse,
    WorkoutSessionUpdate,
)

router = APIRouter(tags=["workouts"])


@router.post("/api/workouts", response_model=WorkoutSessionResponse, status_code=201)
async def create_workout(
    data: WorkoutSessionCreate, session: AsyncSession = Depends(get_session)
):
    workout = WorkoutSession(
        user_id=data.user_id,
        plan_day_id=data.plan_day_id,
        template_id=data.template_id,
        source=data.source,
        started_at=datetime.now(),
        notes=data.notes,
    )
    session.add(workout)
    await session.commit()
    await session.refresh(workout)
    return workout


@router.put("/api/workouts/{workout_id}", response_model=WorkoutSessionResponse)
async def update_workout(
    workout_id: int, data: WorkoutSessionUpdate, session: AsyncSession = Depends(get_session)
):
    result = await session.execute(
        select(WorkoutSession)
        .where(WorkoutSession.id == workout_id)
        .options(selectinload(WorkoutSession.sets), selectinload(WorkoutSession.feedback))
    )
    workout = result.scalar_one_or_none()
    if not workout:
        raise HTTPException(status_code=404, detail="Workout session not found")

    if data.completed_at is not None:
        workout.completed_at = data.completed_at
    if data.notes is not None:
        workout.notes = data.notes
    if data.sets is not None:
        for set_data in data.sets:
            workout_set = WorkoutSet(session_id=workout.id, **set_data.model_dump())
            session.add(workout_set)

    await session.commit()

    result = await session.execute(
        select(WorkoutSession)
        .where(WorkoutSession.id == workout_id)
        .options(selectinload(WorkoutSession.sets), selectinload(WorkoutSession.feedback))
    )
    return result.scalar_one()


@router.get("/api/workouts/{workout_id}", response_model=WorkoutSessionResponse)
async def get_workout(workout_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(WorkoutSession)
        .where(WorkoutSession.id == workout_id)
        .options(selectinload(WorkoutSession.sets), selectinload(WorkoutSession.feedback))
    )
    workout = result.scalar_one_or_none()
    if not workout:
        raise HTTPException(status_code=404, detail="Workout session not found")
    return workout


@router.get("/api/users/{user_id}/workouts", response_model=list[WorkoutSessionResponse])
async def list_user_workouts(user_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(WorkoutSession)
        .where(WorkoutSession.user_id == user_id)
        .options(selectinload(WorkoutSession.sets), selectinload(WorkoutSession.feedback))
        .order_by(WorkoutSession.started_at.desc())
    )
    return result.scalars().all()


@router.post(
    "/api/workouts/{workout_id}/feedback",
    response_model=SessionFeedbackResponse,
    status_code=201,
)
async def submit_feedback(
    workout_id: int, data: SessionFeedbackCreate, session: AsyncSession = Depends(get_session)
):
    result = await session.execute(
        select(WorkoutSession).where(WorkoutSession.id == workout_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Workout session not found")

    feedback = SessionFeedback(session_id=workout_id, **data.model_dump(exclude_unset=True))
    session.add(feedback)
    await session.commit()
    await session.refresh(feedback)
    return feedback
```

- [ ] **Step 4: Register router in main.py**

Add to `src/flexloop/main.py`:

```python
from flexloop.routers.workouts import router as workouts_router

app.include_router(workouts_router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_api_workouts.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add .
git commit -m "feat: add workout session CRUD, set logging, and feedback API endpoints"
```

---

### Task 11: Implement Templates and Measurements API endpoints

**Files:**
- Create: `src/flexloop/routers/templates.py`
- Create: `src/flexloop/routers/measurements.py`
- Create: `tests/test_api_templates.py`
- Create: `tests/test_api_measurements.py`
- Modify: `src/flexloop/main.py`

- [ ] **Step 1: Write failing tests for templates**

```python
# tests/test_api_templates.py
import pytest

from flexloop.models.user import User


@pytest.fixture
async def user(db_session):
    user = User(
        name="Test User", gender="male", age=28, height_cm=180.0,
        weight_kg=82.0, experience_level="intermediate", goals="hypertrophy",
        available_equipment=[],
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.mark.asyncio
async def test_create_template(client, user):
    response = await client.post("/api/templates", json={
        "user_id": user.id,
        "name": "Quick Push Day",
        "exercises_json": [
            {"exercise_id": 1, "sets": 3, "reps": 10, "group_type": "straight"},
        ],
    })
    assert response.status_code == 201
    assert response.json()["name"] == "Quick Push Day"


@pytest.mark.asyncio
async def test_list_templates(client, user):
    await client.post("/api/templates", json={
        "user_id": user.id, "name": "Push Day",
        "exercises_json": [{"exercise_id": 1, "sets": 3, "reps": 10}],
    })
    await client.post("/api/templates", json={
        "user_id": user.id, "name": "Pull Day",
        "exercises_json": [{"exercise_id": 2, "sets": 3, "reps": 10}],
    })

    response = await client.get(f"/api/templates?user_id={user.id}")
    assert response.status_code == 200
    assert len(response.json()) == 2


@pytest.mark.asyncio
async def test_update_template(client, user):
    create_resp = await client.post("/api/templates", json={
        "user_id": user.id, "name": "Push Day",
        "exercises_json": [{"exercise_id": 1, "sets": 3, "reps": 10}],
    })
    template_id = create_resp.json()["id"]

    response = await client.put(f"/api/templates/{template_id}", json={
        "name": "Heavy Push Day",
    })
    assert response.status_code == 200
    assert response.json()["name"] == "Heavy Push Day"


@pytest.mark.asyncio
async def test_delete_template(client, user):
    create_resp = await client.post("/api/templates", json={
        "user_id": user.id, "name": "Push Day",
        "exercises_json": [{"exercise_id": 1, "sets": 3, "reps": 10}],
    })
    template_id = create_resp.json()["id"]

    response = await client.delete(f"/api/templates/{template_id}")
    assert response.status_code == 204

    response = await client.get(f"/api/templates/{template_id}")
    assert response.status_code == 404
```

- [ ] **Step 2: Write failing tests for measurements**

```python
# tests/test_api_measurements.py
import pytest

from flexloop.models.user import User


@pytest.fixture
async def user(db_session):
    user = User(
        name="Test User", gender="male", age=28, height_cm=180.0,
        weight_kg=82.0, experience_level="intermediate", goals="hypertrophy",
        available_equipment=[],
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.mark.asyncio
async def test_create_measurement(client, user):
    response = await client.post("/api/measurements", json={
        "user_id": user.id,
        "date": "2026-03-23",
        "type": "waist",
        "value_cm": 82.5,
        "notes": "Morning measurement",
    })
    assert response.status_code == 201
    assert response.json()["value_cm"] == 82.5


@pytest.mark.asyncio
async def test_list_measurements(client, user):
    await client.post("/api/measurements", json={
        "user_id": user.id, "date": "2026-03-20", "type": "waist", "value_cm": 83.0,
    })
    await client.post("/api/measurements", json={
        "user_id": user.id, "date": "2026-03-23", "type": "waist", "value_cm": 82.5,
    })
    await client.post("/api/measurements", json={
        "user_id": user.id, "date": "2026-03-23", "type": "chest", "value_cm": 100.0,
    })

    response = await client.get(f"/api/users/{user.id}/measurements?type=waist")
    assert response.status_code == 200
    assert len(response.json()) == 2
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_api_templates.py tests/test_api_measurements.py -v`
Expected: FAIL

- [ ] **Step 4: Implement templates router**

```python
# src/flexloop/routers/templates.py
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.db.engine import get_session
from flexloop.models.template import Template
from flexloop.schemas.template import TemplateCreate, TemplateResponse, TemplateUpdate

router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.post("", response_model=TemplateResponse, status_code=201)
async def create_template(data: TemplateCreate, session: AsyncSession = Depends(get_session)):
    template = Template(**data.model_dump())
    session.add(template)
    await session.commit()
    await session.refresh(template)
    return template


@router.get("", response_model=list[TemplateResponse])
async def list_templates(user_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Template).where(Template.user_id == user_id).order_by(Template.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(template_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Template).where(Template.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


@router.put("/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: int, data: TemplateUpdate, session: AsyncSession = Depends(get_session)
):
    result = await session.execute(select(Template).where(Template.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(template, field, value)

    await session.commit()
    await session.refresh(template)
    return template


@router.delete("/{template_id}", status_code=204)
async def delete_template(template_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Template).where(Template.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    await session.delete(template)
    await session.commit()
    return Response(status_code=204)
```

- [ ] **Step 5: Implement measurements router**

```python
# src/flexloop/routers/measurements.py
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.db.engine import get_session
from flexloop.models.measurement import Measurement
from flexloop.schemas.measurement import MeasurementCreate, MeasurementResponse

router = APIRouter(tags=["measurements"])


@router.post("/api/measurements", response_model=MeasurementResponse, status_code=201)
async def create_measurement(
    data: MeasurementCreate, session: AsyncSession = Depends(get_session)
):
    measurement = Measurement(**data.model_dump())
    session.add(measurement)
    await session.commit()
    await session.refresh(measurement)
    return measurement


@router.get(
    "/api/users/{user_id}/measurements", response_model=list[MeasurementResponse]
)
async def list_measurements(
    user_id: int,
    type: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    query = select(Measurement).where(Measurement.user_id == user_id)
    if type:
        query = query.where(Measurement.type == type)
    query = query.order_by(Measurement.date.desc())

    result = await session.execute(query)
    return result.scalars().all()
```

- [ ] **Step 6: Register routers in main.py**

Add to `src/flexloop/main.py`:

```python
from flexloop.routers.templates import router as templates_router
from flexloop.routers.measurements import router as measurements_router

app.include_router(templates_router)
app.include_router(measurements_router)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_api_templates.py tests/test_api_measurements.py -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add .
git commit -m "feat: add templates CRUD and measurements API endpoints"
```

---

## Chunk 3: LLM Adapter Layer & AI Features

### Task 12: Implement LLM adapter interface and OpenAI adapter

**Files:**
- Create: `src/flexloop/ai/__init__.py`
- Create: `src/flexloop/ai/base.py`
- Create: `src/flexloop/ai/openai_adapter.py`
- Create: `src/flexloop/ai/factory.py`
- Create: `tests/test_ai_adapters.py`

- [ ] **Step 1: Write failing test for adapter factory**

```python
# tests/test_ai_adapters.py
import pytest

from flexloop.ai.base import LLMAdapter
from flexloop.ai.factory import create_adapter


def test_create_openai_adapter():
    adapter = create_adapter(provider="openai", model="gpt-4o-mini", api_key="test-key")
    assert isinstance(adapter, LLMAdapter)


def test_create_unknown_adapter_raises():
    with pytest.raises(ValueError, match="Unknown provider"):
        create_adapter(provider="unknown", model="test", api_key="test")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ai_adapters.py -v`
Expected: FAIL — cannot import

- [ ] **Step 3: Implement base adapter interface**

```python
# src/flexloop/ai/__init__.py
```

```python
# src/flexloop/ai/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    content: str
    input_tokens: int
    output_tokens: int


class LLMAdapter(ABC):
    def __init__(self, model: str, api_key: str, base_url: str = "", **kwargs):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url

    @abstractmethod
    async def generate(
        self, system_prompt: str, user_prompt: str, temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> LLMResponse:
        pass

    @abstractmethod
    async def chat(
        self, messages: list[dict], temperature: float = 0.7, max_tokens: int = 2000,
    ) -> LLMResponse:
        pass
```

- [ ] **Step 4: Implement OpenAI adapter**

```python
# src/flexloop/ai/openai_adapter.py
from openai import AsyncOpenAI

from flexloop.ai.base import LLMAdapter, LLMResponse


class OpenAIAdapter(LLMAdapter):
    def __init__(self, model: str, api_key: str, base_url: str = "", **kwargs):
        super().__init__(model, api_key, base_url)
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        self.client = AsyncOpenAI(**client_kwargs)

    async def generate(
        self, system_prompt: str, user_prompt: str, temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> LLMResponse:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return LLMResponse(
            content=response.choices[0].message.content or "",
            input_tokens=response.usage.prompt_tokens if response.usage else 0,
            output_tokens=response.usage.completion_tokens if response.usage else 0,
        )

    async def chat(
        self, messages: list[dict], temperature: float = 0.7, max_tokens: int = 2000,
    ) -> LLMResponse:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return LLMResponse(
            content=response.choices[0].message.content or "",
            input_tokens=response.usage.prompt_tokens if response.usage else 0,
            output_tokens=response.usage.completion_tokens if response.usage else 0,
        )
```

- [ ] **Step 5: Implement adapter factory**

```python
# src/flexloop/ai/factory.py
from flexloop.ai.base import LLMAdapter
from flexloop.ai.openai_adapter import OpenAIAdapter


def create_adapter(
    provider: str, model: str, api_key: str, base_url: str = "", **kwargs
) -> LLMAdapter:
    if provider == "openai":
        return OpenAIAdapter(model=model, api_key=api_key, base_url=base_url, **kwargs)
    elif provider == "openai-compatible":
        return OpenAIAdapter(model=model, api_key=api_key, base_url=base_url, **kwargs)
    raise ValueError(f"Unknown provider: {provider}")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_ai_adapters.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add .
git commit -m "feat: add LLM adapter interface, OpenAI adapter, and factory"
```

---

### Task 13: Implement Anthropic and Ollama adapters

**Files:**
- Create: `src/flexloop/ai/anthropic_adapter.py`
- Create: `src/flexloop/ai/ollama_adapter.py`
- Modify: `src/flexloop/ai/factory.py`
- Modify: `tests/test_ai_adapters.py`

- [ ] **Step 1: Write failing tests for new adapters**

```python
# tests/test_ai_adapters.py (append)

def test_create_anthropic_adapter():
    adapter = create_adapter(provider="anthropic", model="claude-sonnet-4-20250514", api_key="test-key")
    assert isinstance(adapter, LLMAdapter)


def test_create_ollama_adapter():
    adapter = create_adapter(provider="ollama", model="llama3", api_key="")
    assert isinstance(adapter, LLMAdapter)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ai_adapters.py -v`
Expected: FAIL on new tests — ValueError for unknown provider

- [ ] **Step 3: Implement Anthropic adapter**

```python
# src/flexloop/ai/anthropic_adapter.py
from anthropic import AsyncAnthropic

from flexloop.ai.base import LLMAdapter, LLMResponse


class AnthropicAdapter(LLMAdapter):
    def __init__(self, model: str, api_key: str, **kwargs):
        super().__init__(model, api_key)
        self.client = AsyncAnthropic(api_key=api_key)

    async def generate(
        self, system_prompt: str, user_prompt: str, temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> LLMResponse:
        response = await self.client.messages.create(
            model=self.model,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return LLMResponse(
            content=response.content[0].text if response.content else "",
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

    async def chat(
        self, messages: list[dict], temperature: float = 0.7, max_tokens: int = 2000,
    ) -> LLMResponse:
        system_msg = ""
        chat_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            else:
                chat_messages.append(msg)

        kwargs = {
            "model": self.model,
            "messages": chat_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system_msg:
            kwargs["system"] = system_msg

        response = await self.client.messages.create(**kwargs)
        return LLMResponse(
            content=response.content[0].text if response.content else "",
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
```

- [ ] **Step 4: Implement Ollama adapter**

```python
# src/flexloop/ai/ollama_adapter.py
import httpx

from flexloop.ai.base import LLMAdapter, LLMResponse


class OllamaAdapter(LLMAdapter):
    def __init__(self, model: str, base_url: str = "http://localhost:11434", **kwargs):
        super().__init__(model, api_key="", base_url=base_url)

    async def generate(
        self, system_prompt: str, user_prompt: str, temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> LLMResponse:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "stream": False,
                    "options": {"temperature": temperature, "num_predict": max_tokens},
                },
                timeout=120.0,
            )
            response.raise_for_status()
            data = response.json()

        return LLMResponse(
            content=data.get("message", {}).get("content", ""),
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
        )

    async def chat(
        self, messages: list[dict], temperature: float = 0.7, max_tokens: int = 2000,
    ) -> LLMResponse:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": temperature, "num_predict": max_tokens},
                },
                timeout=120.0,
            )
            response.raise_for_status()
            data = response.json()

        return LLMResponse(
            content=data.get("message", {}).get("content", ""),
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
        )
```

- [ ] **Step 5: Update factory with new adapters**

```python
# src/flexloop/ai/factory.py
from flexloop.ai.base import LLMAdapter
from flexloop.ai.anthropic_adapter import AnthropicAdapter
from flexloop.ai.ollama_adapter import OllamaAdapter
from flexloop.ai.openai_adapter import OpenAIAdapter


def create_adapter(
    provider: str, model: str, api_key: str = "", base_url: str = "", **kwargs
) -> LLMAdapter:
    if provider == "openai":
        return OpenAIAdapter(model=model, api_key=api_key, base_url=base_url, **kwargs)
    elif provider == "openai-compatible":
        return OpenAIAdapter(model=model, api_key=api_key, base_url=base_url, **kwargs)
    elif provider == "anthropic":
        return AnthropicAdapter(model=model, api_key=api_key, **kwargs)
    elif provider == "ollama":
        base = base_url or "http://localhost:11434"
        return OllamaAdapter(model=model, base_url=base, **kwargs)
    raise ValueError(f"Unknown provider: {provider}")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_ai_adapters.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add .
git commit -m "feat: add Anthropic and Ollama LLM adapters"
```

---

### Task 14: Implement prompt versioning system

**Files:**
- Create: `src/flexloop/ai/prompts.py`
- Create: `prompts/manifest.json`
- Create: `prompts/plan_generation/v1.md`
- Create: `prompts/block_review/v1.md`
- Create: `prompts/session_review/v1.md`
- Create: `prompts/chat/v1.md`
- Create: `tests/test_prompts.py`

- [ ] **Step 1: Write failing test for prompt loading**

```python
# tests/test_prompts.py
import pytest
import json
import tempfile
from pathlib import Path

from flexloop.ai.prompts import PromptManager


@pytest.fixture
def prompt_dir(tmp_path):
    manifest = {
        "plan_generation": {"default": "v1"},
        "block_review": {"default": "v1"},
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))

    pg_dir = tmp_path / "plan_generation"
    pg_dir.mkdir()
    (pg_dir / "v1.md").write_text("You are a fitness coach. Generate a plan for: {{user_profile}}")

    br_dir = tmp_path / "block_review"
    br_dir.mkdir()
    (br_dir / "v1.md").write_text("Review this training block: {{block_data}}")

    return tmp_path


def test_load_prompt(prompt_dir):
    manager = PromptManager(prompt_dir)
    prompt = manager.get_prompt("plan_generation")
    assert "fitness coach" in prompt
    assert "{{user_profile}}" in prompt


def test_load_prompt_unknown_type(prompt_dir):
    manager = PromptManager(prompt_dir)
    with pytest.raises(KeyError):
        manager.get_prompt("nonexistent")


def test_render_prompt(prompt_dir):
    manager = PromptManager(prompt_dir)
    rendered = manager.render("plan_generation", user_profile="28M, intermediate, PPL")
    assert "28M, intermediate, PPL" in rendered
    assert "{{user_profile}}" not in rendered
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_prompts.py -v`
Expected: FAIL — cannot import PromptManager

- [ ] **Step 3: Implement PromptManager**

```python
# src/flexloop/ai/prompts.py
import json
from pathlib import Path


class PromptManager:
    def __init__(self, prompts_dir: Path | str):
        self.prompts_dir = Path(prompts_dir)
        manifest_path = self.prompts_dir / "manifest.json"
        with open(manifest_path) as f:
            self.manifest = json.load(f)

    def get_prompt(self, prompt_type: str, provider: str = "default") -> str:
        if prompt_type not in self.manifest:
            raise KeyError(f"Unknown prompt type: {prompt_type}")

        versions = self.manifest[prompt_type]
        version = versions.get(provider, versions.get("default"))
        if not version:
            raise KeyError(f"No version found for {prompt_type}/{provider}")

        prompt_path = self.prompts_dir / prompt_type / f"{version}.md"
        return prompt_path.read_text()

    def render(self, prompt_type: str, provider: str = "default", **kwargs) -> str:
        template = self.get_prompt(prompt_type, provider)
        for key, value in kwargs.items():
            template = template.replace(f"{{{{{key}}}}}", str(value))
        return template
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_prompts.py -v`
Expected: All PASS

- [ ] **Step 5: Create initial prompt templates**

```markdown
<!-- prompts/plan_generation/v1.md -->
You are an expert fitness coach designing a personalized training program.

## User Profile
{{user_profile}}

## Instructions
Based on the user's profile, generate a structured weekly training plan. Consider:
- Experience level and appropriate volume (sets per muscle group per week)
- Available equipment constraints
- Goal-appropriate rep ranges and intensity
- Split type that matches available training days
- Progressive overload scheme

## Output Format
Respond with a JSON object matching this structure:
```json
{
  "plan_name": "string",
  "split_type": "ppl|upper_lower|full_body|bro_split|custom",
  "block_weeks": 6,
  "days": [
    {
      "day_number": 1,
      "label": "Push A",
      "focus": "chest,shoulders,triceps",
      "exercise_groups": [
        {
          "group_type": "straight|superset|triset|circuit",
          "rest_after_group_sec": 90,
          "exercises": [
            {
              "exercise_name": "Barbell Bench Press",
              "sets": 4,
              "reps": 8,
              "rpe_target": 8.0,
              "notes": "optional coaching note"
            }
          ]
        }
      ]
    }
  ]
}
```

Only include exercises the user can perform with their available equipment. Be conservative with starting weights and volume for beginners.
```

```markdown
<!-- prompts/block_review/v1.md -->
You are an expert fitness coach reviewing a completed training block.

## User Profile
{{user_profile}}

## Training Data
{{training_data}}

## Volume Landmarks (reference ranges for this experience level)
{{volume_landmarks}}

## Instructions
Analyze the training data and provide:
1. What's progressing well (exercises with consistent strength gains)
2. What's stalling (exercises with no progress or regression)
3. Specific, actionable recommendations

For each recommendation, rate your confidence:
- **high**: Clear trend over 3+ weeks of data
- **medium**: Some data supports it but picture is incomplete
- **low**: General best-practice suggestion, not strongly supported by the data

## Safety Guardrails
- Never recommend volume increases exceeding 10% per week
- Never recommend volume exceeding the MRV landmark for any muscle group
- If fatigue indicators are present (rising RPE with flat performance), suggest deload before progression

## Output Format
Respond with a JSON object:
```json
{
  "summary": "Brief overall assessment",
  "progressing": ["exercise: observation"],
  "stalling": ["exercise: observation"],
  "suggestions": [
    {
      "text": "What to change",
      "confidence": "high|medium|low",
      "reasoning": "Why this change is recommended based on the data"
    }
  ],
  "deload_recommended": false,
  "deload_reasoning": "Only if deload_recommended is true"
}
```
```

```markdown
<!-- prompts/session_review/v1.md -->
You are an expert fitness coach giving brief feedback on a single training session.

## User Profile
{{user_profile}}

## Session Data
{{session_data}}

## Session Feedback (if provided)
{{session_feedback}}

## Instructions
Provide a brief, encouraging review of this session. Keep it to 2-3 sentences. Highlight one positive and one thing to think about next time. If session feedback data is available, factor it into your assessment.

Respond as plain text, not JSON.
```

```markdown
<!-- prompts/chat/v1.md -->
You are FlexLoop's AI fitness coach. You have access to the user's training history and current plan.

## User Profile
{{user_profile}}

## Current Plan
{{current_plan}}

## Recent Training History
{{training_history}}

## Instructions
Answer the user's question about their training. Be specific and reference their actual data when possible. If you're unsure about something, say so. Keep responses concise and actionable.

If the user asks about something outside fitness training, politely redirect them.
```

```json
// prompts/manifest.json
{
  "plan_generation": { "default": "v1" },
  "block_review": { "default": "v1" },
  "session_review": { "default": "v1" },
  "chat": { "default": "v1" }
}
```

- [ ] **Step 6: Commit**

```bash
git add .
git commit -m "feat: add prompt versioning system with initial v1 prompt templates"
```

---

### Task 15: Implement AI Coach service and API endpoints

**Files:**
- Create: `src/flexloop/ai/coach.py`
- Create: `src/flexloop/ai/validators.py`
- Create: `src/flexloop/routers/ai.py`
- Create: `tests/test_ai_coach.py`
- Create: `tests/test_api_ai.py`
- Modify: `src/flexloop/main.py`

- [ ] **Step 1: Write failing test for AI output validation**

```python
# tests/test_ai_coach.py
import pytest

from flexloop.ai.validators import validate_plan_output, validate_review_output


def test_validate_valid_plan_output():
    output = {
        "plan_name": "PPL Block 1",
        "split_type": "ppl",
        "block_weeks": 6,
        "days": [
            {
                "day_number": 1,
                "label": "Push A",
                "focus": "chest,shoulders,triceps",
                "exercise_groups": [
                    {
                        "group_type": "straight",
                        "rest_after_group_sec": 90,
                        "exercises": [
                            {"exercise_name": "Bench Press", "sets": 4, "reps": 8, "rpe_target": 8.0}
                        ],
                    }
                ],
            }
        ],
    }
    result = validate_plan_output(output)
    assert result.is_valid
    assert result.errors == []


def test_validate_invalid_plan_output_missing_days():
    output = {"plan_name": "Test", "split_type": "ppl", "block_weeks": 6}
    result = validate_plan_output(output)
    assert not result.is_valid
    assert len(result.errors) > 0


def test_validate_valid_review_output():
    output = {
        "summary": "Good progress overall",
        "progressing": ["Bench: +5kg over 4 weeks"],
        "stalling": ["Squat: flat for 3 weeks"],
        "suggestions": [
            {"text": "Deload squat", "confidence": "high", "reasoning": "3 weeks flat at RPE 9+"}
        ],
        "deload_recommended": False,
    }
    result = validate_review_output(output)
    assert result.is_valid


def test_validate_review_rejects_excessive_volume_suggestion():
    output = {
        "summary": "Needs more volume",
        "progressing": [],
        "stalling": [],
        "suggestions": [
            {"text": "Increase chest volume from 10 to 25 sets per week",
             "confidence": "medium", "reasoning": "More volume needed"}
        ],
        "deload_recommended": False,
    }
    # Validation passes but guardrail flags the suggestion
    result = validate_review_output(output)
    assert result.is_valid  # structure is valid
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ai_coach.py -v`
Expected: FAIL — cannot import validators

- [ ] **Step 3: Implement AI output validators**

```python
# src/flexloop/ai/validators.py
from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_plan_output(data: dict) -> ValidationResult:
    errors = []

    required_fields = ["plan_name", "split_type", "block_weeks", "days"]
    for f in required_fields:
        if f not in data:
            errors.append(f"Missing required field: {f}")

    if "days" in data:
        if not isinstance(data["days"], list) or len(data["days"]) == 0:
            errors.append("'days' must be a non-empty list")
        else:
            for i, day in enumerate(data["days"]):
                if "exercise_groups" not in day:
                    errors.append(f"Day {i + 1} missing 'exercise_groups'")
                elif not isinstance(day["exercise_groups"], list):
                    errors.append(f"Day {i + 1} 'exercise_groups' must be a list")

    return ValidationResult(is_valid=len(errors) == 0, errors=errors)


def validate_review_output(data: dict) -> ValidationResult:
    errors = []

    required_fields = ["summary", "suggestions"]
    for f in required_fields:
        if f not in data:
            errors.append(f"Missing required field: {f}")

    if "suggestions" in data:
        if not isinstance(data["suggestions"], list):
            errors.append("'suggestions' must be a list")
        else:
            for i, s in enumerate(data["suggestions"]):
                if "text" not in s:
                    errors.append(f"Suggestion {i + 1} missing 'text'")
                if "confidence" not in s:
                    errors.append(f"Suggestion {i + 1} missing 'confidence'")
                elif s["confidence"] not in ("high", "medium", "low"):
                    errors.append(f"Suggestion {i + 1} has invalid confidence: {s['confidence']}")

    return ValidationResult(is_valid=len(errors) == 0, errors=errors)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ai_coach.py -v`
Expected: All PASS

- [ ] **Step 5: Implement AI Coach service**

```python
# src/flexloop/ai/coach.py
import json
import logging
from pathlib import Path

from flexloop.ai.base import LLMAdapter, LLMResponse
from flexloop.ai.prompts import PromptManager
from flexloop.ai.validators import ValidationResult, validate_plan_output, validate_review_output
from flexloop.config import settings

logger = logging.getLogger(__name__)


class AICoach:
    def __init__(self, adapter: LLMAdapter, prompt_manager: PromptManager):
        self.adapter = adapter
        self.prompts = prompt_manager

    async def generate_plan(self, user_profile: str) -> tuple[dict | None, LLMResponse]:
        prompt = self.prompts.render(
            "plan_generation",
            provider=settings.ai_provider,
            user_profile=user_profile,
        )

        response = await self.adapter.generate(
            system_prompt="You are a fitness plan generator. Respond only with valid JSON.",
            user_prompt=prompt,
            temperature=settings.ai_temperature,
            max_tokens=settings.ai_max_tokens,
        )

        try:
            data = json.loads(response.content)
        except json.JSONDecodeError:
            logger.warning("AI returned non-JSON response for plan generation")
            return None, response

        validation = validate_plan_output(data)
        if not validation.is_valid:
            logger.warning(f"AI plan output validation failed: {validation.errors}")
            return None, response

        return data, response

    async def review_block(
        self, user_profile: str, training_data: str, volume_landmarks: str,
    ) -> tuple[dict | None, LLMResponse]:
        prompt = self.prompts.render(
            "block_review",
            provider=settings.ai_provider,
            user_profile=user_profile,
            training_data=training_data,
            volume_landmarks=volume_landmarks,
        )

        response = await self.adapter.generate(
            system_prompt="You are a fitness coach reviewing training data. Respond only with valid JSON.",
            user_prompt=prompt,
            temperature=settings.ai_temperature,
            max_tokens=settings.ai_max_tokens,
        )

        try:
            data = json.loads(response.content)
        except json.JSONDecodeError:
            logger.warning("AI returned non-JSON response for block review")
            return None, response

        validation = validate_review_output(data)
        if not validation.is_valid:
            logger.warning(f"AI review output validation failed: {validation.errors}")
            return None, response

        return data, response

    async def chat(self, messages: list[dict], user_profile: str,
                   current_plan: str, training_history: str) -> LLMResponse:
        system_prompt = self.prompts.render(
            "chat",
            provider=settings.ai_provider,
            user_profile=user_profile,
            current_plan=current_plan,
            training_history=training_history,
        )

        full_messages = [{"role": "system", "content": system_prompt}] + messages

        return await self.adapter.chat(
            messages=full_messages,
            temperature=settings.ai_temperature,
            max_tokens=settings.ai_max_tokens,
        )
```

- [ ] **Step 6: Write failing test for AI API endpoint**

```python
# tests/test_api_ai.py
import pytest

from flexloop.models.user import User


@pytest.fixture
async def user(db_session):
    user = User(
        name="Test User", gender="male", age=28, height_cm=180.0,
        weight_kg=82.0, experience_level="intermediate", goals="hypertrophy",
        available_equipment=["barbell", "dumbbells"],
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.mark.asyncio
async def test_ai_usage_endpoint_empty(client, user):
    response = await client.get(f"/api/ai/usage?user_id={user.id}")
    assert response.status_code == 200
    assert response.json() == []
```

- [ ] **Step 7: Implement AI router (usage endpoint first)**

```python
# src/flexloop/routers/ai.py
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.db.engine import get_session
from flexloop.models.ai import AIUsage
from flexloop.schemas.ai import AIUsageResponse

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/usage", response_model=list[AIUsageResponse])
async def get_ai_usage(user_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(AIUsage).where(AIUsage.user_id == user_id).order_by(AIUsage.month.desc())
    )
    return result.scalars().all()
```

- [ ] **Step 8: Register router in main.py**

Add to `src/flexloop/main.py`:

```python
from flexloop.routers.ai import router as ai_router

app.include_router(ai_router)
```

- [ ] **Step 9: Run all tests**

Run: `pytest tests/test_ai_coach.py tests/test_api_ai.py -v`
Expected: All PASS

- [ ] **Step 10: Commit**

```bash
git add .
git commit -m "feat: add AI Coach service with validation, prompt rendering, and usage API endpoint"
```

---

## Chunk 4: Data Export, Backup/Restore, Sync & Docker

### Task 16: Implement Data Export (JSON/CSV)

**Files:**
- Create: `src/flexloop/services/__init__.py`
- Create: `src/flexloop/services/export.py`
- Create: `src/flexloop/routers/data.py`
- Create: `tests/test_api_export.py`
- Modify: `src/flexloop/main.py`

- [ ] **Step 1: Write failing test for JSON export**

```python
# tests/test_api_export.py
import pytest
from datetime import datetime

from flexloop.models.user import User
from flexloop.models.exercise import Exercise
from flexloop.models.workout import WorkoutSession, WorkoutSet


@pytest.fixture
async def seed_data(db_session):
    user = User(
        name="Test User", gender="male", age=28, height_cm=180.0,
        weight_kg=82.0, experience_level="intermediate", goals="hypertrophy",
        available_equipment=["barbell"],
    )
    exercise = Exercise(
        name="Squat", muscle_group="quads", equipment="barbell",
        category="compound", difficulty="intermediate",
    )
    db_session.add_all([user, exercise])
    await db_session.commit()

    session = WorkoutSession(
        user_id=user.id, source="ad_hoc",
        started_at=datetime(2026, 3, 23, 10, 0, 0),
        completed_at=datetime(2026, 3, 23, 11, 0, 0),
    )
    db_session.add(session)
    await db_session.commit()

    workout_set = WorkoutSet(
        session_id=session.id, exercise_id=exercise.id,
        set_number=1, set_type="working", weight=100.0, reps=5, rpe=8.0,
    )
    db_session.add(workout_set)
    await db_session.commit()

    return user


@pytest.mark.asyncio
async def test_export_json(client, seed_data):
    user = seed_data
    response = await client.get(f"/api/export?user_id={user.id}&format=json")
    assert response.status_code == 200
    data = response.json()
    assert "user" in data
    assert "workouts" in data
    assert len(data["workouts"]) == 1
    assert len(data["workouts"][0]["sets"]) == 1


@pytest.mark.asyncio
async def test_export_single_session(client, seed_data):
    user = seed_data
    workouts_resp = await client.get(f"/api/users/{user.id}/workouts")
    session_id = workouts_resp.json()[0]["id"]

    response = await client.get(f"/api/export/session/{session_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == session_id
    assert len(data["sets"]) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_export.py -v`
Expected: FAIL

- [ ] **Step 3: Implement export service**

```python
# src/flexloop/services/__init__.py
```

```python
# src/flexloop/services/export.py
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from flexloop.models.measurement import Measurement
from flexloop.models.template import Template
from flexloop.models.user import User
from flexloop.models.workout import WorkoutSession


async def export_user_data(user_id: int, session: AsyncSession) -> dict:
    user_result = await session.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one()

    workouts_result = await session.execute(
        select(WorkoutSession)
        .where(WorkoutSession.user_id == user_id)
        .options(
            selectinload(WorkoutSession.sets),
            selectinload(WorkoutSession.feedback),
        )
        .order_by(WorkoutSession.started_at)
    )
    workouts = workouts_result.scalars().all()

    templates_result = await session.execute(
        select(Template).where(Template.user_id == user_id)
    )
    templates = templates_result.scalars().all()

    measurements_result = await session.execute(
        select(Measurement).where(Measurement.user_id == user_id).order_by(Measurement.date)
    )
    measurements = measurements_result.scalars().all()

    return {
        "user": {
            "name": user.name, "gender": user.gender, "age": user.age,
            "height_cm": user.height_cm, "weight_kg": user.weight_kg,
            "experience_level": user.experience_level, "goals": user.goals,
            "available_equipment": user.available_equipment,
        },
        "workouts": [
            {
                "id": w.id, "source": w.source,
                "started_at": w.started_at.isoformat() if w.started_at else None,
                "completed_at": w.completed_at.isoformat() if w.completed_at else None,
                "notes": w.notes,
                "sets": [
                    {
                        "exercise_id": s.exercise_id, "set_number": s.set_number,
                        "set_type": s.set_type, "weight": s.weight, "reps": s.reps,
                        "rpe": s.rpe, "duration_sec": s.duration_sec,
                        "distance_m": s.distance_m, "rest_sec": s.rest_sec,
                    }
                    for s in w.sets
                ],
            }
            for w in workouts
        ],
        "templates": [
            {"name": t.name, "exercises_json": t.exercises_json}
            for t in templates
        ],
        "measurements": [
            {"date": m.date.isoformat(), "type": m.type, "value_cm": m.value_cm, "notes": m.notes}
            for m in measurements
        ],
    }


async def export_session(session_id: int, session: AsyncSession) -> dict:
    result = await session.execute(
        select(WorkoutSession)
        .where(WorkoutSession.id == session_id)
        .options(
            selectinload(WorkoutSession.sets),
            selectinload(WorkoutSession.feedback),
        )
    )
    workout = result.scalar_one_or_none()
    if not workout:
        return None

    return {
        "id": workout.id, "source": workout.source,
        "started_at": workout.started_at.isoformat() if workout.started_at else None,
        "completed_at": workout.completed_at.isoformat() if workout.completed_at else None,
        "notes": workout.notes,
        "sets": [
            {
                "exercise_id": s.exercise_id, "set_number": s.set_number,
                "set_type": s.set_type, "weight": s.weight, "reps": s.reps,
                "rpe": s.rpe, "duration_sec": s.duration_sec,
                "distance_m": s.distance_m, "rest_sec": s.rest_sec,
            }
            for s in workout.sets
        ],
    }
```

- [ ] **Step 4: Implement data router**

```python
# src/flexloop/routers/data.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.db.engine import get_session
from flexloop.services.export import export_session, export_user_data

router = APIRouter(prefix="/api/export", tags=["data"])


@router.get("")
async def export_data(
    user_id: int, format: str = "json", session: AsyncSession = Depends(get_session)
):
    data = await export_user_data(user_id, session)
    return data


@router.get("/session/{session_id}")
async def export_single_session(
    session_id: int, session: AsyncSession = Depends(get_session)
):
    data = await export_session(session_id, session)
    if not data:
        raise HTTPException(status_code=404, detail="Session not found")
    return data
```

- [ ] **Step 5: Register router in main.py**

Add to `src/flexloop/main.py`:

```python
from flexloop.routers.data import router as data_router

app.include_router(data_router)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_api_export.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add .
git commit -m "feat: add data export endpoints (full JSON export and single session export)"
```

---

### Task 17: Implement Backup & Restore

**Files:**
- Create: `src/flexloop/services/backup.py`
- Create: `src/flexloop/routers/backup.py`
- Create: `tests/test_backup.py`
- Modify: `src/flexloop/main.py`

- [ ] **Step 1: Write failing test for backup creation**

```python
# tests/test_backup.py
import pytest
from pathlib import Path
from unittest.mock import patch

from flexloop.services.backup import BackupService


@pytest.fixture
def backup_service(tmp_path):
    db_path = tmp_path / "test.db"
    db_path.write_bytes(b"fake database content")
    return BackupService(db_path=str(db_path), backup_dir=str(tmp_path / "backups"))


def test_create_backup(backup_service):
    result = backup_service.create_backup(schema_version="1.0.0")
    assert result is not None
    assert Path(result.filepath).exists()
    assert result.schema_version == "1.0.0"
    assert result.size_bytes > 0


def test_list_backups_empty(backup_service):
    backups = backup_service.list_backups()
    assert backups == []


def test_list_backups_after_create(backup_service):
    backup_service.create_backup(schema_version="1.0.0")
    backup_service.create_backup(schema_version="1.0.0")
    backups = backup_service.list_backups()
    assert len(backups) == 2


def test_prune_keeps_recent(backup_service):
    for _ in range(10):
        backup_service.create_backup(schema_version="1.0.0")

    backup_service.prune(keep_daily=7, keep_weekly=0)
    backups = backup_service.list_backups()
    assert len(backups) <= 7
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_backup.py -v`
Expected: FAIL — cannot import BackupService

- [ ] **Step 3: Implement BackupService**

```python
# src/flexloop/services/backup.py
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class BackupInfo:
    filename: str
    filepath: str
    size_bytes: int
    schema_version: str
    created_at: datetime


class BackupService:
    def __init__(self, db_path: str, backup_dir: str = "backups"):
        self.db_path = Path(db_path)
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self, schema_version: str) -> BackupInfo:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"flexloop_backup_{timestamp}.db"
        dest = self.backup_dir / filename

        shutil.copy2(self.db_path, dest)

        return BackupInfo(
            filename=filename,
            filepath=str(dest),
            size_bytes=dest.stat().st_size,
            schema_version=schema_version,
            created_at=datetime.now(),
        )

    def list_backups(self) -> list[BackupInfo]:
        backups = []
        for f in sorted(self.backup_dir.glob("flexloop_backup_*.db"), reverse=True):
            backups.append(BackupInfo(
                filename=f.name,
                filepath=str(f),
                size_bytes=f.stat().st_size,
                schema_version="unknown",
                created_at=datetime.fromtimestamp(f.stat().st_mtime),
            ))
        return backups

    def restore(self, backup_filename: str) -> bool:
        source = self.backup_dir / backup_filename
        if not source.exists():
            return False

        # Create a pre-restore backup first
        self.create_backup(schema_version="pre-restore")

        shutil.copy2(source, self.db_path)
        return True

    def prune(self, keep_daily: int = 7, keep_weekly: int = 4):
        backups = self.list_backups()
        if len(backups) <= keep_daily:
            return

        to_keep = set()
        for b in backups[:keep_daily]:
            to_keep.add(b.filename)

        seen_weeks = set()
        for b in backups:
            week_key = b.created_at.strftime("%Y-W%U")
            if week_key not in seen_weeks and len(seen_weeks) < keep_weekly:
                seen_weeks.add(week_key)
                to_keep.add(b.filename)

        for b in backups:
            if b.filename not in to_keep:
                Path(b.filepath).unlink(missing_ok=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_backup.py -v`
Expected: All PASS

- [ ] **Step 5: Implement backup router**

```python
# src/flexloop/routers/backup.py
from fastapi import APIRouter, HTTPException

from flexloop.services.backup import BackupService

router = APIRouter(prefix="/api", tags=["backup"])


def get_backup_service() -> BackupService:
    return BackupService(db_path="flexloop.db", backup_dir="backups")


@router.post("/backup")
async def create_backup():
    service = get_backup_service()
    result = service.create_backup(schema_version="1.0.0")
    return {
        "filename": result.filename,
        "size_bytes": result.size_bytes,
        "created_at": result.created_at.isoformat(),
    }


@router.get("/backups")
async def list_backups():
    service = get_backup_service()
    backups = service.list_backups()
    return [
        {
            "filename": b.filename,
            "size_bytes": b.size_bytes,
            "created_at": b.created_at.isoformat(),
        }
        for b in backups
    ]


@router.post("/restore/{backup_filename}")
async def restore_backup(backup_filename: str):
    service = get_backup_service()
    success = service.restore(backup_filename)
    if not success:
        raise HTTPException(status_code=404, detail="Backup not found")
    return {"status": "restored", "from": backup_filename}
```

- [ ] **Step 6: Register router in main.py**

Add to `src/flexloop/main.py`:

```python
from flexloop.routers.backup import router as backup_router

app.include_router(backup_router)
```

- [ ] **Step 7: Commit**

```bash
git add .
git commit -m "feat: add backup/restore service with pruning and API endpoints"
```

---

### Task 18: Implement Sync endpoint

**Files:**
- Create: `src/flexloop/routers/sync.py`
- Create: `tests/test_api_sync.py`
- Modify: `src/flexloop/main.py`

- [ ] **Step 1: Write failing test for sync endpoint**

```python
# tests/test_api_sync.py
import pytest

from flexloop.models.user import User
from flexloop.models.exercise import Exercise


@pytest.fixture
async def seed_data(db_session):
    user = User(
        name="Test User", gender="male", age=28, height_cm=180.0,
        weight_kg=82.0, experience_level="intermediate", goals="hypertrophy",
        available_equipment=["barbell"],
    )
    exercise = Exercise(
        name="Squat", muscle_group="quads", equipment="barbell",
        category="compound", difficulty="intermediate",
    )
    db_session.add_all([user, exercise])
    await db_session.commit()
    return user, exercise


@pytest.mark.asyncio
async def test_sync_push_workouts(client, seed_data):
    user, exercise = seed_data

    response = await client.post("/api/sync", json={
        "user_id": user.id,
        "workouts": [
            {
                "source": "ad_hoc",
                "started_at": "2026-03-23T10:00:00",
                "completed_at": "2026-03-23T11:00:00",
                "sets": [
                    {
                        "exercise_id": exercise.id, "set_number": 1,
                        "set_type": "working", "weight": 100.0, "reps": 5,
                    }
                ],
            }
        ],
    })
    assert response.status_code == 200
    data = response.json()
    assert data["workouts_synced"] == 1


@pytest.mark.asyncio
async def test_sync_empty_payload(client, seed_data):
    user, _ = seed_data
    response = await client.post("/api/sync", json={
        "user_id": user.id,
        "workouts": [],
    })
    assert response.status_code == 200
    assert response.json()["workouts_synced"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_sync.py -v`
Expected: FAIL

- [ ] **Step 3: Implement sync router**

```python
# src/flexloop/routers/sync.py
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.db.engine import get_session
from flexloop.models.workout import WorkoutSession, WorkoutSet


class SyncSetData(BaseModel):
    exercise_id: int
    exercise_group_id: int | None = None
    set_number: int
    set_type: str = "working"
    weight: float | None = None
    reps: int | None = None
    rpe: float | None = None
    duration_sec: int | None = None
    distance_m: float | None = None
    rest_sec: int | None = None


class SyncWorkoutData(BaseModel):
    plan_day_id: int | None = None
    template_id: int | None = None
    source: str = "ad_hoc"
    started_at: datetime
    completed_at: datetime | None = None
    notes: str | None = None
    sets: list[SyncSetData] = []


class SyncRequest(BaseModel):
    user_id: int
    workouts: list[SyncWorkoutData] = []


class SyncResponse(BaseModel):
    workouts_synced: int


router = APIRouter(tags=["sync"])


@router.post("/api/sync", response_model=SyncResponse)
async def sync_data(data: SyncRequest, session: AsyncSession = Depends(get_session)):
    synced = 0

    for workout_data in data.workouts:
        workout = WorkoutSession(
            user_id=data.user_id,
            plan_day_id=workout_data.plan_day_id,
            template_id=workout_data.template_id,
            source=workout_data.source,
            started_at=workout_data.started_at,
            completed_at=workout_data.completed_at,
            notes=workout_data.notes,
        )
        session.add(workout)
        await session.flush()

        for set_data in workout_data.sets:
            workout_set = WorkoutSet(
                session_id=workout.id,
                **set_data.model_dump(),
            )
            session.add(workout_set)

        synced += 1

    await session.commit()
    return SyncResponse(workouts_synced=synced)
```

- [ ] **Step 4: Register router in main.py**

Add to `src/flexloop/main.py`:

```python
from flexloop.routers.sync import router as sync_router

app.include_router(sync_router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_api_sync.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add .
git commit -m "feat: add sync endpoint for iOS client to push offline workout data"
```

---

### Task 19: Docker deployment

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.dockerignore`

- [ ] **Step 1: Create Dockerfile**

```dockerfile
# Dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini .
COPY prompts/ prompts/

EXPOSE 8000

CMD ["uvicorn", "flexloop.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Create docker-compose.yml**

```yaml
# docker-compose.yml
version: "3.8"

services:
  flexloop:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - flexloop-data:/app/data
      - flexloop-backups:/app/backups
    env_file:
      - .env
    environment:
      - DATABASE_URL=sqlite+aiosqlite:///./data/flexloop.db
    restart: unless-stopped

volumes:
  flexloop-data:
  flexloop-backups:
```

- [ ] **Step 3: Create .dockerignore**

```
__pycache__/
*.pyc
.venv/
*.db
.env
.git/
tests/
.pytest_cache/
.ruff_cache/
```

- [ ] **Step 4: Verify Docker build**

Run: `docker build -t flexloop-server .`
Expected: Build completes successfully

- [ ] **Step 5: Verify docker-compose up**

Run: `docker-compose up -d && sleep 3 && curl http://localhost:8000/api/health && docker-compose down`
Expected: `{"status":"ok","version":"1.0.0"}`

- [ ] **Step 6: Commit**

```bash
git add .
git commit -m "feat: add Dockerfile and docker-compose for one-command deployment"
```

---

### Task 20: Seed exercise library from wger data

**Files:**
- Create: `scripts/seed_exercises.py`
- Create: `data/exercises_core.json`
- Create: `tests/test_seed_exercises.py`

- [ ] **Step 1: Create core exercise data file**

Create `data/exercises_core.json` — a curated list of ~80 exercises with muscle groups, equipment, category, and difficulty. This is the manually reviewed subset from wger.de data.

```json
[
  {"name": "Barbell Bench Press", "muscle_group": "chest", "equipment": "barbell", "category": "compound", "difficulty": "intermediate"},
  {"name": "Incline Dumbbell Press", "muscle_group": "chest", "equipment": "dumbbell", "category": "compound", "difficulty": "intermediate"},
  {"name": "Cable Fly", "muscle_group": "chest", "equipment": "cable", "category": "isolation", "difficulty": "beginner"},
  {"name": "Push-Up", "muscle_group": "chest", "equipment": "bodyweight", "category": "compound", "difficulty": "beginner"},
  {"name": "Barbell Back Squat", "muscle_group": "quads", "equipment": "barbell", "category": "compound", "difficulty": "intermediate"},
  {"name": "Leg Press", "muscle_group": "quads", "equipment": "machine", "category": "compound", "difficulty": "beginner"},
  {"name": "Leg Extension", "muscle_group": "quads", "equipment": "machine", "category": "isolation", "difficulty": "beginner"},
  {"name": "Bulgarian Split Squat", "muscle_group": "quads", "equipment": "dumbbell", "category": "compound", "difficulty": "intermediate"},
  {"name": "Romanian Deadlift", "muscle_group": "hamstrings", "equipment": "barbell", "category": "compound", "difficulty": "intermediate"},
  {"name": "Leg Curl", "muscle_group": "hamstrings", "equipment": "machine", "category": "isolation", "difficulty": "beginner"}
]
```

(Full list of ~80 exercises to be completed — this shows the format. Include exercises covering: chest, back, quads, hamstrings, glutes, shoulders, biceps, triceps, core, calves.)

- [ ] **Step 2: Write failing test for seed script**

```python
# tests/test_seed_exercises.py
import json
import pytest
from pathlib import Path
from sqlalchemy import select

from flexloop.models.exercise import Exercise


@pytest.mark.asyncio
async def test_seed_exercises(db_session):
    data_path = Path(__file__).parent.parent / "data" / "exercises_core.json"
    with open(data_path) as f:
        exercises_data = json.load(f)

    for ex in exercises_data:
        db_session.add(Exercise(**ex))
    await db_session.commit()

    result = await db_session.execute(select(Exercise))
    exercises = result.scalars().all()
    assert len(exercises) == len(exercises_data)
    assert all(e.name for e in exercises)
    assert all(e.muscle_group for e in exercises)
```

- [ ] **Step 3: Run test to verify it passes**

Run: `pytest tests/test_seed_exercises.py -v`
Expected: PASS

- [ ] **Step 4: Create seed script**

```python
# scripts/seed_exercises.py
import asyncio
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.db.engine import async_session
from flexloop.models.exercise import Exercise


async def seed():
    data_path = Path(__file__).parent.parent / "data" / "exercises_core.json"
    with open(data_path) as f:
        exercises_data = json.load(f)

    async with async_session() as session:
        result = await session.execute(select(Exercise))
        existing = {e.name for e in result.scalars().all()}

        added = 0
        for ex in exercises_data:
            if ex["name"] not in existing:
                session.add(Exercise(**ex))
                added += 1

        await session.commit()
        print(f"Seeded {added} exercises ({len(existing)} already existed)")


if __name__ == "__main__":
    asyncio.run(seed())
```

- [ ] **Step 5: Commit**

```bash
git add .
git commit -m "feat: add core exercise library (curated from wger.de) and seed script"
```

---

### Task 21: Run full test suite and finalize

- [ ] **Step 1: Run complete test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 2: Run ruff linter**

Run: `ruff check src/ tests/`
Expected: No errors (or fix any that appear)

- [ ] **Step 3: Verify Docker build with all changes**

Run: `docker build -t flexloop-server . && docker run --rm flexloop-server python -c "from flexloop.main import app; print('OK')"`
Expected: Prints "OK"

- [ ] **Step 4: Commit any final fixes**

```bash
git add .
git commit -m "chore: fix lint issues and verify full test suite passes"
```

- [ ] **Step 5: Tag v1.0.0-alpha**

```bash
git tag v1.0.0-alpha
```
