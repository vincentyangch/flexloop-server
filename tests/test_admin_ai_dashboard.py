"""Integration tests for /api/admin/ai/usage/stats + /api/admin/ai/pricing."""
from __future__ import annotations

from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import SESSION_COOKIE_NAME, create_session, hash_password
from flexloop.models.admin_user import AdminUser
from flexloop.models.ai import AIUsage
from flexloop.models.user import User


ORIGIN = "http://localhost:5173"


async def _make_admin_and_cookie(db: AsyncSession) -> dict[str, str]:
    admin = AdminUser(username="tester", password_hash=hash_password("password123"))
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    token, _ = await create_session(db, admin_user_id=admin.id)
    return {SESSION_COOKIE_NAME: token}


async def _make_user(db: AsyncSession, name: str = "Usage User") -> User:
    user = User(
        name=name,
        gender="other",
        age=30,
        height=180,
        weight=80,
        weight_unit="kg",
        height_unit="cm",
        experience_level="intermediate",
        goals="",
        available_equipment=[],
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _current_month() -> str:
    return date.today().strftime("%Y-%m")


class TestStatsCurrentMonth:
    async def test_requires_auth(self, client: AsyncClient) -> None:
        assert (await client.get("/api/admin/ai/usage/stats")).status_code == 401

    async def test_empty_returns_zero_totals(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.get("/api/admin/ai/usage/stats", cookies=cookies)
        assert res.status_code == 200
        body = res.json()
        assert "current_month" in body
        current_month = body["current_month"]
        assert current_month["month"] == _current_month()
        assert current_month["input_tokens"] == 0
        assert current_month["output_tokens"] == 0
        assert current_month["call_count"] == 0

    async def test_aggregates_across_users(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        user_one = await _make_user(db_session, "u1")
        user_two = await _make_user(db_session, "u2")
        month = _current_month()
        db_session.add_all(
            [
                AIUsage(
                    user_id=user_one.id,
                    month=month,
                    total_input_tokens=100,
                    total_output_tokens=50,
                    total_cache_read_tokens=0,
                    total_cache_creation_tokens=0,
                    estimated_cost=0,
                    call_count=3,
                ),
                AIUsage(
                    user_id=user_two.id,
                    month=month,
                    total_input_tokens=200,
                    total_output_tokens=70,
                    total_cache_read_tokens=10,
                    total_cache_creation_tokens=5,
                    estimated_cost=0,
                    call_count=4,
                ),
            ]
        )
        await db_session.commit()

        res = await client.get("/api/admin/ai/usage/stats", cookies=cookies)
        body = res.json()
        current_month = body["current_month"]
        assert current_month["input_tokens"] == 300
        assert current_month["output_tokens"] == 120
        assert current_month["cache_read_tokens"] == 10
        assert current_month["cache_write_tokens"] == 5
        assert current_month["call_count"] == 7

    async def test_current_month_includes_cost_when_pricing_known(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        user = await _make_user(db_session)
        month = _current_month()
        db_session.add(
            AIUsage(
                user_id=user.id,
                month=month,
                total_input_tokens=1_000_000,
                total_output_tokens=1_000_000,
                total_cache_read_tokens=0,
                total_cache_creation_tokens=0,
                estimated_cost=0,
                call_count=1,
            )
        )
        await db_session.commit()

        res = await client.get("/api/admin/ai/usage/stats", cookies=cookies)
        body = res.json()
        assert body["current_month"]["estimated_cost"] == pytest.approx(0.75, abs=1e-9)

    async def test_unknown_model_returns_null_cost(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from flexloop.config import settings

        monkeypatch.setattr(settings, "ai_model", "never-heard-of-this-model")

        cookies = await _make_admin_and_cookie(db_session)
        user = await _make_user(db_session)
        db_session.add(
            AIUsage(
                user_id=user.id,
                month=_current_month(),
                total_input_tokens=1_000,
                total_output_tokens=500,
                total_cache_read_tokens=0,
                total_cache_creation_tokens=0,
                estimated_cost=0,
                call_count=1,
            )
        )
        await db_session.commit()

        res = await client.get("/api/admin/ai/usage/stats", cookies=cookies)
        assert res.status_code == 200
        assert res.json()["current_month"]["estimated_cost"] is None


class TestStatsLast12Months:
    async def test_returns_12_entries(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.get("/api/admin/ai/usage/stats", cookies=cookies)
        body = res.json()
        assert len(body["last_12_months"]) == 12

    async def test_oldest_first_ordering(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.get("/api/admin/ai/usage/stats", cookies=cookies)
        months = [month["month"] for month in res.json()["last_12_months"]]
        assert months == sorted(months)
        assert months[-1] == _current_month()

    async def test_months_with_no_usage_show_zero(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.get("/api/admin/ai/usage/stats", cookies=cookies)
        for month in res.json()["last_12_months"]:
            assert "input_tokens" in month
            assert month["input_tokens"] >= 0


class TestStatsRows:
    async def test_returns_all_rows_by_default(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        user_one = await _make_user(db_session, "u1")
        user_two = await _make_user(db_session, "u2")
        db_session.add_all(
            [
                AIUsage(
                    user_id=user_one.id,
                    month="2026-01",
                    total_input_tokens=100,
                    total_output_tokens=50,
                    total_cache_read_tokens=0,
                    total_cache_creation_tokens=0,
                    estimated_cost=0,
                    call_count=1,
                ),
                AIUsage(
                    user_id=user_two.id,
                    month="2026-02",
                    total_input_tokens=200,
                    total_output_tokens=100,
                    total_cache_read_tokens=0,
                    total_cache_creation_tokens=0,
                    estimated_cost=0,
                    call_count=2,
                ),
            ]
        )
        await db_session.commit()

        res = await client.get("/api/admin/ai/usage/stats", cookies=cookies)
        rows = res.json()["rows"]
        assert len(rows) == 2

    async def test_filter_by_user_id(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        user_one = await _make_user(db_session, "u1")
        user_two = await _make_user(db_session, "u2")
        db_session.add_all(
            [
                AIUsage(
                    user_id=user_one.id,
                    month="2026-01",
                    total_input_tokens=100,
                    total_output_tokens=50,
                    total_cache_read_tokens=0,
                    total_cache_creation_tokens=0,
                    estimated_cost=0,
                    call_count=1,
                ),
                AIUsage(
                    user_id=user_two.id,
                    month="2026-01",
                    total_input_tokens=200,
                    total_output_tokens=100,
                    total_cache_read_tokens=0,
                    total_cache_creation_tokens=0,
                    estimated_cost=0,
                    call_count=2,
                ),
            ]
        )
        await db_session.commit()

        res = await client.get(
            f"/api/admin/ai/usage/stats?user_id={user_one.id}",
            cookies=cookies,
        )
        rows = res.json()["rows"]
        assert len(rows) == 1
        assert rows[0]["user_id"] == user_one.id

    async def test_filter_by_month_range(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        user = await _make_user(db_session)
        db_session.add_all(
            [
                AIUsage(
                    user_id=user.id,
                    month="2025-12",
                    total_input_tokens=10,
                    total_output_tokens=5,
                    total_cache_read_tokens=0,
                    total_cache_creation_tokens=0,
                    estimated_cost=0,
                    call_count=1,
                ),
                AIUsage(
                    user_id=user.id,
                    month="2026-02",
                    total_input_tokens=20,
                    total_output_tokens=10,
                    total_cache_read_tokens=0,
                    total_cache_creation_tokens=0,
                    estimated_cost=0,
                    call_count=1,
                ),
                AIUsage(
                    user_id=user.id,
                    month="2026-04",
                    total_input_tokens=30,
                    total_output_tokens=15,
                    total_cache_read_tokens=0,
                    total_cache_creation_tokens=0,
                    estimated_cost=0,
                    call_count=1,
                ),
            ]
        )
        await db_session.commit()

        res = await client.get(
            "/api/admin/ai/usage/stats?month_from=2026-01&month_to=2026-03",
            cookies=cookies,
        )
        rows = res.json()["rows"]
        assert len(rows) == 1
        assert rows[0]["month"] == "2026-02"
