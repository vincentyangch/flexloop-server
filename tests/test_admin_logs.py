"""Integration tests for /api/admin/logs."""
from __future__ import annotations

import logging
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import SESSION_COOKIE_NAME, create_session, hash_password
from flexloop.admin.log_handler import admin_ring_buffer
from flexloop.models.admin_user import AdminUser


async def _cookie(db: AsyncSession) -> dict[str, str]:
    admin = AdminUser(username="logs-tester", password_hash=hash_password("password123"))
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    token, _ = await create_session(db, admin_user_id=admin.id)
    return {SESSION_COOKIE_NAME: token}


@pytest.fixture(autouse=True)
def _clear_buffer(tmp_path: Path):
    original_dir = admin_ring_buffer._log_dir
    admin_ring_buffer.clear()
    admin_ring_buffer._log_dir = tmp_path
    yield
    admin_ring_buffer.clear()
    admin_ring_buffer._log_dir = original_dir


class TestGetLogs:
    async def test_auth(self, client: AsyncClient) -> None:
        response = await client.get("/api/admin/logs")
        assert response.status_code == 401

    async def test_empty(self, client: AsyncClient, db_session: AsyncSession) -> None:
        cookies = await _cookie(db_session)

        response = await client.get("/api/admin/logs", cookies=cookies)

        assert response.status_code == 200
        assert response.json() == []

    async def test_returns_records(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        cookies = await _cookie(db_session)
        logger = logging.getLogger("test.logs.records")
        logger.warning("test warning message")

        response = await client.get("/api/admin/logs", cookies=cookies)

        assert response.status_code == 200
        records = response.json()
        assert any(record["message"] == "test warning message" for record in records)

    async def test_filter_by_level(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        cookies = await _cookie(db_session)
        logger = logging.getLogger("test.logs.level")
        logger.info("info msg")
        logger.warning("warn msg")

        response = await client.get("/api/admin/logs?level=WARNING", cookies=cookies)

        assert response.status_code == 200
        records = response.json()
        assert [record["message"] for record in records] == ["warn msg"]

    async def test_filter_by_search(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        cookies = await _cookie(db_session)
        logger = logging.getLogger("test.logs.search")
        logger.info("needle in haystack")
        logger.info("just hay")

        response = await client.get("/api/admin/logs?search=needle", cookies=cookies)

        assert response.status_code == 200
        records = response.json()
        assert [record["message"] for record in records] == ["needle in haystack"]

    async def test_limit(self, client: AsyncClient, db_session: AsyncSession) -> None:
        cookies = await _cookie(db_session)
        logger = logging.getLogger("test.logs.limit")
        for idx in range(10):
            logger.info(f"msg {idx}")

        response = await client.get("/api/admin/logs?limit=3", cookies=cookies)

        assert response.status_code == 200
        records = response.json()
        assert [record["message"] for record in records] == ["msg 7", "msg 8", "msg 9"]
