import pytest
from sqlalchemy import select

from flexloop.models.admin_user import AdminUser


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
