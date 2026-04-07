import pytest
from datetime import datetime, timedelta
from sqlalchemy import select

from flexloop.models.admin_user import AdminUser
from flexloop.models.admin_session import AdminSession


async def test_admin_user_can_be_created(db_session):
    user = AdminUser(
        username="testadmin",
        password_hash="$2b$12$fakehash",
    )
    db_session.add(user)
    await db_session.flush()
    result = await db_session.execute(select(AdminUser).where(AdminUser.username == "testadmin"))
    loaded = result.scalar_one()
    assert loaded.id is not None
    assert loaded.username == "testadmin"
    assert loaded.is_active is True
    assert loaded.last_login_at is None
    assert loaded.created_at is not None


async def test_admin_session_can_be_created(db_session):
    user = AdminUser(username="sessiontest", password_hash="x")
    db_session.add(user)
    await db_session.flush()

    session = AdminSession(
        id="abc123deadbeef",
        admin_user_id=user.id,
        expires_at=datetime.utcnow() + timedelta(days=14),
    )
    db_session.add(session)
    await db_session.flush()

    result = await db_session.execute(
        select(AdminSession).where(AdminSession.id == "abc123deadbeef")
    )
    loaded = result.scalar_one()
    assert loaded.admin_user_id == user.id
    assert loaded.created_at is not None
    assert loaded.last_seen_at is not None
    assert loaded.expires_at > datetime.utcnow()


from flexloop.models.admin_audit_log import AdminAuditLog
from flexloop.models.app_settings import AppSettings
from flexloop.models.model_pricing import ModelPricing


async def test_admin_audit_log_can_be_created(db_session):
    entry = AdminAuditLog(
        admin_user_id=None,
        action="config.update",
        target_type="app_settings",
        target_id="1",
        before_json={"ai_model": "old"},
        after_json={"ai_model": "new"},
    )
    db_session.add(entry)
    await db_session.flush()
    assert entry.id is not None


async def test_app_settings_can_be_created(db_session):
    row = AppSettings(
        id=1,
        ai_provider="openai",
        ai_model="gpt-4o-mini",
        ai_api_key="sk-test",
        ai_base_url="",
        ai_temperature=0.7,
        ai_max_tokens=2000,
        ai_review_frequency="block",
        ai_review_block_weeks=6,
        admin_allowed_origins=["http://localhost:5173"],
    )
    db_session.add(row)
    await db_session.flush()
    assert row.id == 1
    assert row.admin_allowed_origins == ["http://localhost:5173"]


async def test_model_pricing_can_be_created(db_session):
    row = ModelPricing(
        model_name="custom-proxy-model",
        input_per_million=0.2,
        output_per_million=0.6,
    )
    db_session.add(row)
    await db_session.flush()
    assert row.model_name == "custom-proxy-model"
