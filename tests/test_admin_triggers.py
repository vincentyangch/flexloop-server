"""Integration tests for /api/admin/triggers."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from httpx import AsyncClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.ext.asyncio import AsyncSession

import flexloop.models  # noqa: F401
from flexloop.admin.auth import SESSION_COOKIE_NAME, create_session, hash_password
from flexloop.config import settings
from flexloop.db.base import Base
from flexloop.models.admin_session import AdminSession
from flexloop.models.admin_user import AdminUser
from flexloop.models.ai import AIUsage
from flexloop.models.exercise import Exercise
from flexloop.models.personal_record import PersonalRecord
from flexloop.models.user import User
from flexloop.models.workout import WorkoutSession, WorkoutSet


ORIGIN = {"Origin": "http://localhost:5173"}
BACKUP_DIR = Path("backups")


@pytest.fixture(autouse=True)
def _trigger_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "flexloop.db"
    sqlite3.connect(db_path).close()
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{db_path}")


async def _cookie(db: AsyncSession) -> dict[str, str]:
    admin = AdminUser(username="t", password_hash=hash_password("password123"))
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    token, _ = await create_session(db, admin_user_id=admin.id)
    return {SESSION_COOKIE_NAME: token}


async def _user(db: AsyncSession, *, name: str = "Trigger User") -> User:
    user = User(
        name=name,
        gender="other",
        age=30,
        height=170,
        weight=70,
        weight_unit="kg",
        height_unit="cm",
        experience_level="intermediate",
        goals="",
        available_equipment=[],
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _alembic_head() -> str:
    return ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()


def _prepare_migration_db(db_path: Path) -> None:
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        Base.metadata.create_all(engine)
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"))
            conn.execute(text("DELETE FROM alembic_version"))
            conn.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:version_num)"),
                {"version_num": _alembic_head()},
            )
    finally:
        engine.dispose()


class TestTriggerAuth:
    """All non-streaming trigger endpoints require admin auth."""

    async def test_reseed_auth(self, client: AsyncClient) -> None:
        assert (
            await client.post("/api/admin/triggers/reseed-exercises", headers=ORIGIN)
        ).status_code == 401

    async def test_migrations_auth(self, client: AsyncClient) -> None:
        assert (
            await client.post("/api/admin/triggers/run-migrations", headers=ORIGIN)
        ).status_code == 401

    async def test_backup_auth(self, client: AsyncClient) -> None:
        assert (
            await client.post("/api/admin/triggers/backup", headers=ORIGIN)
        ).status_code == 401

    async def test_test_ai_auth(self, client: AsyncClient) -> None:
        assert (
            await client.post("/api/admin/triggers/test-ai", headers=ORIGIN)
        ).status_code == 401

    async def test_reload_prompts_auth(self, client: AsyncClient) -> None:
        assert (
            await client.post("/api/admin/triggers/reload-prompts", headers=ORIGIN)
        ).status_code == 401

    async def test_vacuum_auth(self, client: AsyncClient) -> None:
        assert (
            await client.post("/api/admin/triggers/vacuum-db", headers=ORIGIN)
        ).status_code == 401

    async def test_clear_sessions_auth(self, client: AsyncClient) -> None:
        assert (
            await client.post("/api/admin/triggers/clear-sessions", headers=ORIGIN)
        ).status_code == 401

    async def test_clear_ai_usage_auth(self, client: AsyncClient) -> None:
        assert (
            await client.post("/api/admin/triggers/clear-ai-usage", headers=ORIGIN)
        ).status_code == 401


class TestReloadPrompts:
    async def test_reload(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        res = await client.post(
            "/api/admin/triggers/reload-prompts",
            cookies=cookies,
            headers=ORIGIN,
        )
        assert res.status_code == 200
        assert res.json() == {"status": "ok", "message": "Prompt cache cleared"}


class TestBackupTrigger:
    async def test_creates_backup(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        res = await client.post(
            "/api/admin/triggers/backup",
            cookies=cookies,
            headers=ORIGIN,
        )
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "ok"
        assert body["filename"].startswith("flexloop_backup_")
        assert (BACKUP_DIR / body["filename"]).exists()


class TestTestAi:
    async def test_returns_result(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        cookies = await _cookie(db_session)
        monkeypatch.setattr(settings, "codex_auth_file", "/tmp/trigger-auth.json")
        monkeypatch.setattr(settings, "ai_reasoning_effort", "high")
        captured: dict[str, object] = {}

        class FakeAdapter:
            async def generate(self, **_: object) -> SimpleNamespace:
                return SimpleNamespace(content="hello")

        monkeypatch.setattr(
            "flexloop.ai.factory.create_adapter",
            lambda **kwargs: captured.update(kwargs) or FakeAdapter(),
        )

        res = await client.post(
            "/api/admin/triggers/test-ai",
            cookies=cookies,
            headers=ORIGIN,
        )
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "ok"
        assert body["response_text"] == "hello"
        assert isinstance(body["latency_ms"], int)
        assert captured["codex_auth_file"] == "/tmp/trigger-auth.json"
        assert captured["reasoning_effort"] == "high"


class TestRunMigrations:
    async def test_runs_alembic(
        self, client: AsyncClient, db_session: AsyncSession, tmp_path: Path
    ) -> None:
        cookies = await _cookie(db_session)
        db_path = tmp_path / "flexloop.db"
        _prepare_migration_db(db_path)

        res = await client.post(
            "/api/admin/triggers/run-migrations",
            cookies=cookies,
            headers=ORIGIN,
        )
        assert res.status_code == 200
        assert res.json()["status"] == "ok"

        conn = sqlite3.connect(db_path)
        try:
            version = conn.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone()
        finally:
            conn.close()

        assert version == (_alembic_head(),)


class TestReseedExercises:
    async def test_updates_matching_exercises(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        exercise = Exercise(
            name="Barbell Bench Press",
            muscle_group="chest",
            equipment="barbell",
            category="compound",
            difficulty="intermediate",
            metadata_json=None,
        )
        db_session.add(exercise)
        await db_session.commit()
        await db_session.refresh(exercise)

        res = await client.post(
            "/api/admin/triggers/reseed-exercises",
            cookies=cookies,
            headers=ORIGIN,
        )
        assert res.status_code == 200
        assert res.json() == {"status": "ok", "updated": 1}

        await db_session.refresh(exercise)
        assert exercise.metadata_json is not None
        assert "description" in exercise.metadata_json


class TestVacuumDb:
    async def test_vacuum(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        res = await client.post(
            "/api/admin/triggers/vacuum-db",
            cookies=cookies,
            headers=ORIGIN,
        )
        assert res.status_code == 200
        assert res.json()["status"] == "ok"


class TestClearSessions:
    async def test_clears_all_and_invalidates_current_session(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)

        before = await db_session.execute(select(AdminSession))
        assert len(before.scalars().all()) == 1

        res = await client.post(
            "/api/admin/triggers/clear-sessions",
            cookies=cookies,
            headers=ORIGIN,
        )
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "ok"
        assert body["deleted"] >= 1

        follow_up = await client.get("/api/admin/auth/me", cookies=cookies)
        assert follow_up.status_code == 401


class TestClearAiUsage:
    async def test_clears_all(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        user = await _user(db_session)
        db_session.add(
            AIUsage(
                user_id=user.id,
                month="2026-04",
                total_input_tokens=100,
                total_output_tokens=200,
                estimated_cost=1.23,
                call_count=4,
            )
        )
        await db_session.commit()

        res = await client.post(
            "/api/admin/triggers/clear-ai-usage",
            cookies=cookies,
            headers=ORIGIN,
        )
        assert res.status_code == 200
        assert res.json() == {"status": "ok", "deleted": 1}


class TestRecomputePrs:
    async def test_auth(self, client: AsyncClient) -> None:
        assert (
            await client.post("/api/admin/triggers/recompute-prs", headers=ORIGIN)
        ).status_code == 401

    async def test_returns_sse_and_recomputes_prs(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        user = await _user(db_session)
        exercise = Exercise(
            name="Barbell Back Squat",
            muscle_group="quads",
            equipment="barbell",
            category="compound",
            difficulty="intermediate",
        )
        db_session.add(exercise)
        await db_session.commit()
        await db_session.refresh(exercise)

        session = WorkoutSession(
            user_id=user.id,
            source="plan",
            started_at=datetime.utcnow(),
        )
        db_session.add(session)
        await db_session.commit()
        await db_session.refresh(session)

        db_session.add(
            WorkoutSet(
                session_id=session.id,
                exercise_id=exercise.id,
                set_number=1,
                set_type="working",
                weight=100.0,
                reps=5,
            )
        )
        await db_session.commit()

        async with client.stream(
            "POST",
            "/api/admin/triggers/recompute-prs",
            cookies=cookies,
            headers=ORIGIN,
        ) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")
            text = "".join([chunk async for chunk in response.aiter_text()])

        blocks = [block.strip() for block in text.split("\n\n") if block.strip()]
        events = [
            json.loads(block.removeprefix("data:").strip())
            for block in blocks
            if block.startswith("data:")
        ]

        progress = [event for event in events if event.get("type") == "progress"]
        done = [event for event in events if event.get("type") == "done"]

        assert progress
        assert done
        assert done[-1]["result"]["sets_checked"] == 1
        assert done[-1]["result"]["new_prs"] >= 1

        records = await db_session.execute(
            select(PersonalRecord).where(PersonalRecord.user_id == user.id)
        )
        assert len(records.scalars().all()) >= 1
