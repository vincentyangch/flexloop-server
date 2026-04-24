"""Regression tests for programmatic Alembic migrations."""
from __future__ import annotations

import logging
from pathlib import Path

import pytest
from sqlalchemy import create_engine

import flexloop.models  # noqa: F401
from flexloop.config import settings
from flexloop.db.base import Base
from flexloop.db.engine import _run_migrations


def test_run_migrations_preserves_app_logging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "flexloop.db"
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        Base.metadata.create_all(engine)
    finally:
        engine.dispose()

    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{db_path}")

    root_logger = logging.getLogger()
    uvicorn_logger = logging.getLogger("uvicorn.error")
    sentinel_handler = logging.NullHandler()
    original_root_handlers = list(root_logger.handlers)
    original_uvicorn_disabled = uvicorn_logger.disabled

    root_logger.addHandler(sentinel_handler)
    uvicorn_logger.disabled = False
    try:
        _run_migrations()

        assert sentinel_handler in root_logger.handlers
        assert uvicorn_logger.disabled is False
    finally:
        root_logger.handlers[:] = original_root_handlers
        uvicorn_logger.disabled = original_uvicorn_disabled
