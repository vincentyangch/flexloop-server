"""Admin authentication primitives: bcrypt hashing and opaque session tokens.

Sessions are DB-keyed opaque random tokens stored in admin_sessions. There is
no signing — the lookup IS the validation. The cookie value is the token.
"""
import secrets
from datetime import datetime, timedelta

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.db.engine import get_session
from flexloop.models.admin_session import AdminSession
from flexloop.models.admin_user import AdminUser

SESSION_DURATION = timedelta(days=14)
SESSION_COOKIE_NAME = "flexloop_admin_session"


def hash_password(password: str) -> str:
    """Hash a password with bcrypt. Cost factor 12 is the bcrypt default."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Return True if password matches the bcrypt hash. Returns False (not raises)
    if the hash format is invalid/truncated."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


async def create_session(
    db: AsyncSession,
    admin_user_id: int,
    user_agent: str | None = None,
    ip: str | None = None,
) -> tuple[str, datetime]:
    """Create a new session row. Returns (token, expires_at)."""
    token = secrets.token_hex(32)  # 64 hex chars
    now = datetime.utcnow()
    expires_at = now + SESSION_DURATION
    session = AdminSession(
        id=token,
        admin_user_id=admin_user_id,
        created_at=now,
        last_seen_at=now,
        expires_at=expires_at,
        user_agent=user_agent,
        ip_address=ip,
    )
    db.add(session)
    await db.flush()
    return token, expires_at


async def lookup_session(db: AsyncSession, token: str) -> AdminSession | None:
    """Look up a session by token. Bumps last_seen_at and expires_at on hit.

    Returns None if the token doesn't exist, the session has expired, or the
    associated admin user is inactive.
    """
    result = await db.execute(select(AdminSession).where(AdminSession.id == token))
    session = result.scalar_one_or_none()
    if session is None:
        return None

    now = datetime.utcnow()
    if session.expires_at < now:
        return None

    # Verify the associated user is still active (not deleted or deactivated).
    user_result = await db.execute(
        select(AdminUser).where(AdminUser.id == session.admin_user_id)
    )
    user = user_result.scalar_one_or_none()
    if user is None or not user.is_active:
        return None

    # Bump last_seen_at and roll the expiry forward (rolling 14-day window)
    session.last_seen_at = now
    session.expires_at = now + SESSION_DURATION
    await db.flush()
    return session


async def revoke_session(db: AsyncSession, token: str) -> None:
    await db.execute(delete(AdminSession).where(AdminSession.id == token))
    await db.flush()


async def revoke_all_sessions(db: AsyncSession, admin_user_id: int) -> int:
    """Delete every session for a given admin. Returns count removed."""
    result = await db.execute(
        delete(AdminSession).where(AdminSession.admin_user_id == admin_user_id)
    )
    await db.flush()
    return result.rowcount or 0


async def require_admin(
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> AdminUser:
    """FastAPI dependency that enforces an active admin session.

    Stashes the active AdminSession on `request.state.admin_session` so that
    handlers can access it without a duplicate query.

    Used by every admin endpoint except /api/admin/auth/login.
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated"
        )
    session = await lookup_session(db, token)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="session expired"
        )
    # lookup_session already verified the user exists and is_active, so a
    # single fetch is safe — no need to re-check.
    result = await db.execute(select(AdminUser).where(AdminUser.id == session.admin_user_id))
    user = result.scalar_one()
    # Stash the session for downstream handlers (e.g. /me needs expires_at).
    request.state.admin_session = session
    return user
