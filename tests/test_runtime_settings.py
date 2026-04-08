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
