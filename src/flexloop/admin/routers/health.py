"""Admin health endpoint: /api/admin/health.

Runs a handful of quick checks (DB reachability, row counts, system info,
recent errors from the ring buffer) and returns a structured payload for
the dashboard health card and the dedicated health page.

Phase 1 scope: DB, system info, recent errors, table row counts. Later
phases will add AI provider check, disk/memory, backups, migrations status.
"""
import os
import platform
import sys
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import require_admin
from flexloop.admin.log_handler import admin_ring_buffer
from flexloop.db.engine import get_session

router = APIRouter(prefix="/api/admin", tags=["admin:health"])


_PROCESS_START = time.time()


# List of tables to count rows for on the health page. Plain table names are
# enough; we don't need to import the model classes for this.
_COUNTABLE_TABLES = [
    "users",
    "plans",
    "plan_days",
    "workout_sessions",
    "workout_sets",
    "measurements",
    "personal_records",
    "exercises",
    "ai_usage",
    "admin_users",
    "admin_sessions",
]


async def _check_database(db: AsyncSession) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        await db.execute(text("SELECT 1"))
        ms = (time.perf_counter() - start) * 1000
    except Exception as e:  # noqa: BLE001
        return {"status": "down", "error": str(e), "ms": 0}

    row_counts: dict[str, int] = {}
    for tbl in _COUNTABLE_TABLES:
        try:
            result = await db.execute(text(f"SELECT COUNT(*) FROM {tbl}"))
            row_counts[tbl] = result.scalar_one()
        except Exception:  # noqa: BLE001
            # Table may not exist yet on a fresh DB — skip silently
            continue

    db_size_bytes = 0
    try:
        # Best-effort for SQLite; other DBs will fall through
        from flexloop.config import settings as app_settings
        url = app_settings.database_url
        if url.startswith("sqlite"):
            path = url.split(":///")[-1]
            if os.path.exists(path):
                db_size_bytes = os.path.getsize(path)
    except Exception:  # noqa: BLE001
        pass

    return {
        "status": "healthy",
        "ms": round(ms, 2),
        "db_size_bytes": db_size_bytes,
        "table_row_counts": row_counts,
    }


def _recent_errors(limit: int = 20) -> list[dict[str, Any]]:
    return admin_ring_buffer.get_records(min_level="WARNING", limit=limit)


def _system_info() -> dict[str, Any]:
    import fastapi
    import uvicorn

    return {
        "python": sys.version.split()[0],
        "fastapi": fastapi.__version__,
        "uvicorn": uvicorn.__version__,
        "os": f"{platform.system()} {platform.release()}",
        "hostname": platform.node(),
        "uptime_seconds": int(time.time() - _PROCESS_START),
    }


@router.get("/health")
async def admin_health(
    db: AsyncSession = Depends(get_session),
    _user=Depends(require_admin),
):
    database = await _check_database(db)
    recent_errors = _recent_errors()
    system = _system_info()

    status = "healthy" if database["status"] == "healthy" else "degraded"

    return {
        "status": status,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "components": {
            "database": database,
            # Phase 4 will add ai_provider component
            # Phase 5 will add disk, memory, backups, migrations
        },
        "recent_errors": recent_errors,
        "system": system,
    }
