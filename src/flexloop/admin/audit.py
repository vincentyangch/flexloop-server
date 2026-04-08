"""Admin audit log writer.

Every administrative mutation that needs an audit trail goes through
``write_audit_log``. The helper takes the caller's ``AsyncSession`` and
appends a row without committing — the caller controls the transaction
boundary so the audit entry and the audited write commit atomically.

For config updates the typical use is:

    before = _masked_config_dict(current)
    # mutate app_settings row
    after = _masked_config_dict(current)
    await write_audit_log(
        db,
        admin_user_id=admin.id,
        action="config_update",
        target_type="app_settings",
        target_id="1",
        before=before,
        after=after,
    )
    await db.commit()

API keys MUST be masked before being passed into ``before``/``after`` —
see ``flexloop.admin.routers.config`` for the masking helper used there.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.models.admin_audit_log import AdminAuditLog


async def write_audit_log(
    db: AsyncSession,
    *,
    admin_user_id: int,
    action: str,
    target_type: str,
    target_id: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
) -> AdminAuditLog:
    """Append an admin_audit_log row.

    Does NOT commit — the caller owns the transaction. Returns the newly
    added row (with ``id`` populated once the caller flushes/commits).
    """
    entry = AdminAuditLog(
        admin_user_id=admin_user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        before_json=before,
        after_json=after,
    )
    db.add(entry)
    await db.flush()
    return entry
