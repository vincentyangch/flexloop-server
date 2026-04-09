"""Admin log viewer endpoints."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

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


@router.get("/stream")
async def stream_logs(
    level: str = "DEBUG",
    search: str | None = None,
    _admin=Depends(require_admin),
) -> StreamingResponse:
    async def event_generator():
        last_id = admin_ring_buffer.get_latest_id()
        initial_records = admin_ring_buffer.get_records(
            min_level=level,
            search=search,
            limit=50,
        )
        for record in initial_records:
            yield f"data: {json.dumps(record, default=str)}\n\n"
            last_id = max(last_id, record.get("id", -1))

        try:
            while True:
                records = admin_ring_buffer.get_records_after(
                    last_id,
                    min_level=level,
                    search=search,
                )
                for record in records:
                    yield f"data: {json.dumps(record, default=str)}\n\n"
                    last_id = record.get("id", -1)
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            return

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
