"""Admin CRUD schemas for ``WorkoutSession``.

Sets are embedded into the workout session response as a read-only list.
Admins can't add individual sets through this endpoint — the assumption is
that any fine-grained set editing happens on the iOS client or a future
dedicated set editor. Admin create accepts only the session header.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WorkoutSetAdminResponse(BaseModel):
    """Single set row embedded inside a ``WorkoutSessionAdminResponse``."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    exercise_id: int
    exercise_group_id: int | None
    set_number: int
    set_type: str
    weight: float | None
    reps: int | None
    rpe: float | None
    duration_sec: int | None
    distance_m: float | None
    rest_sec: int | None


class WorkoutSessionAdminResponse(BaseModel):
    """Full workout session row with embedded sets."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    plan_day_id: int | None
    template_id: int | None
    source: str
    started_at: datetime
    completed_at: datetime | None
    notes: str | None
    sets: list[WorkoutSetAdminResponse] = Field(default_factory=list)


class WorkoutSessionAdminCreate(BaseModel):
    """Payload for POST /api/admin/workouts."""
    model_config = ConfigDict(extra="forbid")

    user_id: int
    plan_day_id: int | None = None
    template_id: int | None = None
    source: str = "plan"
    started_at: datetime
    completed_at: datetime | None = None
    notes: str | None = None


class WorkoutSessionAdminUpdate(BaseModel):
    """Payload for PUT /api/admin/workouts/{id}. All fields optional — partial update."""
    model_config = ConfigDict(extra="forbid")

    plan_day_id: int | None = None
    template_id: int | None = None
    source: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    notes: str | None = None
