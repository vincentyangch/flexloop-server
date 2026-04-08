"""Admin CRUD schemas for PersonalRecord."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PersonalRecordAdminResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    exercise_id: int
    pr_type: str
    value: float
    session_id: int | None
    achieved_at: datetime


class PersonalRecordAdminCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: int
    exercise_id: int
    pr_type: str = Field(min_length=1, max_length=20)
    value: float
    session_id: int | None = None
    achieved_at: datetime


class PersonalRecordAdminUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exercise_id: int | None = None
    pr_type: str | None = Field(default=None, min_length=1, max_length=20)
    value: float | None = None
    session_id: int | None = None
    achieved_at: datetime | None = None
