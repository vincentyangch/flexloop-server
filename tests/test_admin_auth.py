import asyncio
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from flexloop.admin.auth import (
    create_session,
    hash_password,
    lookup_session,
    require_admin,
    revoke_all_sessions,
    revoke_session,
    verify_password,
)
from flexloop.admin.bootstrap import create_admin_user, reset_admin_password
from flexloop.models.admin_audit_log import AdminAuditLog
from flexloop.models.admin_session import AdminSession
from flexloop.models.admin_user import AdminUser
from flexloop.models.app_settings import AppSettings
from flexloop.models.model_pricing import ModelPricing


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


def test_hash_and_verify_password_roundtrip():
    h = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", h) is True
    assert verify_password("wrong password", h) is False


async def test_create_and_lookup_session(db_session):
    user = AdminUser(username="authu1", password_hash=hash_password("pw"))
    db_session.add(user)
    await db_session.flush()

    token = await create_session(db_session, admin_user_id=user.id, user_agent="test-ua", ip="127.0.0.1")
    assert isinstance(token, str)
    assert len(token) == 64  # 32 bytes hex

    loaded = await lookup_session(db_session, token)
    assert loaded is not None
    assert loaded.admin_user_id == user.id
    assert loaded.user_agent == "test-ua"


async def test_lookup_session_returns_none_for_unknown_token(db_session):
    assert await lookup_session(db_session, "nonexistent") is None


async def test_revoke_session(db_session):
    user = AdminUser(username="authu2", password_hash=hash_password("pw"))
    db_session.add(user)
    await db_session.flush()
    token = await create_session(db_session, admin_user_id=user.id)

    await revoke_session(db_session, token)
    assert await lookup_session(db_session, token) is None


async def test_revoke_all_sessions(db_session):
    user = AdminUser(username="revokeall", password_hash=hash_password("pw"))
    db_session.add(user)
    await db_session.flush()

    # Create 3 sessions for this user
    token1 = await create_session(db_session, admin_user_id=user.id)
    token2 = await create_session(db_session, admin_user_id=user.id)
    token3 = await create_session(db_session, admin_user_id=user.id)

    count = await revoke_all_sessions(db_session, admin_user_id=user.id)
    assert count == 3

    # All three should be gone
    assert await lookup_session(db_session, token1) is None
    assert await lookup_session(db_session, token2) is None
    assert await lookup_session(db_session, token3) is None


async def test_lookup_session_rejects_expired(db_session):
    user = AdminUser(username="authu3", password_hash=hash_password("pw"))
    db_session.add(user)
    await db_session.flush()

    # Manually create an expired session
    sess = AdminSession(
        id="expired_token",
        admin_user_id=user.id,
        expires_at=datetime.utcnow() - timedelta(seconds=1),
    )
    db_session.add(sess)
    await db_session.flush()

    assert await lookup_session(db_session, "expired_token") is None


async def test_lookup_session_bumps_last_seen_and_expiry(db_session):
    user = AdminUser(username="authu4", password_hash=hash_password("pw"))
    db_session.add(user)
    await db_session.flush()
    token = await create_session(db_session, admin_user_id=user.id)

    result = await db_session.execute(select(AdminSession).where(AdminSession.id == token))
    before = result.scalar_one()
    original_expiry = before.expires_at
    original_last_seen = before.last_seen_at

    # Wait a moment then look up again
    await asyncio.sleep(0.01)
    await lookup_session(db_session, token)

    result = await db_session.execute(select(AdminSession).where(AdminSession.id == token))
    after = result.scalar_one()
    assert after.last_seen_at > original_last_seen
    assert after.expires_at > original_expiry


async def test_create_admin_user(db_session):
    user = await create_admin_user(db_session, "newadmin", "mypassword123")
    assert user.id is not None
    assert user.username == "newadmin"
    assert verify_password("mypassword123", user.password_hash)


async def test_create_admin_user_rejects_duplicate(db_session):
    await create_admin_user(db_session, "dup", "pw123456")
    with pytest.raises(ValueError, match="already exists"):
        await create_admin_user(db_session, "dup", "pw789012")


async def test_reset_admin_password(db_session):
    await create_admin_user(db_session, "resetme", "oldpw1234")
    await reset_admin_password(db_session, "resetme", "newpw5678")

    result = await db_session.execute(select(AdminUser).where(AdminUser.username == "resetme"))
    user = result.scalar_one()
    assert verify_password("newpw5678", user.password_hash)
    assert not verify_password("oldpw1234", user.password_hash)


async def test_reset_admin_password_rejects_unknown(db_session):
    with pytest.raises(ValueError, match="not found"):
        await reset_admin_password(db_session, "nobody", "pw123456")
