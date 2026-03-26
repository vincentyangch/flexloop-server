from datetime import date, datetime

from pydantic import BaseModel


# --- Response schemas ---

class PlanExerciseResponse(BaseModel):
    id: int
    exercise_id: int
    order: int
    sets: int
    reps: int
    weight: float | None = None
    rpe_target: float | None = None
    sets_json: list[dict] | None = None
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
    cycle_length: int
    block_start: date | None = None
    block_end: date | None = None
    status: str
    ai_generated: bool
    created_at: datetime
    updated_at: datetime | None = None
    days: list[PlanDayResponse] = []

    model_config = {"from_attributes": True}


class PlanListResponse(BaseModel):
    plans: list[PlanResponse]
    total: int


# --- Create/Update schemas ---

class SetTarget(BaseModel):
    set_number: int
    target_weight_kg: float | None = None
    target_reps: int = 10
    target_rpe: float | None = None


class PlanExerciseCreate(BaseModel):
    exercise_id: int
    order: int = 1
    sets: int = 3
    reps: int = 10
    weight: float | None = None
    rpe_target: float | None = None
    sets_json: list[SetTarget] | None = None
    notes: str | None = None


class ExerciseGroupCreate(BaseModel):
    group_type: str = "straight"
    order: int = 1
    rest_after_group_sec: int = 90
    exercises: list[PlanExerciseCreate] = []


class PlanDayCreate(BaseModel):
    day_number: int
    label: str
    focus: str = ""
    exercise_groups: list[ExerciseGroupCreate] = []


class PlanCreate(BaseModel):
    user_id: int
    name: str
    split_type: str = "custom"
    cycle_length: int = 3
    days: list[PlanDayCreate] = []


class PlanUpdate(BaseModel):
    name: str | None = None
    split_type: str | None = None
    cycle_length: int | None = None
    days: list[PlanDayCreate] | None = None


class PlanGenerateRequest(BaseModel):
    user_id: int
