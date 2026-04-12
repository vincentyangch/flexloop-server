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
    codex_auth_file: str = "~/.codex/auth.json"
    ai_reasoning_effort: str = "medium"
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
    "codex_auth_file",
    "ai_reasoning_effort",
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
