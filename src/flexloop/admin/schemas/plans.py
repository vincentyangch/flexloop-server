"""Admin CRUD schemas for Plan and its nested relations.

The Plan resource is nested four levels deep (Plan → PlanDay → ExerciseGroup
→ PlanExercise, with an optional sets_json blob inside each exercise). This
file defines:

- Response schemas — one per level, from leaf to root, so Pydantic's
  forward-refs are satisfied naturally.
- PlanAdminCreate / PlanAdminUpdate — metadata-only write schemas. The admin
  router deliberately refuses nested days on these endpoints; day edits go
  through POST/PUT/DELETE /api/admin/plans/{id}/days endpoints.
- PlanDayAdminCreate (and its nested ExerciseGroupAdminCreate,
  PlanExerciseAdminCreate, SetTargetAdmin) — used by the day endpoints in
  Chunk 2. They are defined here to keep all plan-shaped schemas in one
  file.

All write schemas use ``extra="forbid"`` to reject typos at validation time.
All response schemas use ``from_attributes=True`` so they read directly off
SQLAlchemy ORM rows.
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


# --- Response schemas (leaf → root) -----------------------------------------


class PlanExerciseAdminResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    exercise_id: int
    exercise_group_id: int
    order: int
    sets: int
    reps: int
    weight: float | None
    rpe_target: float | None
    sets_json: list[dict] | None
    notes: str | None


class ExerciseGroupAdminResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    group_type: str
    order: int
    rest_after_group_sec: int
    exercises: list[PlanExerciseAdminResponse] = Field(default_factory=list)


class PlanDayAdminResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    day_number: int
    label: str
    focus: str
    exercise_groups: list[ExerciseGroupAdminResponse] = Field(default_factory=list)


class PlanAdminResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    split_type: str
    cycle_length: int
    block_start: date | None
    block_end: date | None
    status: str
    ai_generated: bool
    created_at: datetime
    updated_at: datetime | None
    days: list[PlanDayAdminResponse] = Field(default_factory=list)


# --- Plan-level write schemas -----------------------------------------------


class PlanAdminCreate(BaseModel):
    """POST /api/admin/plans — metadata only. Days are added via
    POST /api/admin/plans/{id}/days after the plan exists.
    """
    model_config = ConfigDict(extra="forbid")

    user_id: int
    name: str
    split_type: str = "custom"
    cycle_length: int = 3
    block_start: date | None = None
    block_end: date | None = None
    status: str = "active"
    ai_generated: bool = False


class PlanAdminUpdate(BaseModel):
    """PUT /api/admin/plans/{id} — metadata only. ``days`` is deliberately
    NOT a field here, so submitting a payload that includes a ``days`` key
    returns 422 (thanks to ``extra="forbid"``). Day edits go through the
    dedicated day endpoints.
    """
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    split_type: str | None = None
    cycle_length: int | None = None
    block_start: date | None = None
    block_end: date | None = None
    status: str | None = None
    ai_generated: bool | None = None


# --- Day-level write schemas (used by Chunk 2) -------------------------------


class SetTargetAdmin(BaseModel):
    """One row inside PlanExercise.sets_json. Stored as a JSON blob on the
    PlanExercise row; not its own table.
    """
    model_config = ConfigDict(extra="forbid")

    set_number: int
    target_weight: float | None = None
    target_reps: int = 10
    target_rpe: float | None = None


class PlanExerciseAdminCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exercise_id: int
    order: int = 1
    sets: int = 3
    reps: int = 10
    weight: float | None = None
    rpe_target: float | None = None
    sets_json: list[SetTargetAdmin] | None = None
    notes: str | None = None


class ExerciseGroupAdminCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_type: str = "straight"
    order: int = 1
    rest_after_group_sec: int = 90
    exercises: list[PlanExerciseAdminCreate] = Field(default_factory=list)


class PlanDayAdminCreate(BaseModel):
    """POST /api/admin/plans/{plan_id}/days — full nested day payload."""
    model_config = ConfigDict(extra="forbid")

    day_number: int
    label: str
    focus: str = ""
    exercise_groups: list[ExerciseGroupAdminCreate] = Field(default_factory=list)


class PlanDayAdminUpdate(BaseModel):
    """PUT /api/admin/plans/{plan_id}/days/{day_number} — replace entire day.

    ``day_number`` is NOT a field — it's fixed by the URL path. Only label,
    focus, and the nested groups/exercises are mutable.
    """
    model_config = ConfigDict(extra="forbid")

    label: str | None = None
    focus: str | None = None
    exercise_groups: list[ExerciseGroupAdminCreate] = Field(default_factory=list)
