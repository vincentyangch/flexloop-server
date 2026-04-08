"""Admin CRUD schemas for Exercise."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExerciseAdminResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    muscle_group: str
    equipment: str
    category: str
    difficulty: str
    source_plugin: str | None
    metadata_json: dict[str, Any] | None


class ExerciseAdminCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    muscle_group: str = Field(min_length=1, max_length=50)
    equipment: str = Field(min_length=1, max_length=50)
    category: str = Field(min_length=1, max_length=50)
    difficulty: str = Field(min_length=1, max_length=20)
    source_plugin: str | None = None
    metadata_json: dict[str, Any] | None = None


class ExerciseAdminUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    muscle_group: str | None = Field(default=None, min_length=1, max_length=50)
    equipment: str | None = Field(default=None, min_length=1, max_length=50)
    category: str | None = Field(default=None, min_length=1, max_length=50)
    difficulty: str | None = Field(default=None, min_length=1, max_length=20)
    source_plugin: str | None = None
    metadata_json: dict[str, Any] | None = None
