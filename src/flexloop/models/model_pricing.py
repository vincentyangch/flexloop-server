from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column

from flexloop.db.base import Base


class ModelPricing(Base):
    """Per-model AI cost overrides. Takes precedence over the static PRICING dict.

    Populated via the admin UI when a proxied or custom model isn't in the
    default pricing table.
    """
    __tablename__ = "model_pricing"

    model_name: Mapped[str] = mapped_column(String(128), primary_key=True)
    input_per_million: Mapped[float] = mapped_column(Float, nullable=False)
    output_per_million: Mapped[float] = mapped_column(Float, nullable=False)
    cache_read_per_million: Mapped[float | None] = mapped_column(Float, nullable=True)
    cache_write_per_million: Mapped[float | None] = mapped_column(Float, nullable=True)
