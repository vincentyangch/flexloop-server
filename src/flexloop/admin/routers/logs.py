"""Admin log viewer endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from flexloop.admin.auth import require_admin
from flexloop.admin.log_handler import admin_ring_buffer

router = APIRouter(prefix="/api/admin/logs", tags=["admin:logs"])


@router.get("")
async def get_logs(
    level: str = "DEBUG",
    search: str | None = None,
    since: str | None = None,
    limit: int = 200,
    _admin=Depends(require_admin),
) -> list[dict[str, Any]]:
    return admin_ring_buffer.get_records(
        min_level=level,
        search=search,
        since=since,
        limit=limit,
    )
