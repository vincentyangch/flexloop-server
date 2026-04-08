"""Integration tests for /api/admin/ai/usage."""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import SESSION_COOKIE_NAME, create_session, hash_password
from flexloop.models.admin_user import AdminUser
from flexloop.models.ai import AIUsage
from flexloop.models.user import User


async def _cookie(db: AsyncSession) -> dict[str, str]:
    a = AdminUser(username="t", password_hash=hash_password("password123"))
    db.add(a); await db.commit(); await db.refresh(a)
    token, _ = await create_session(db, admin_user_id=a.id)
    return {SESSION_COOKIE_NAME: token}


async def _user(db: AsyncSession) -> User:
    u = User(
        name="AI User", gender="other", age=30, height=170, weight=70,
        weight_unit="kg", height_unit="cm", experience_level="intermediate",
        goals="", available_equipment=[],
    )
    db.add(u); await db.commit(); await db.refresh(u)
    return u


class TestAIUsage:
    async def test_auth(self, client: AsyncClient) -> None:
        assert (await client.get("/api/admin/ai/usage")).status_code == 401

    async def test_list_and_filter_by_month(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        user = await _user(db_session)
        db_session.add_all([
            AIUsage(user_id=user.id, month="2026-03", total_input_tokens=1000, estimated_cost=0.01, call_count=5),
            AIUsage(user_id=user.id, month="2026-04", total_input_tokens=2000, estimated_cost=0.02, call_count=7),
        ])
        await db_session.commit()

        res = await client.get("/api/admin/ai/usage", cookies=cookies)
        assert res.json()["total"] == 2

        res = await client.get(
            "/api/admin/ai/usage?filter[month]=2026-04", cookies=cookies,
        )
        assert res.json()["total"] == 1
        assert res.json()["items"][0]["call_count"] == 7
