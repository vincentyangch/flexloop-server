from sqlalchemy import JSON, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from flexloop.db.base import Base


class AppSettings(Base):
    """Single-row table holding runtime-mutable application settings.

    Always loaded as id=1. Created/updated via flexloop.admin.config endpoints.
    """
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # always 1
    ai_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    ai_model: Mapped[str] = mapped_column(String(128), nullable=False)
    ai_api_key: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    ai_base_url: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    ai_temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    ai_max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=2000)
    ai_review_frequency: Mapped[str] = mapped_column(String(32), nullable=False, default="block")
    ai_review_block_weeks: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    admin_allowed_origins: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
