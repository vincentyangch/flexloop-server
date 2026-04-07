import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine

from flexloop.db.base import Base
import flexloop.models  # noqa: F401 — register all models with Base.metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    url = config.get_main_option("sqlalchemy.url", "")
    if "aiosqlite" in url:
        # Async path (CLI usage)
        connectable = create_async_engine(url)

        async def _run():
            async with connectable.connect() as connection:
                await connection.run_sync(do_run_migrations)
            await connectable.dispose()

        asyncio.run(_run())
    else:
        # Sync path (called from within running server)
        connectable = create_engine(url)
        with connectable.connect() as connection:
            do_run_migrations(connection)
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
