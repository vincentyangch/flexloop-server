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
