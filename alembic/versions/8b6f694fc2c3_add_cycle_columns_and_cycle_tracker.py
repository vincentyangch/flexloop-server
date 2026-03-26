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


def upgrade() -> None:
    # Add cycle_length to plans
    op.add_column("plans", sa.Column("cycle_length", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("plans", sa.Column("updated_at", sa.DateTime(), nullable=True))

    # Make block_start and block_end nullable (no longer required for cycle-based plans)
    op.alter_column("plans", "block_start", existing_type=sa.Date(), nullable=True)
    op.alter_column("plans", "block_end", existing_type=sa.Date(), nullable=True)

    # Add sets_json to plan_exercises
    op.add_column("plan_exercises", sa.Column("sets_json", sa.JSON(), nullable=True))

    # Create cycle_tracker table
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
