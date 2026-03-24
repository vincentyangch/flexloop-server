from pathlib import Path

from flexloop.services.backup import BackupService


def test_create_backup(tmp_path):
    db_path = tmp_path / "test.db"
    db_path.write_bytes(b"fake database content")
    service = BackupService(db_path=str(db_path), backup_dir=str(tmp_path / "backups"))

    result = service.create_backup(schema_version="1.0.0")
    assert result is not None
    assert Path(result.filepath).exists()
    assert result.schema_version == "1.0.0"
    assert result.size_bytes > 0


def test_list_backups_empty(tmp_path):
    db_path = tmp_path / "test.db"
    db_path.write_bytes(b"fake")
    service = BackupService(db_path=str(db_path), backup_dir=str(tmp_path / "backups"))

    backups = service.list_backups()
    assert backups == []


def test_list_backups_after_create(tmp_path):
    db_path = tmp_path / "test.db"
    db_path.write_bytes(b"fake")
    service = BackupService(db_path=str(db_path), backup_dir=str(tmp_path / "backups"))

    service.create_backup(schema_version="1.0.0")
    service.create_backup(schema_version="1.0.0")
    backups = service.list_backups()
    assert len(backups) == 2


def test_restore_backup(tmp_path):
    db_path = tmp_path / "test.db"
    db_path.write_bytes(b"original content")
    service = BackupService(db_path=str(db_path), backup_dir=str(tmp_path / "backups"))

    backup = service.create_backup(schema_version="1.0.0")
    db_path.write_bytes(b"modified content")

    success = service.restore(backup.filename)
    assert success
    assert db_path.read_bytes() == b"original content"


def test_restore_nonexistent(tmp_path):
    db_path = tmp_path / "test.db"
    db_path.write_bytes(b"fake")
    service = BackupService(db_path=str(db_path), backup_dir=str(tmp_path / "backups"))

    success = service.restore("nonexistent.db")
    assert not success


def test_prune_keeps_recent(tmp_path):
    import time

    db_path = tmp_path / "test.db"
    db_path.write_bytes(b"fake")
    service = BackupService(db_path=str(db_path), backup_dir=str(tmp_path / "backups"))

    for _ in range(10):
        service.create_backup(schema_version="1.0.0")
        time.sleep(0.01)  # ensure unique timestamps

    service.prune(keep_daily=7, keep_weekly=0)
    backups = service.list_backups()
    assert len(backups) <= 7
