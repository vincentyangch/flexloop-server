"""Admin CRUD endpoints for the ``admin_users`` table itself.

Security notes:
- Passwords are never returned in responses; only ``AdminAdminUserResponse``
  is used as ``response_model``, which has no password fields.
- Create hashes the password with bcrypt via the phase 1 ``hash_password``.
- Update re-hashes the password only when present (partial update).
- Delete refuses to delete the currently-authenticated admin — you can't
  lock yourself out.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import hash_password, require_admin
from flexloop.admin.crud import paginated_response, parse_filter_params, parse_sort_spec
from flexloop.admin.schemas.admin_users import (
    AdminAdminUserCreate,
    AdminAdminUserResponse,
    AdminAdminUserUpdate,
)
from flexloop.admin.schemas.common import ListQueryParams, PaginatedResponse
from flexloop.db.engine import get_session
from flexloop.models.admin_user import AdminUser

router = APIRouter(prefix="/api/admin/admin-users", tags=["admin:admin-users"])

ALLOWED_SORT = {"id", "username", "created_at", "last_login_at"}
ALLOWED_FILTER = {"is_active"}


@router.get("", response_model=PaginatedResponse[AdminAdminUserResponse])
async def list_admin_users(
    request: Request,
    params: ListQueryParams = Depends(ListQueryParams.as_dependency),
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> dict:
    query = select(AdminUser)
    for key, value in parse_filter_params(request.query_params, allowed=ALLOWED_FILTER).items():
        if key == "is_active":
            query = query.where(AdminUser.is_active.is_(value.lower() in ("true", "1")))
        else:
            query = query.where(getattr(AdminUser, key) == value)

    if params.search:
        query = query.where(AdminUser.username.ilike(f"%{params.search}%"))

    sort_clauses = parse_sort_spec(params.sort, model=AdminUser, allowed=ALLOWED_SORT)
    query = query.order_by(*sort_clauses) if sort_clauses else query.order_by(AdminUser.username.asc())

    return await paginated_response(
        db, query=query, item_schema=AdminAdminUserResponse,
        page=params.page, per_page=params.per_page,
    )


@router.get("/{admin_user_id}", response_model=AdminAdminUserResponse)
async def get_admin_user(
    admin_user_id: int,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> AdminUser:
    result = await db.execute(select(AdminUser).where(AdminUser.id == admin_user_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "admin user not found")
    return row


@router.post("", response_model=AdminAdminUserResponse, status_code=201)
async def create_admin_user(
    payload: AdminAdminUserCreate,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> AdminUser:
    # Uniqueness check — prefer a clean 409 over SQL integrity error
    existing = await db.execute(
        select(AdminUser).where(AdminUser.username == payload.username)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "username already exists")

    row = AdminUser(
        username=payload.username,
        password_hash=hash_password(payload.password),
        is_active=payload.is_active,
    )
    db.add(row); await db.commit(); await db.refresh(row)
    return row


@router.put("/{admin_user_id}", response_model=AdminAdminUserResponse)
async def update_admin_user(
    admin_user_id: int,
    payload: AdminAdminUserUpdate,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> AdminUser:
    result = await db.execute(select(AdminUser).where(AdminUser.id == admin_user_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "admin user not found")

    data = payload.model_dump(exclude_unset=True)
    if "password" in data:
        row.password_hash = hash_password(data.pop("password"))
    for field, value in data.items():
        setattr(row, field, value)

    await db.commit(); await db.refresh(row)
    return row


@router.delete("/{admin_user_id}", status_code=204)
async def delete_admin_user(
    admin_user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current=Depends(require_admin),
) -> None:
    if admin_user_id == current.id:
        raise HTTPException(
            status_code=400,
            detail="cannot delete your own admin account; deactivate instead",
        )
    result = await db.execute(select(AdminUser).where(AdminUser.id == admin_user_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "admin user not found")
    await db.delete(row); await db.commit()
