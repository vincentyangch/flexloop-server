"""Unit tests for flexloop.config.refresh_settings_from_db."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.config import _DB_BACKED_FIELDS, refresh_settings_from_db, settings
from flexloop.models.app_settings import AppSettings


@pytest.fixture(autouse=True)
def _restore_settings_singleton():
    """Snapshot the runtime-mutable fields on ``settings`` before each test
    and restore them on teardown.

    Prevents state leakage between tests — especially important because
    ``test_mutates_singleton_from_row`` writes values like
    ``admin_allowed_origins=["https://admin.example.com"]`` that would
    otherwise block future admin write tests at the CSRF layer.
    """
    snapshot = {f: getattr(settings, f) for f in _DB_BACKED_FIELDS}
    # Copy lists so subsequent mutations don't alias the snapshot
    for key, value in list(snapshot.items()):
        if isinstance(value, list):
            snapshot[key] = list(value)
    yield
    for key, value in snapshot.items():
        setattr(settings, key, value)


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
        # Capture all DB-backed fields before the call
        snapshot = {f: getattr(settings, f) for f in _DB_BACKED_FIELDS}
        await refresh_settings_from_db(db_session)
        # Every field should still match its pre-call value
        for field, expected in snapshot.items():
            assert getattr(settings, field) == expected, (
                f"{field} changed unexpectedly: {expected!r} -> {getattr(settings, field)!r}"
            )

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
        # Fields left at default by _seed_row — verify they still came through the refresh
        assert settings.ai_base_url == ""
        assert settings.ai_review_frequency == "block"
        assert settings.ai_review_block_weeks == 6

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
