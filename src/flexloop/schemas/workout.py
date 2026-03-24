from datetime import datetime

from pydantic import BaseModel


class WorkoutSetCreate(BaseModel):
    exercise_id: int
    exercise_group_id: int | None = None
    set_number: int
    set_type: str = "working"
    weight: float | None = None
    reps: int | None = None
    rpe: float | None = None
    duration_sec: int | None = None
    distance_m: float | None = None
    rest_sec: int | None = None


class WorkoutSetResponse(BaseModel):
    id: int
    exercise_id: int
    exercise_group_id: int | None = None
    set_number: int
    set_type: str
    weight: float | None = None
    reps: int | None = None
    rpe: float | None = None
    duration_sec: int | None = None
    distance_m: float | None = None
    rest_sec: int | None = None

    model_config = {"from_attributes": True}


class SessionFeedbackCreate(BaseModel):
    sleep_quality: int | None = None
    energy_level: int | None = None
    muscle_soreness_json: dict | None = None
    session_difficulty: int | None = None
    stress_level: int | None = None


class SessionFeedbackResponse(BaseModel):
    id: int
    sleep_quality: int | None = None
    energy_level: int | None = None
    muscle_soreness_json: dict | None = None
    session_difficulty: int | None = None
    stress_level: int | None = None

    model_config = {"from_attributes": True}


class WorkoutSessionCreate(BaseModel):
    user_id: int
    plan_day_id: int | None = None
    template_id: int | None = None
    source: str = "ad_hoc"
    notes: str | None = None


class WorkoutSessionUpdate(BaseModel):
    completed_at: datetime | None = None
    notes: str | None = None
    sets: list[WorkoutSetCreate] | None = None


class WorkoutSessionResponse(BaseModel):
    id: int
    user_id: int
    plan_day_id: int | None = None
    template_id: int | None = None
    source: str
    started_at: datetime
    completed_at: datetime | None = None
    notes: str | None = None
    sets: list[WorkoutSetResponse] = []
    feedback: SessionFeedbackResponse | None = None

    model_config = {"from_attributes": True}
