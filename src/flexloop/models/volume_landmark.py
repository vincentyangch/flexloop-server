from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from flexloop.db.base import Base


class VolumeLandmark(Base):
    __tablename__ = "volume_landmarks"
    __table_args__ = (
        UniqueConstraint("muscle_group", "experience_level", name="uq_volume_landmark"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    muscle_group: Mapped[str] = mapped_column(String(50), nullable=False)
    experience_level: Mapped[str] = mapped_column(String(20), nullable=False)
    mv_sets: Mapped[int] = mapped_column(Integer, nullable=False)
    mev_sets: Mapped[int] = mapped_column(Integer, nullable=False)
    mav_sets: Mapped[int] = mapped_column(Integer, nullable=False)
    mrv_sets: Mapped[int] = mapped_column(Integer, nullable=False)
