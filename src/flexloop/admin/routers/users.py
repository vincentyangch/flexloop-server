"""Admin CRUD endpoints for the end-user ``User`` table."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import require_admin
from flexloop.admin.crud import (
    paginated_response,
    parse_filter_params,
    parse_sort_spec,
)
from flexloop.admin.schemas.common import ListQueryParams, PaginatedResponse
from flexloop.admin.schemas.users import (
    UserAdminCreate,
    UserAdminResponse,
    UserAdminUpdate,
)
from flexloop.db.engine import get_session
from flexloop.models.user import User

router = APIRouter(prefix="/api/admin/users", tags=["admin:users"])

ALLOWED_SORT_COLUMNS = {"id", "name", "age", "experience_level", "created_at"}
ALLOWED_FILTER_COLUMNS = {"experience_level", "gender"}
SEARCH_COLUMNS = (User.name, User.goals)


@router.get("", response_model=PaginatedResponse[UserAdminResponse])
async def list_users(
    request: Request,
    params: ListQueryParams = Depends(ListQueryParams.as_dependency),
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> dict:
    query = select(User)

    # Filters
    filters = parse_filter_params(request.query_params, allowed=ALLOWED_FILTER_COLUMNS)
    for key, value in filters.items():
        query = query.where(getattr(User, key) == value)

    # Search — OR over SEARCH_COLUMNS with ILIKE
    if params.search:
        like = f"%{params.search}%"
        query = query.where(or_(*(col.ilike(like) for col in SEARCH_COLUMNS)))

    # Sort — default to id asc so tests are deterministic
    sort_clauses = parse_sort_spec(params.sort, model=User, allowed=ALLOWED_SORT_COLUMNS)
    if sort_clauses:
        query = query.order_by(*sort_clauses)
    else:
        query = query.order_by(User.id.asc())

    return await paginated_response(
        db,
        query=query,
        item_schema=UserAdminResponse,
        page=params.page,
        per_page=params.per_page,
    )


@router.get("/{user_id}", response_model=UserAdminResponse)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    return user


@router.post("", response_model=UserAdminResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserAdminCreate,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> User:
    user = User(**payload.model_dump())
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.put("/{user_id}", response_model=UserAdminResponse)
async def update_user(
    user_id: int,
    payload: UserAdminUpdate,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)

    await db.commit()
    await db.refresh(user)
    return user
