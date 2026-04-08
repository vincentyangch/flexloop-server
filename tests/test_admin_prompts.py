"""Integration tests for /api/admin/prompts."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import SESSION_COOKIE_NAME, create_session, hash_password
from flexloop.admin.routers.prompts import get_prompts_dir
from flexloop.main import app
from flexloop.models.admin_user import AdminUser


ORIGIN = "http://localhost:5173"


async def _make_admin_and_cookie(db: AsyncSession) -> dict[str, str]:
    admin = AdminUser(username="tester", password_hash=hash_password("password123"))
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    token, _ = await create_session(db, admin_user_id=admin.id)
    return {SESSION_COOKIE_NAME: token}


@pytest.fixture
def prompts_tmp_dir(tmp_path: Path) -> Path:
    """Seed a minimal prompts directory and override the router dependency."""
    (tmp_path / "plan_generation").mkdir()
    (tmp_path / "plan_generation" / "v1.md").write_text("v1 original content")
    (tmp_path / "plan_generation" / "v2.md").write_text("v2 {{user_name}}")
    (tmp_path / "chat").mkdir()
    (tmp_path / "chat" / "v1.md").write_text("chat v1 {{message}}")
    manifest = {
        "plan_generation": {"default": "v2"},
        "chat": {"default": "v1"},
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))

    app.dependency_overrides[get_prompts_dir] = lambda: tmp_path
    yield tmp_path
    app.dependency_overrides.pop(get_prompts_dir, None)


class TestListPromptsEndpoint:
    async def test_requires_auth(
        self, client: AsyncClient, prompts_tmp_dir: Path
    ) -> None:
        assert (await client.get("/api/admin/prompts")).status_code == 401

    async def test_returns_all_prompts(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        prompts_tmp_dir: Path,
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.get("/api/admin/prompts", cookies=cookies)
        assert res.status_code == 200
        body = res.json()
        assert "prompts" in body
        by_name = {p["name"]: p for p in body["prompts"]}
        assert "plan_generation" in by_name
        assert by_name["plan_generation"]["versions"] == ["v1", "v2"]
        assert by_name["plan_generation"]["active_by_provider"] == {"default": "v2"}
        assert "chat" in by_name
        assert by_name["chat"]["versions"] == ["v1"]
