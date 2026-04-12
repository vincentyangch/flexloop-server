"""Tests for the Codex OAuth app_settings Alembic migration."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from collections.abc import Callable

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect


_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "bc0403ed481f_add_codex_oauth_fields_to_app_settings.py"
)
_spec = importlib.util.spec_from_file_location("codex_oauth_migration", _MIGRATION_PATH)
assert _spec is not None
assert _spec.loader is not None
migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migration)


def _create_pre_codex_app_settings_table(engine: sa.Engine) -> None:
    metadata = sa.MetaData()
    sa.Table(
        "app_settings",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ai_provider", sa.String(32), nullable=False),
        sa.Column("ai_model", sa.String(128), nullable=False),
        sa.Column("ai_api_key", sa.String(256), nullable=False),
        sa.Column("ai_base_url", sa.String(256), nullable=False),
        sa.Column("ai_temperature", sa.Float(), nullable=False),
        sa.Column("ai_max_tokens", sa.Integer(), nullable=False),
        sa.Column("ai_review_frequency", sa.String(32), nullable=False),
        sa.Column("ai_review_block_weeks", sa.Integer(), nullable=False),
        sa.Column("admin_allowed_origins", sa.JSON(), nullable=False),
    )
    metadata.create_all(engine)


def _run_migration(engine: sa.Engine, fn: Callable[[], None]) -> None:
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        original_op = migration.op
        migration.op = Operations(context)
        try:
            fn()
        finally:
            migration.op = original_op


def _column_map(engine: sa.Engine) -> dict[str, dict]:
    return {
        column["name"]: column
        for column in inspect(engine).get_columns("app_settings")
    }


def _sqlite_default(column: dict) -> str:
    return str(column["default"]).strip("'")


def test_upgrade_adds_columns_to_fresh_schema() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    _create_pre_codex_app_settings_table(engine)

    _run_migration(engine, migration.upgrade)

    columns = _column_map(engine)
    assert "codex_auth_file" in columns
    assert "ai_reasoning_effort" in columns
    assert str(columns["codex_auth_file"]["type"]) == "VARCHAR(512)"
    assert str(columns["ai_reasoning_effort"]["type"]) == "VARCHAR(16)"
    assert columns["codex_auth_file"]["nullable"] is False
    assert columns["ai_reasoning_effort"]["nullable"] is False
    assert _sqlite_default(columns["codex_auth_file"]) == "~/.codex/auth.json"
    assert _sqlite_default(columns["ai_reasoning_effort"]) == "medium"


def test_downgrade_removes_columns() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    _create_pre_codex_app_settings_table(engine)
    _run_migration(engine, migration.upgrade)

    _run_migration(engine, migration.downgrade)

    columns = _column_map(engine)
    assert "codex_auth_file" not in columns
    assert "ai_reasoning_effort" not in columns


def test_upgrade_idempotent_on_rerun() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    _create_pre_codex_app_settings_table(engine)

    _run_migration(engine, migration.upgrade)
    _run_migration(engine, migration.upgrade)

    columns = _column_map(engine)
    assert "codex_auth_file" in columns
    assert "ai_reasoning_effort" in columns
