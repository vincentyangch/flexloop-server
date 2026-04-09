"""Admin backup endpoints.

Wraps the existing ``BackupService`` with admin auth, audit logging,
download streaming, and multipart upload. The non-admin backup routes
in ``flexloop.routers.backup`` remain unchanged.

The list endpoint scans ``*.db`` in the backup directory (not just
``flexloop_backup_*.db``) so that uploaded files with custom names
are visible. All ``/{filename}`` endpoints validate the filename
for path-traversal safety.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.audit import write_audit_log
from flexloop.admin.auth import require_admin
from flexloop.admin.schemas.backup import BackupResponse, BackupRestoreResponse
from flexloop.config import settings
from flexloop.db.engine import _run_migrations, get_session
from flexloop.services.backup import BackupService

router = APIRouter(prefix="/api/admin/backups", tags=["admin:backups"])

_MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB


def _get_backup_service() -> BackupService:
    db_path = settings.database_url.replace("sqlite+aiosqlite:///", "")
    return BackupService(db_path=db_path, backup_dir="backups")


def _validate_filename(filename: str) -> None:
    """Reject path-traversal attempts and non-.db files."""
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(422, "invalid filename")
    if not filename.endswith(".db"):
        raise HTTPException(422, "filename must end with .db")


@router.get("", response_model=list[BackupResponse])
async def list_backups(
    _admin=Depends(require_admin),
) -> list[dict]:
    """List all *.db files in the backup directory, sorted newest first.

    Uses a direct directory scan instead of BackupService.list_backups()
    which only finds ``flexloop_backup_*.db`` files. This ensures uploaded
    files with custom names are visible.
    """
    svc = _get_backup_service()
    svc.backup_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(
        svc.backup_dir.glob("*.db"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    return [
        {
            "filename": f.name,
            "size_bytes": f.stat().st_size,
            "created_at": datetime.fromtimestamp(f.stat().st_mtime),
        }
        for f in files
    ]


@router.post("", response_model=BackupResponse, status_code=201)
async def create_backup(
    db: AsyncSession = Depends(get_session),
    admin=Depends(require_admin),
) -> dict:
    svc = _get_backup_service()
    info = svc.create_backup(schema_version="1.0.0")
    await write_audit_log(
        db,
        admin_user_id=admin.id,
        action="backup_create",
        target_type="backup",
        target_id=info.filename,
    )
    await db.commit()
    return {
        "filename": info.filename,
        "size_bytes": info.size_bytes,
        "created_at": info.created_at,
    }


@router.get("/{filename}/download")
async def download_backup(
    filename: str,
    _admin=Depends(require_admin),
) -> FileResponse:
    _validate_filename(filename)
    svc = _get_backup_service()
    filepath = svc.backup_dir / filename
    if not filepath.exists():
        raise HTTPException(404, "backup not found")
    return FileResponse(
        filepath,
        media_type="application/octet-stream",
        filename=filename,
    )
