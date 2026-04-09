"""Integration tests for /api/admin/backups."""
from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import SESSION_COOKIE_NAME, create_session, hash_password
from flexloop.config import settings
from flexloop.models.admin_user import AdminUser


ORIGIN = {"Origin": "http://localhost:5173"}


@pytest.fixture(autouse=True)
def _backup_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "flexloop.db"
    db_path.write_bytes(b"SQLite format 3\x00" + b"\x00" * 100)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{db_path}")


async def _cookie(db: AsyncSession) -> dict[str, str]:
    a = AdminUser(username="t", password_hash=hash_password("password123"))
    db.add(a); await db.commit(); await db.refresh(a)
    token, _ = await create_session(db, admin_user_id=a.id)
    return {SESSION_COOKIE_NAME: token}


class TestListBackups:
    async def test_auth(self, client: AsyncClient) -> None:
        assert (await client.get("/api/admin/backups")).status_code == 401

    async def test_list_empty(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        res = await client.get("/api/admin/backups", cookies=cookies)
        assert res.status_code == 200
        assert res.json() == []


class TestCreateBackup:
    async def test_auth(self, client: AsyncClient) -> None:
        assert (await client.post("/api/admin/backups", headers=ORIGIN)).status_code == 401

    async def test_create(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        res = await client.post(
            "/api/admin/backups", cookies=cookies, headers=ORIGIN,
        )
        assert res.status_code == 201
        body = res.json()
        assert body["filename"].startswith("flexloop_backup_")
        assert body["size_bytes"] > 0

        res2 = await client.get("/api/admin/backups", cookies=cookies)
        assert len(res2.json()) >= 1



class TestDownloadBackup:
    async def test_auth(self, client: AsyncClient) -> None:
        assert (await client.get("/api/admin/backups/x.db/download")).status_code == 401

    async def test_download(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        res = await client.post(
            "/api/admin/backups", cookies=cookies, headers=ORIGIN,
        )
        filename = res.json()["filename"]

        res2 = await client.get(
            f"/api/admin/backups/{filename}/download", cookies=cookies,
        )
        assert res2.status_code == 200
        assert res2.headers["content-type"] == "application/octet-stream"
        assert len(res2.content) > 0

    async def test_download_not_found(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        res = await client.get(
            "/api/admin/backups/nonexistent.db/download", cookies=cookies,
        )
        assert res.status_code == 404


class TestUploadBackup:
    async def test_auth(self, client: AsyncClient) -> None:
        assert (await client.post("/api/admin/backups/upload", headers=ORIGIN)).status_code == 401

    async def test_upload(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        fake_db = b"SQLite format 3\x00" + b"\x00" * 100
        res = await client.post(
            "/api/admin/backups/upload",
            cookies=cookies,
            headers=ORIGIN,
            files={"file": ("my_backup.db", fake_db, "application/octet-stream")},
        )
        assert res.status_code == 201
        assert res.json()["filename"] == "my_backup.db"

        res2 = await client.get("/api/admin/backups", cookies=cookies)
        filenames = [b["filename"] for b in res2.json()]
        assert "my_backup.db" in filenames

    async def test_upload_duplicate(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        fake_db = b"SQLite format 3\x00" + b"\x00" * 100
        await client.post(
            "/api/admin/backups/upload",
            cookies=cookies, headers=ORIGIN,
            files={"file": ("dup.db", fake_db, "application/octet-stream")},
        )
        res = await client.post(
            "/api/admin/backups/upload",
            cookies=cookies, headers=ORIGIN,
            files={"file": ("dup.db", fake_db, "application/octet-stream")},
        )
        assert res.status_code == 409

    async def test_upload_invalid_extension(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        res = await client.post(
            "/api/admin/backups/upload",
            cookies=cookies, headers=ORIGIN,
            files={"file": ("bad.txt", b"hello", "application/octet-stream")},
        )
        assert res.status_code == 422

    async def test_upload_path_traversal(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        res = await client.post(
            "/api/admin/backups/upload",
            cookies=cookies, headers=ORIGIN,
            files={"file": ("../evil.db", b"x", "application/octet-stream")},
        )
        assert res.status_code == 422


class TestRestoreBackup:
    async def test_auth(self, client: AsyncClient) -> None:
        assert (await client.post("/api/admin/backups/x.db/restore", headers=ORIGIN)).status_code == 401

    async def test_restore(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        res = await client.post(
            "/api/admin/backups", cookies=cookies, headers=ORIGIN,
        )
        filename = res.json()["filename"]

        res2 = await client.post(
            f"/api/admin/backups/{filename}/restore",
            cookies=cookies, headers=ORIGIN,
        )
        assert res2.status_code == 200
        body = res2.json()
        assert body["status"] == "restored"
        assert body["restored_from"] == filename
        assert body["safety_backup"].startswith("flexloop_backup_")

    async def test_restore_not_found(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        res = await client.post(
            "/api/admin/backups/nonexistent.db/restore",
            cookies=cookies, headers=ORIGIN,
        )
        assert res.status_code == 404


class TestDeleteBackup:
    async def test_auth(self, client: AsyncClient) -> None:
        assert (await client.delete("/api/admin/backups/x.db", headers=ORIGIN)).status_code == 401

    async def test_delete(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        res = await client.post(
            "/api/admin/backups", cookies=cookies, headers=ORIGIN,
        )
        filename = res.json()["filename"]

        res2 = await client.delete(
            f"/api/admin/backups/{filename}",
            cookies=cookies, headers=ORIGIN,
        )
        assert res2.status_code == 204

        res3 = await client.get("/api/admin/backups", cookies=cookies)
        filenames = [b["filename"] for b in res3.json()]
        assert filename not in filenames

    async def test_delete_not_found(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        res = await client.delete(
            "/api/admin/backups/nonexistent.db",
            cookies=cookies, headers=ORIGIN,
        )
        assert res.status_code == 404
