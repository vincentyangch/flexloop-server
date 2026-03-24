from datetime import date, datetime

from pydantic import BaseModel


class PlanExerciseResponse(BaseModel):
    id: int
    exercise_id: int
    order: int
    sets: int
    reps: int
    weight: float | None = None
    rpe_target: float | None = None
    notes: str | None = None

    model_config = {"from_attributes": True}


class ExerciseGroupResponse(BaseModel):
    id: int
    group_type: str
    order: int
    rest_after_group_sec: int
    exercises: list[PlanExerciseResponse] = []

    model_config = {"from_attributes": True}


class PlanDayResponse(BaseModel):
    id: int
    day_number: int
    label: str
    focus: str
    exercise_groups: list[ExerciseGroupResponse] = []

    model_config = {"from_attributes": True}


class PlanResponse(BaseModel):
    id: int
    user_id: int
    name: str
    split_type: str
    block_start: date
    block_end: date
    status: str
    ai_generated: bool
    created_at: datetime
    days: list[PlanDayResponse] = []

    model_config = {"from_attributes": True}


class PlanListResponse(BaseModel):
    plans: list[PlanResponse]
    total: int


class PlanGenerateRequest(BaseModel):
    user_id: int
