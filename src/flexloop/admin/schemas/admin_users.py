"""Admin CRUD schemas for the ``admin_users`` table itself."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AdminAdminUserResponse(BaseModel):
    """Response shape — password_hash intentionally excluded."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    created_at: datetime
    last_login_at: datetime | None
    is_active: bool


class AdminAdminUserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=256)
    is_active: bool = True


class AdminAdminUserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str | None = Field(default=None, min_length=1, max_length=64)
    password: str | None = Field(default=None, min_length=8, max_length=256)
    is_active: bool | None = None
