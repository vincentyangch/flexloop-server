import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class BackupInfo:
    filename: str
    filepath: str
    size_bytes: int
    schema_version: str
    created_at: datetime


class BackupService:
    def __init__(self, db_path: str, backup_dir: str = "backups"):
        self.db_path = Path(db_path)
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self, schema_version: str) -> BackupInfo:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"flexloop_backup_{timestamp}.db"
        dest = self.backup_dir / filename

        shutil.copy2(self.db_path, dest)

        return BackupInfo(
            filename=filename,
            filepath=str(dest),
            size_bytes=dest.stat().st_size,
            schema_version=schema_version,
            created_at=datetime.now(),
        )

    def list_backups(self) -> list[BackupInfo]:
        backups = []
        for f in sorted(self.backup_dir.glob("flexloop_backup_*.db"), reverse=True):
            backups.append(BackupInfo(
                filename=f.name,
                filepath=str(f),
                size_bytes=f.stat().st_size,
                schema_version="unknown",
                created_at=datetime.fromtimestamp(f.stat().st_mtime),
            ))
        return backups

    def restore(self, backup_filename: str) -> bool:
        source = self.backup_dir / backup_filename
        if not source.exists():
            return False

        self.create_backup(schema_version="pre-restore")
        shutil.copy2(source, self.db_path)
        return True

    def prune(self, keep_daily: int = 7, keep_weekly: int = 4):
        backups = self.list_backups()
        if len(backups) <= keep_daily:
            return

        to_keep = set()
        for b in backups[:keep_daily]:
            to_keep.add(b.filename)

        seen_weeks = set()
        for b in backups:
            week_key = b.created_at.strftime("%Y-W%U")
            if week_key not in seen_weeks and len(seen_weeks) < keep_weekly:
                seen_weeks.add(week_key)
                to_keep.add(b.filename)

        for b in backups:
            if b.filename not in to_keep:
                Path(b.filepath).unlink(missing_ok=True)
