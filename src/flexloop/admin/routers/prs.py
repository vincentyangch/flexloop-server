"""Admin CRUD endpoints for PersonalRecord."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import require_admin
from flexloop.admin.crud import paginated_response, parse_filter_params, parse_sort_spec
from flexloop.admin.schemas.common import ListQueryParams, PaginatedResponse
from flexloop.admin.schemas.prs import (
    PersonalRecordAdminCreate,
    PersonalRecordAdminResponse,
    PersonalRecordAdminUpdate,
)
from flexloop.db.engine import get_session
from flexloop.models.personal_record import PersonalRecord

router = APIRouter(prefix="/api/admin/prs", tags=["admin:prs"])

ALLOWED_SORT = {"id", "achieved_at", "value", "user_id", "exercise_id"}
ALLOWED_FILTER = {"user_id", "exercise_id", "pr_type"}


@router.get("", response_model=PaginatedResponse[PersonalRecordAdminResponse])
async def list_prs(
    request: Request,
    params: ListQueryParams = Depends(ListQueryParams.as_dependency),
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> dict:
    query = select(PersonalRecord)
    for key, value in parse_filter_params(request.query_params, allowed=ALLOWED_FILTER).items():
        query = query.where(getattr(PersonalRecord, key) == value)

    sort_clauses = parse_sort_spec(params.sort, model=PersonalRecord, allowed=ALLOWED_SORT)
    query = (
        query.order_by(*sort_clauses)
        if sort_clauses
        else query.order_by(PersonalRecord.achieved_at.desc())
    )

    return await paginated_response(
        db,
        query=query,
        item_schema=PersonalRecordAdminResponse,
        page=params.page,
        per_page=params.per_page,
    )


@router.get("/{pr_id}", response_model=PersonalRecordAdminResponse)
async def get_pr(
    pr_id: int,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> PersonalRecord:
    result = await db.execute(select(PersonalRecord).where(PersonalRecord.id == pr_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "personal record not found")
    return row


@router.post("", response_model=PersonalRecordAdminResponse, status_code=201)
async def create_pr(
    payload: PersonalRecordAdminCreate,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> PersonalRecord:
    row = PersonalRecord(**payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.put("/{pr_id}", response_model=PersonalRecordAdminResponse)
async def update_pr(
    pr_id: int,
    payload: PersonalRecordAdminUpdate,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> PersonalRecord:
    result = await db.execute(select(PersonalRecord).where(PersonalRecord.id == pr_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "personal record not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/{pr_id}", status_code=204)
async def delete_pr(
    pr_id: int,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> None:
    result = await db.execute(select(PersonalRecord).where(PersonalRecord.id == pr_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "personal record not found")
    await db.delete(row)
    await db.commit()
