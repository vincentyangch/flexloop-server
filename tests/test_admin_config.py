"""Integration tests for /api/admin/config."""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import SESSION_COOKIE_NAME, create_session, hash_password
from flexloop.config import _DB_BACKED_FIELDS, settings
from flexloop.models.admin_audit_log import AdminAuditLog
from flexloop.models.admin_user import AdminUser
from flexloop.models.app_settings import AppSettings


ORIGIN = "http://localhost:5173"


@pytest.fixture(autouse=True)
def _restore_settings_singleton():
    """Snapshot the runtime-mutable fields on ``settings`` before each test
    and restore them on teardown.

    Prevents state leakage between tests — especially important because
    ``test_refreshes_settings_singleton`` writes values like
    ``admin_allowed_origins=["https://admin.example.com"]`` that would
    otherwise block future admin write tests at the CSRF layer.
    """
    snapshot = {f: getattr(settings, f) for f in _DB_BACKED_FIELDS}
    # Copy lists so subsequent mutations don't alias the snapshot
    for key, value in list(snapshot.items()):
        if isinstance(value, list):
            snapshot[key] = list(value)
    yield
    for key, value in snapshot.items():
        setattr(settings, key, value)


async def _make_admin_and_cookie(db: AsyncSession) -> tuple[AdminUser, dict[str, str]]:
    admin = AdminUser(username="tester", password_hash=hash_password("password123"))
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    token, _ = await create_session(db, admin_user_id=admin.id)
    return admin, {SESSION_COOKIE_NAME: token}


async def _seed_default_app_settings(db: AsyncSession) -> AppSettings:
    row = AppSettings(
        id=1,
        ai_provider="openai",
        ai_model="gpt-4o-mini",
        ai_api_key="sk-test-1234567xyz",
        ai_base_url="",
        ai_temperature=0.7,
        ai_max_tokens=2000,
        ai_review_frequency="block",
        ai_review_block_weeks=6,
        admin_allowed_origins=["http://localhost:5173", "http://localhost:8000"],
    )
    db.add(row)
    await db.commit()
    return row


class TestGetConfig:
    async def test_requires_auth(self, client: AsyncClient) -> None:
        assert (await client.get("/api/admin/config")).status_code == 401

    async def test_404_when_row_missing(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, cookies = await _make_admin_and_cookie(db_session)
        res = await client.get("/api/admin/config", cookies=cookies)
        assert res.status_code == 404

    async def test_returns_masked_api_key(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, cookies = await _make_admin_and_cookie(db_session)
        await _seed_default_app_settings(db_session)
        res = await client.get("/api/admin/config", cookies=cookies)
        assert res.status_code == 200
        body = res.json()
        assert body["ai_provider"] == "openai"
        assert body["ai_model"] == "gpt-4o-mini"
        # Masked: last 3 chars preserved, everything else bullets
        assert body["ai_api_key"].endswith("xyz")
        assert "sk-test" not in body["ai_api_key"]
        assert body["ai_max_tokens"] == 2000
        assert body["admin_allowed_origins"] == [
            "http://localhost:5173",
            "http://localhost:8000",
        ]

    async def test_empty_key_returns_empty_string(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, cookies = await _make_admin_and_cookie(db_session)
        row = await _seed_default_app_settings(db_session)
        row.ai_api_key = ""
        await db_session.commit()
        res = await client.get("/api/admin/config", cookies=cookies)
        assert res.status_code == 200
        assert res.json()["ai_api_key"] == ""
