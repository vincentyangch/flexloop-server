"""Admin backup schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class BackupResponse(BaseModel):
    filename: str
    size_bytes: int
    created_at: datetime


class BackupRestoreResponse(BaseModel):
    status: str
    restored_from: str
    safety_backup: str
