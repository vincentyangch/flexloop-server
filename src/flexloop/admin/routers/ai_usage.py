"""Admin CRUD endpoints for AIUsage."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import require_admin
from flexloop.admin.crud import paginated_response, parse_filter_params, parse_sort_spec
from flexloop.admin.schemas.ai_usage import (
    AIUsageAdminCreate,
    AIUsageAdminResponse,
    AIUsageAdminUpdate,
)
from flexloop.admin.schemas.common import ListQueryParams, PaginatedResponse
from flexloop.db.engine import get_session
from flexloop.models.ai import AIUsage

router = APIRouter(prefix="/api/admin/ai/usage", tags=["admin:ai-usage"])

ALLOWED_SORT = {"id", "month", "estimated_cost", "call_count", "user_id"}
ALLOWED_FILTER = {"user_id", "month"}


@router.get("", response_model=PaginatedResponse[AIUsageAdminResponse])
async def list_ai_usage(
    request: Request,
    params: ListQueryParams = Depends(ListQueryParams.as_dependency),
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> dict:
    query = select(AIUsage)
    for key, value in parse_filter_params(request.query_params, allowed=ALLOWED_FILTER).items():
        query = query.where(getattr(AIUsage, key) == value)

    sort_clauses = parse_sort_spec(params.sort, model=AIUsage, allowed=ALLOWED_SORT)
    query = query.order_by(*sort_clauses) if sort_clauses else query.order_by(AIUsage.month.desc())

    return await paginated_response(
        db, query=query, item_schema=AIUsageAdminResponse,
        page=params.page, per_page=params.per_page,
    )


@router.get("/{usage_id}", response_model=AIUsageAdminResponse)
async def get_ai_usage(
    usage_id: int,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> AIUsage:
    result = await db.execute(select(AIUsage).where(AIUsage.id == usage_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "ai usage row not found")
    return row


@router.post("", response_model=AIUsageAdminResponse, status_code=201)
async def create_ai_usage(
    payload: AIUsageAdminCreate,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> AIUsage:
    row = AIUsage(**payload.model_dump())
    db.add(row); await db.commit(); await db.refresh(row)
    return row


@router.put("/{usage_id}", response_model=AIUsageAdminResponse)
async def update_ai_usage(
    usage_id: int,
    payload: AIUsageAdminUpdate,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> AIUsage:
    result = await db.execute(select(AIUsage).where(AIUsage.id == usage_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "ai usage row not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    await db.commit(); await db.refresh(row)
    return row


@router.delete("/{usage_id}", status_code=204)
async def delete_ai_usage(
    usage_id: int,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> None:
    result = await db.execute(select(AIUsage).where(AIUsage.id == usage_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "ai usage row not found")
    await db.delete(row); await db.commit()
