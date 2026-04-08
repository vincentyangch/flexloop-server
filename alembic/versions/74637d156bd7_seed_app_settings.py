"""seed app_settings

Revision ID: 74637d156bd7
Revises: 1595e0843e18
Create Date: 2026-04-08 13:13:50.124997
"""
import json as _json
import os
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from dotenv import load_dotenv

# Load the project's .env so os.getenv sees the deployment's current values.
# Same pattern used by the phase 1 migration.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# revision identifiers, used by Alembic.
revision: str = "74637d156bd7"
down_revision: Union[str, None] = "1595e0843e18"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Default allowed origins — mirrors the old hardcoded list in
# flexloop.main._PHASE1_ALLOWED_ORIGINS so behavior is unchanged on
# existing deployments that haven't set custom origins yet.
_DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:8000",
]


def _parse_int(raw: str | None, default: int) -> int:
    try:
        return int(raw) if raw is not None else default
    except ValueError:
        return default


def _parse_float(raw: str | None, default: float) -> float:
    try:
        return float(raw) if raw is not None else default
    except ValueError:
        return default


def upgrade() -> None:
    """Insert a single app_settings row if one doesn't already exist.

    Values come from the deployment's current environment (loaded from
    .env above). If a field isn't set, the pydantic-settings default is
    used to match what ``flexloop.config.Settings()`` would load.
    """
    conn = op.get_bind()
    existing = conn.execute(
        sa.text("SELECT COUNT(*) FROM app_settings WHERE id = 1")
    ).scalar_one()
    if existing > 0:
        return

    conn.execute(
        sa.text(
            """
            INSERT INTO app_settings (
                id, ai_provider, ai_model, ai_api_key, ai_base_url,
                ai_temperature, ai_max_tokens, ai_review_frequency,
                ai_review_block_weeks, admin_allowed_origins
            ) VALUES (
                1, :ai_provider, :ai_model, :ai_api_key, :ai_base_url,
                :ai_temperature, :ai_max_tokens, :ai_review_frequency,
                :ai_review_block_weeks, :admin_allowed_origins
            )
            """
        ),
        {
            "ai_provider": os.getenv("AI_PROVIDER", "openai"),
            "ai_model": os.getenv("AI_MODEL", "gpt-4o-mini"),
            "ai_api_key": os.getenv("AI_API_KEY", ""),
            "ai_base_url": os.getenv("AI_BASE_URL", ""),
            "ai_temperature": _parse_float(os.getenv("AI_TEMPERATURE"), 0.7),
            "ai_max_tokens": _parse_int(os.getenv("AI_MAX_TOKENS"), 2000),
            "ai_review_frequency": os.getenv("AI_REVIEW_FREQUENCY", "block"),
            "ai_review_block_weeks": _parse_int(
                os.getenv("AI_REVIEW_BLOCK_WEEKS"), 6
            ),
            # SQLite's JSON column accepts raw text blobs; pre-serialize to avoid
            # sa.func.json binding issues through op.get_bind().execute(sa.text(...)).
            "admin_allowed_origins": _json.dumps(_DEFAULT_ALLOWED_ORIGINS),
        },
    )


def downgrade() -> None:
    """Delete the seeded row. Phase 1's migration drops the table itself."""
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM app_settings WHERE id = 1"))
