"""Admin CRUD schemas for Measurement."""
from __future__ import annotations

from datetime import date as date_type

from pydantic import BaseModel, ConfigDict, Field


class MeasurementAdminResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    date: date_type
    type: str
    value: float
    notes: str | None


class MeasurementAdminCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: int
    date: date_type
    type: str = Field(min_length=1, max_length=20)
    value: float
    notes: str | None = None


class MeasurementAdminUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date_type | None = None
    type: str | None = Field(default=None, min_length=1, max_length=20)
    value: float | None = None
    notes: str | None = None
