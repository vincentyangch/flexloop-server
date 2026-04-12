"""add codex oauth fields to app_settings

Revision ID: bc0403ed481f
Revises: 74637d156bd7
Create Date: 2026-04-11 21:40:08.462979
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'bc0403ed481f'
down_revision: Union[str, None] = '74637d156bd7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    """Check whether a column exists in a SQLite table.

    ``init_db`` runs ``create_all()`` before Alembic upgrades, so a fresh
    database may already have model-defined columns by the time this
    migration executes.
    """
    conn = op.get_bind()
    result = conn.execute(sa.text(f"PRAGMA table_info({table})"))
    return any(row[1] == column for row in result)


def upgrade() -> None:
    if not _column_exists("app_settings", "codex_auth_file"):
        op.add_column(
            "app_settings",
            sa.Column(
                "codex_auth_file",
                sa.String(512),
                nullable=False,
                server_default="~/.codex/auth.json",
            ),
        )
    if not _column_exists("app_settings", "ai_reasoning_effort"):
        op.add_column(
            "app_settings",
            sa.Column(
                "ai_reasoning_effort",
                sa.String(16),
                nullable=False,
                server_default="medium",
            ),
        )


def downgrade() -> None:
    if _column_exists("app_settings", "ai_reasoning_effort"):
        op.drop_column("app_settings", "ai_reasoning_effort")
    if _column_exists("app_settings", "codex_auth_file"):
        op.drop_column("app_settings", "codex_auth_file")
