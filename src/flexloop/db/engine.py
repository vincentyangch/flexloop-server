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

    # Run Alembic migrations to apply any schema updates
    # (handles columns added after initial create_all)
    _run_migrations()

    # Load runtime-mutable settings from the app_settings row so the
    # in-memory singleton matches the DB before any request is served.
    from flexloop.config import refresh_settings_from_db

    async with async_session() as db:
        await refresh_settings_from_db(db)


def _run_migrations():
    """Run Alembic migrations using a synchronous connection to avoid async conflicts."""
    import sqlite3

    from alembic import command
    from alembic.config import Config

    # Stamp current version if alembic_version table doesn't exist yet
    # (handles DBs created before migrations were introduced)
    db_path = settings.database_url.replace("sqlite+aiosqlite:///", "")
    conn = sqlite3.connect(db_path)
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    conn.close()

    alembic_cfg = Config("alembic.ini")
    # Override the URL to use synchronous sqlite driver
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(alembic_cfg, "head")
