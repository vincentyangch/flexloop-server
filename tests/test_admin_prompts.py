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


class TestGetVersion:
    async def test_requires_auth(
        self, client: AsyncClient, prompts_tmp_dir: Path
    ) -> None:
        res = await client.get("/api/admin/prompts/plan_generation/versions/v1")
        assert res.status_code == 401

    async def test_returns_content_and_variables(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        prompts_tmp_dir: Path,
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.get(
            "/api/admin/prompts/plan_generation/versions/v2",
            cookies=cookies,
        )
        assert res.status_code == 200
        body = res.json()
        assert body["name"] == "plan_generation"
        assert body["version"] == "v2"
        assert body["content"] == "v2 {{user_name}}"
        assert body["variables"] == ["user_name"]

    async def test_404_when_missing(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        prompts_tmp_dir: Path,
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.get(
            "/api/admin/prompts/plan_generation/versions/v99",
            cookies=cookies,
        )
        assert res.status_code == 404

    async def test_400_on_invalid_name(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        prompts_tmp_dir: Path,
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.get(
            "/api/admin/prompts/Bad-Name/versions/v1",
            cookies=cookies,
        )
        assert res.status_code == 400


class TestUpdateVersion:
    async def test_requires_auth(
        self, client: AsyncClient, prompts_tmp_dir: Path
    ) -> None:
        res = await client.put(
            "/api/admin/prompts/plan_generation/versions/v1",
            json={"content": "x"},
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 401

    async def test_updates_content(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        prompts_tmp_dir: Path,
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.put(
            "/api/admin/prompts/plan_generation/versions/v1",
            json={"content": "brand new content"},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 200
        # Returns the new content + variables
        body = res.json()
        assert body["content"] == "brand new content"
        assert body["variables"] == []
        # File on disk reflects the update
        assert (prompts_tmp_dir / "plan_generation" / "v1.md").read_text() == (
            "brand new content"
        )

    async def test_404_missing_version(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        prompts_tmp_dir: Path,
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.put(
            "/api/admin/prompts/plan_generation/versions/v99",
            json={"content": "x"},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 404

    async def test_400_invalid_name(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        prompts_tmp_dir: Path,
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.put(
            "/api/admin/prompts/Bad/versions/v1",
            json={"content": "x"},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 400

    async def test_rejects_unknown_payload_fields(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        prompts_tmp_dir: Path,
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.put(
            "/api/admin/prompts/plan_generation/versions/v1",
            json={"content": "x", "rogue_field": True},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 422


class TestCreateVersionEndpoint:
    async def test_requires_auth(
        self, client: AsyncClient, prompts_tmp_dir: Path
    ) -> None:
        res = await client.post(
            "/api/admin/prompts/plan_generation/versions",
            json={},
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 401

    async def test_clones_active_version(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        prompts_tmp_dir: Path,
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.post(
            "/api/admin/prompts/plan_generation/versions",
            json={},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 201
        body = res.json()
        assert body["version"] == "v3"
        assert body["content"] == "v2 {{user_name}}"  # cloned from active v2
        assert body["variables"] == ["user_name"]
        # File on disk
        assert (prompts_tmp_dir / "plan_generation" / "v3.md").read_text() == (
            "v2 {{user_name}}"
        )

    async def test_404_missing_prompt(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        prompts_tmp_dir: Path,
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.post(
            "/api/admin/prompts/nonexistent/versions",
            json={},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 404
