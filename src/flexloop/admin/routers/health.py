"""Admin health endpoint: /api/admin/health.

Runs a handful of quick checks (DB reachability, row counts, system info,
recent errors from the ring buffer, AI provider, disk, memory, backups,
migrations) and returns a structured payload for the dashboard health card
and the dedicated health page.
"""
import os
import platform
import resource
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import require_admin
from flexloop.admin.log_handler import admin_ring_buffer
from flexloop.ai.codex_auth import CodexAuthReader
from flexloop.config import settings as _settings
from flexloop.db.engine import get_session

router = APIRouter(prefix="/api/admin", tags=["admin:health"])


_PROCESS_START = time.time()

# AI provider check cache (60-second TTL)
_ai_cache: dict[str, Any] | None = None
_ai_cache_at: float = 0


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
        url = _settings.database_url
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


async def _check_ai_provider() -> dict[str, Any]:
    global _ai_cache, _ai_cache_at  # noqa: PLW0603
    now = time.time()
    current_provider = _settings.ai_provider
    if (
        _ai_cache is not None
        and _ai_cache.get("provider") == current_provider
        and (now - _ai_cache_at) < 60
    ):
        return {**_ai_cache, "cached": True}

    provider = current_provider
    model = _settings.ai_model

    if provider == "openai-codex":
        snapshot = CodexAuthReader(_settings.codex_auth_file).snapshot()
        result: dict[str, Any] = {
            "status": snapshot.status,
            "provider": provider,
            "model": model,
            "has_key": False,
            "reachable": False,
            "file_exists": snapshot.file_exists,
            "file_path": snapshot.file_path,
            "auth_mode": snapshot.auth_mode,
            "last_refresh": snapshot.last_refresh,
            "days_since_refresh": snapshot.days_since_refresh,
            "account_email": snapshot.account_email,
            "error": snapshot.error,
            "error_code": snapshot.error_code,
        }
        _ai_cache = result
        _ai_cache_at = now
        return result

    api_key = _settings.ai_api_key
    base_url = _settings.ai_base_url or "https://api.openai.com"

    has_key = bool(api_key)
    reachable = False
    error = None

    if has_key:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(base_url)
                reachable = r.status_code < 500
        except Exception as e:  # noqa: BLE001
            error = str(e)

    if has_key and reachable:
        status = "healthy"
    elif has_key:
        status = "degraded"
    else:
        status = "unconfigured"

    result: dict[str, Any] = {
        "status": status,
        "provider": provider,
        "model": model,
        "has_key": has_key,
        "reachable": reachable,
    }
    if error:
        result["error"] = error

    _ai_cache = result
    _ai_cache_at = now
    return result


def _check_disk() -> dict[str, Any]:
    try:
        usage = shutil.disk_usage("/")
        return {
            "total_bytes": usage.total,
            "free_bytes": usage.free,
            "used_pct": round((usage.used / usage.total) * 100, 1),
        }
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def _check_memory() -> dict[str, Any]:
    try:
        rusage = resource.getrusage(resource.RUSAGE_SELF)
        rss = rusage.ru_maxrss
        # macOS reports ru_maxrss in bytes, Linux in KB
        if platform.system() == "Linux":
            rss *= 1024
        result: dict[str, Any] = {"rss_bytes": rss}
        # Try to get current VMS from /proc on Linux
        try:
            with open("/proc/self/status") as f:
                for line in f:
                    if line.startswith("VmSize:"):
                        result["vms_bytes"] = int(line.split()[1]) * 1024
                        break
        except (FileNotFoundError, PermissionError):
            pass
        return result
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def _check_backups() -> dict[str, Any]:
    try:
        backups_dir = Path("backups")
        if not backups_dir.exists():
            return {"count": 0, "total_bytes": 0}
        files = list(backups_dir.glob("*.db"))
        if not files:
            return {"count": 0, "total_bytes": 0}
        total_bytes = sum(f.stat().st_size for f in files)
        latest = max(files, key=lambda f: f.stat().st_mtime)
        last_at = datetime.fromtimestamp(
            latest.stat().st_mtime, tz=timezone.utc
        ).isoformat()
        return {
            "count": len(files),
            "last_at": last_at,
            "total_bytes": total_bytes,
        }
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def _check_migrations() -> dict[str, Any]:
    try:
        from alembic.config import Config
        from alembic.migration import MigrationContext
        from alembic.script import ScriptDirectory
        from sqlalchemy import create_engine

        alembic_cfg = Config("alembic.ini")
        script = ScriptDirectory.from_config(alembic_cfg)
        head_rev = script.get_current_head()

        sync_url = _settings.database_url.replace(
            "sqlite+aiosqlite", "sqlite"
        )
        engine = create_engine(sync_url)
        with engine.connect() as conn:
            context = MigrationContext.configure(conn)
            current_rev = context.get_current_revision()
        engine.dispose()

        return {
            "current_rev": current_rev,
            "head_rev": head_rev,
            "in_sync": current_rev == head_rev,
        }
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


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
    ai_provider = await _check_ai_provider()
    recent_errors = _recent_errors()
    system = _system_info()

    component_statuses = [
        database.get("status"),
        ai_provider.get("status"),
    ]
    if all(s == "healthy" for s in component_statuses):
        status = "healthy"
    elif any(s == "down" for s in component_statuses):
        status = "down"
    else:
        status = "degraded"

    return {
        "status": status,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "components": {
            "database": database,
            "ai_provider": ai_provider,
            "disk": _check_disk(),
            "memory": _check_memory(),
            "backups": _check_backups(),
            "migrations": _check_migrations(),
        },
        "recent_errors": recent_errors,
        "system": system,
    }
