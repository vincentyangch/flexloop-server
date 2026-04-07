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
