"""add cache token columns to ai_usage

Revision ID: 4ea6733bdacc
Revises: 
Create Date: 2026-03-24 20:27:41.917935
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '4ea6733bdacc'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if columns already exist (handles DBs that were manually patched)
    conn = op.get_bind()
    columns = [col["name"] for col in conn.execute(sa.text("PRAGMA table_info(ai_usage)")).mappings()]
    if "total_cache_read_tokens" not in columns:
        op.add_column("ai_usage", sa.Column("total_cache_read_tokens", sa.Integer(), nullable=False, server_default="0"))
    if "total_cache_creation_tokens" not in columns:
        op.add_column("ai_usage", sa.Column("total_cache_creation_tokens", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("ai_usage", "total_cache_creation_tokens")
    op.drop_column("ai_usage", "total_cache_read_tokens")
