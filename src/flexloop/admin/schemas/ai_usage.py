"""Admin CRUD schemas for AIUsage (per-month rollup table)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AIUsageAdminResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    month: str
    total_input_tokens: int
    total_output_tokens: int
    total_cache_read_tokens: int
    total_cache_creation_tokens: int
    estimated_cost: float
    call_count: int


class AIUsageAdminCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: int
    month: str = Field(min_length=7, max_length=7)  # "YYYY-MM"
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cache_creation_tokens: int = 0
    estimated_cost: float = 0.0
    call_count: int = 0


class AIUsageAdminUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_input_tokens: int | None = None
    total_output_tokens: int | None = None
    total_cache_read_tokens: int | None = None
    total_cache_creation_tokens: int | None = None
    estimated_cost: float | None = None
    call_count: int | None = None
