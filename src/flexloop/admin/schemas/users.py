"""Admin CRUD schemas for the end-user ``User`` table.

Distinct from ``flexloop.schemas.user`` — those are iOS-facing DTOs which
intentionally expose only a subset of fields. Admin callers see everything
including internal timestamps and full raw JSON columns.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserAdminResponse(BaseModel):
    """Full user row as seen by the admin dashboard."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    gender: str
    age: int
    height: float
    weight: float
    weight_unit: str
    height_unit: str
    experience_level: str
    goals: str
    available_equipment: list[str] | None
    created_at: datetime


class UserAdminCreate(BaseModel):
    """Payload for POST /api/admin/users."""
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    gender: str = Field(min_length=1, max_length=20)
    age: int = Field(ge=0, le=150)
    height: float = Field(gt=0)
    weight: float = Field(gt=0)
    weight_unit: str = "kg"
    height_unit: str = "cm"
    experience_level: str = Field(min_length=1, max_length=20)
    goals: str = Field(default="", max_length=500)
    available_equipment: list[str] | None = None


class UserAdminUpdate(BaseModel):
    """Payload for PUT /api/admin/users/{id}. All fields optional — partial update."""
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    gender: str | None = Field(default=None, min_length=1, max_length=20)
    age: int | None = Field(default=None, ge=0, le=150)
    height: float | None = Field(default=None, gt=0)
    weight: float | None = Field(default=None, gt=0)
    weight_unit: str | None = None
    height_unit: str | None = None
    experience_level: str | None = Field(default=None, min_length=1, max_length=20)
    goals: str | None = Field(default=None, max_length=500)
    available_equipment: list[str] | None = None
