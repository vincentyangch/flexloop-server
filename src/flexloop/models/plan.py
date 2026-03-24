from datetime import date, datetime

from sqlalchemy import (
    Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from flexloop.db.base import Base


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    split_type: Mapped[str] = mapped_column(String(50), nullable=False)
    block_start: Mapped[date] = mapped_column(Date, nullable=False)
    block_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    days: Mapped[list["PlanDay"]] = relationship(back_populates="plan", cascade="all, delete-orphan")


class PlanDay(Base):
    __tablename__ = "plan_days"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("plans.id"), nullable=False)
    day_number: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    focus: Mapped[str] = mapped_column(String(200), nullable=False)

    plan: Mapped["Plan"] = relationship(back_populates="days")
    exercise_groups: Mapped[list["ExerciseGroup"]] = relationship(
        back_populates="plan_day", cascade="all, delete-orphan"
    )
    exercises: Mapped[list["PlanExercise"]] = relationship(
        back_populates="plan_day", cascade="all, delete-orphan"
    )


class ExerciseGroup(Base):
    __tablename__ = "exercise_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_day_id: Mapped[int] = mapped_column(Integer, ForeignKey("plan_days.id"), nullable=False)
    group_type: Mapped[str] = mapped_column(String(20), nullable=False, default="straight")
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    rest_after_group_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=90)

    plan_day: Mapped["PlanDay"] = relationship(back_populates="exercise_groups")
    exercises: Mapped[list["PlanExercise"]] = relationship(back_populates="exercise_group")


class PlanExercise(Base):
    __tablename__ = "plan_exercises"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_day_id: Mapped[int] = mapped_column(Integer, ForeignKey("plan_days.id"), nullable=False)
    exercise_group_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("exercise_groups.id"), nullable=False
    )
    exercise_id: Mapped[int] = mapped_column(Integer, ForeignKey("exercises.id"), nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    sets: Mapped[int] = mapped_column(Integer, nullable=False)
    reps: Mapped[int] = mapped_column(Integer, nullable=False)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    rpe_target: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    plan_day: Mapped["PlanDay"] = relationship(back_populates="exercises")
    exercise_group: Mapped["ExerciseGroup"] = relationship(back_populates="exercises")
