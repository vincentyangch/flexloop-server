"""Admin auth router: /api/admin/auth/*"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import (
    SESSION_COOKIE_NAME,
    SESSION_DURATION,
    create_session,
    hash_password,
    require_admin,
    revoke_session,
    verify_password,
)
from flexloop.db.engine import get_session
from flexloop.models.admin_session import AdminSession
from flexloop.models.admin_user import AdminUser

router = APIRouter(prefix="/api/admin/auth", tags=["admin:auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class LoginResponse(BaseModel):
    ok: bool
    username: str
    expires_at: datetime


class MeResponse(BaseModel):
    username: str
    expires_at: datetime


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=256)


class SessionInfo(BaseModel):
    id: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    user_agent: str | None
    ip_address: str | None
    is_current: bool


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=int(SESSION_DURATION.total_seconds()),
        httponly=True,
        secure=True,
        samesite="strict",
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=True,
        samesite="strict",
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    data: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(select(AdminUser).where(AdminUser.username == data.username))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(data.password, user.password_hash):
        # Generic error message — do not reveal whether the user exists
        raise HTTPException(status_code=401, detail="invalid credentials")

    token, expires_at = await create_session(
        db,
        admin_user_id=user.id,
        user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client else None,
    )
    user.last_login_at = datetime.utcnow()
    await db.commit()

    _set_session_cookie(response, token)
    return LoginResponse(
        ok=True,
        username=user.username,
        expires_at=expires_at,  # use the authoritative value from create_session
    )


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_session),
):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        await revoke_session(db, token)
        await db.commit()
    _clear_session_cookie(response)
    return {"ok": True}


@router.get("/me", response_model=MeResponse)
async def me(
    request: Request,
    user: AdminUser = Depends(require_admin),
):
    session = request.state.admin_session
    return MeResponse(username=user.username, expires_at=session.expires_at)


@router.post("/change-password")
async def change_password(
    request: Request,
    data: ChangePasswordRequest,
    db: AsyncSession = Depends(get_session),
    user: AdminUser = Depends(require_admin),
):
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="current password incorrect")
    user.password_hash = hash_password(data.new_password)

    # Revoke all OTHER sessions for this admin (keeps the current session alive
    # so the user isn't logged out of their active browser; but kicks any
    # attacker who had stolen a different session).
    current_token = request.cookies.get(SESSION_COOKIE_NAME)
    await db.execute(
        delete(AdminSession).where(
            AdminSession.admin_user_id == user.id,
            AdminSession.id != current_token,
        )
    )

    await db.commit()
    return {"ok": True}


@router.get("/sessions", response_model=list[SessionInfo])
async def list_sessions(
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: AdminUser = Depends(require_admin),
):
    current_token = request.cookies.get(SESSION_COOKIE_NAME)
    result = await db.execute(
        select(AdminSession)
        .where(AdminSession.admin_user_id == user.id)
        .order_by(AdminSession.created_at.desc())
    )
    sessions = result.scalars().all()
    return [
        SessionInfo(
            id=s.id,
            created_at=s.created_at,
            last_seen_at=s.last_seen_at,
            expires_at=s.expires_at,
            user_agent=s.user_agent,
            ip_address=s.ip_address,
            is_current=(s.id == current_token),
        )
        for s in sessions
    ]


@router.delete("/sessions/{session_id}")
async def revoke_specific_session(
    session_id: str,
    db: AsyncSession = Depends(get_session),
    user: AdminUser = Depends(require_admin),
):
    # Make sure the session belongs to the current admin
    result = await db.execute(
        select(AdminSession).where(
            AdminSession.id == session_id,
            AdminSession.admin_user_id == user.id,
        )
    )
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="session not found")
    await revoke_session(db, session_id)
    await db.commit()
    return {"ok": True}
