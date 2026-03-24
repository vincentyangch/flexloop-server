from fastapi import APIRouter, HTTPException

from flexloop.services.backup import BackupService

router = APIRouter(prefix="/api", tags=["backup"])


def get_backup_service() -> BackupService:
    return BackupService(db_path="flexloop.db", backup_dir="backups")


@router.post("/backup")
async def create_backup():
    service = get_backup_service()
    result = service.create_backup(schema_version="1.0.0")
    return {
        "filename": result.filename,
        "size_bytes": result.size_bytes,
        "created_at": result.created_at.isoformat(),
    }


@router.get("/backups")
async def list_backups():
    service = get_backup_service()
    backups = service.list_backups()
    return [
        {
            "filename": b.filename,
            "size_bytes": b.size_bytes,
            "created_at": b.created_at.isoformat(),
        }
        for b in backups
    ]


@router.post("/restore/{backup_filename}")
async def restore_backup(backup_filename: str):
    service = get_backup_service()
    success = service.restore(backup_filename)
    if not success:
        raise HTTPException(status_code=404, detail="Backup not found")
    return {"status": "restored", "from": backup_filename}
