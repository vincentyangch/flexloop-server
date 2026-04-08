"""Unit tests for flexloop.admin.audit.write_audit_log."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.audit import write_audit_log
from flexloop.admin.auth import hash_password
from flexloop.models.admin_audit_log import AdminAuditLog
from flexloop.models.admin_user import AdminUser


async def _make_admin(db: AsyncSession, username: str = "auditor") -> AdminUser:
    admin = AdminUser(username=username, password_hash=hash_password("password123"))
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    return admin


class TestWriteAuditLog:
    async def test_inserts_a_row(self, db_session: AsyncSession) -> None:
        admin = await _make_admin(db_session)
        entry = await write_audit_log(
            db_session,
            admin_user_id=admin.id,
            action="config_update",
            target_type="app_settings",
            target_id="1",
            before={"ai_provider": "openai"},
            after={"ai_provider": "anthropic"},
        )
        await db_session.commit()
        assert entry.id is not None
        fetched = (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.id == entry.id)
            )
        ).scalar_one()
        assert fetched.admin_user_id == admin.id
        assert fetched.action == "config_update"
        assert fetched.target_type == "app_settings"
        assert fetched.target_id == "1"
        assert fetched.before_json == {"ai_provider": "openai"}
        assert fetched.after_json == {"ai_provider": "anthropic"}
        assert fetched.timestamp is not None

    async def test_accepts_nullable_fields(self, db_session: AsyncSession) -> None:
        admin = await _make_admin(db_session)
        entry = await write_audit_log(
            db_session,
            admin_user_id=admin.id,
            action="plan_delete",
            target_type="plan",
            target_id=None,
            before=None,
            after=None,
        )
        await db_session.commit()
        assert entry.target_id is None
        assert entry.before_json is None
        assert entry.after_json is None

    async def test_does_not_commit_caller_transaction(
        self, db_session: AsyncSession
    ) -> None:
        """The helper must not auto-commit — the caller's transaction owns
        commit boundaries so the audit row + the audited write land atomically.
        """
        admin = await _make_admin(db_session)
        await write_audit_log(
            db_session,
            admin_user_id=admin.id,
            action="test",
            target_type="test",
        )
        # Rollback instead of commit — the audit row should NOT appear.
        await db_session.rollback()
        count = (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "test")
            )
        ).all()
        assert len(count) == 0
