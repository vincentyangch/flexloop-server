"""add cycle columns and cycle_tracker

Revision ID: 8b6f694fc2c3
Revises: 4ea6733bdacc
Create Date: 2026-03-25 19:18:21.922205
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '8b6f694fc2c3'
down_revision: Union[str, None] = '4ea6733bdacc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table, column):
    """Check if a column exists in a SQLite table."""
    conn = op.get_bind()
    result = conn.execute(sa.text(f"PRAGMA table_info({table})"))
    return any(row[1] == column for row in result)


def _table_exists(table):
    """Check if a table exists in SQLite."""
    conn = op.get_bind()
    result = conn.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
        {"name": table},
    )
    return result.fetchone() is not None


def upgrade() -> None:
    # Add cycle_length to plans
    if not _column_exists("plans", "cycle_length"):
        op.add_column("plans", sa.Column("cycle_length", sa.Integer(), nullable=False, server_default="3"))
    if not _column_exists("plans", "updated_at"):
        op.add_column("plans", sa.Column("updated_at", sa.DateTime(), nullable=True))

    # Make block_start and block_end nullable (no longer required for cycle-based plans)
    # Note: SQLite doesn't enforce ALTER COLUMN nullable changes, but this documents intent
    try:
        op.alter_column("plans", "block_start", existing_type=sa.Date(), nullable=True)
        op.alter_column("plans", "block_end", existing_type=sa.Date(), nullable=True)
    except Exception:
        pass  # Already nullable or SQLite doesn't support this operation

    # Add sets_json to plan_exercises
    if not _column_exists("plan_exercises", "sets_json"):
        op.add_column("plan_exercises", sa.Column("sets_json", sa.JSON(), nullable=True))

    # Create cycle_tracker table
    if not _table_exists("cycle_tracker"):
        op.create_table(
            "cycle_tracker",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, unique=True),
            sa.Column("plan_id", sa.Integer(), sa.ForeignKey("plans.id"), nullable=False),
            sa.Column("next_day_number", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("last_completed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        )


def downgrade() -> None:
    op.drop_table("cycle_tracker")
    op.drop_column("plan_exercises", "sets_json")
    op.drop_column("plans", "updated_at")
    op.drop_column("plans", "cycle_length")
    op.alter_column("plans", "block_start", existing_type=sa.Date(), nullable=False)
    op.alter_column("plans", "block_end", existing_type=sa.Date(), nullable=False)
