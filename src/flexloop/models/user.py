from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from flexloop.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    gender: Mapped[str] = mapped_column(String(20), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[float] = mapped_column(Float, nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    weight_unit: Mapped[str] = mapped_column(String(10), nullable=False, default="kg")
    height_unit: Mapped[str] = mapped_column(String(10), nullable=False, default="cm")
    experience_level: Mapped[str] = mapped_column(String(20), nullable=False)
    goals: Mapped[str] = mapped_column(String(500), nullable=False)
    available_equipment: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
