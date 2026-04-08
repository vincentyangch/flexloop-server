"""Admin CRUD endpoints for ``Plan`` plus nested day endpoints.

This router has two endpoint groups on the same prefix:

1. Standard 5-endpoint CRUD (list, detail, create, update, delete) that
   reuses ``flexloop.admin.crud`` helpers, matching every other admin
   resource router.
2. Three day-level endpoints (POST/PUT/DELETE /plans/{id}/days[/{N}]) that
   treat a single ``PlanDay`` as the atomic save unit per spec §9.3.

Day endpoints are added in a later task — this commit only wires up the
standard CRUD surface.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from flexloop.admin.auth import require_admin
from flexloop.admin.crud import (
    paginated_response,
    parse_filter_params,
    parse_sort_spec,
)
from flexloop.admin.schemas.common import ListQueryParams, PaginatedResponse
from flexloop.admin.schemas.plans import (
    PlanAdminCreate,
    PlanAdminResponse,
    PlanAdminUpdate,
)
from flexloop.db.engine import get_session
from flexloop.models.plan import ExerciseGroup, Plan, PlanDay

router = APIRouter(prefix="/api/admin/plans", tags=["admin:plans"])

ALLOWED_SORT_COLUMNS = {"id", "name", "created_at", "updated_at", "user_id", "status"}
ALLOWED_FILTER_COLUMNS = {"user_id", "status"}


def _plan_query():
    """Base SELECT with the full nested eager-load chain.

    Three levels deep: Plan → PlanDay.exercise_groups → ExerciseGroup.exercises.
    Every endpoint that returns a PlanAdminResponse must go through this so
    the Pydantic serializer never triggers lazy IO inside the async request.
    """
    return select(Plan).options(
        selectinload(Plan.days)
        .selectinload(PlanDay.exercise_groups)
        .selectinload(ExerciseGroup.exercises)
    )


@router.get("", response_model=PaginatedResponse[PlanAdminResponse])
async def list_plans(
    request: Request,
    params: ListQueryParams = Depends(ListQueryParams.as_dependency),
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> dict:
    query = _plan_query()

    # Filters — plain equality on whitelisted columns.
    filters = parse_filter_params(request.query_params, allowed=ALLOWED_FILTER_COLUMNS)
    for key, value in filters.items():
        query = query.where(getattr(Plan, key) == value)

    # Search — single-column ILIKE on name.
    if params.search:
        like = f"%{params.search}%"
        query = query.where(Plan.name.ilike(like))

    # Sort — default to newest first.
    sort_clauses = parse_sort_spec(
        params.sort, model=Plan, allowed=ALLOWED_SORT_COLUMNS
    )
    if sort_clauses:
        query = query.order_by(*sort_clauses)
    else:
        query = query.order_by(Plan.created_at.desc())

    return await paginated_response(
        db,
        query=query,
        item_schema=PlanAdminResponse,
        page=params.page,
        per_page=params.per_page,
    )


@router.get("/{plan_id}", response_model=PlanAdminResponse)
async def get_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> Plan:
    result = await db.execute(_plan_query().where(Plan.id == plan_id))
    plan = result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="plan not found",
        )
    return plan


@router.post(
    "",
    response_model=PlanAdminResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_plan(
    payload: PlanAdminCreate,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> Plan:
    plan = Plan(**payload.model_dump())
    db.add(plan)
    await db.commit()
    # Refresh with the full eager-load so the response matches the detail
    # endpoint's shape (empty days list populated, timestamps filled in).
    result = await db.execute(_plan_query().where(Plan.id == plan.id))
    return result.scalar_one()


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> None:
    # Eager-load everything so cascade="all, delete-orphan" can walk the tree
    # without issuing lazy lookups during flush.
    result = await db.execute(_plan_query().where(Plan.id == plan_id))
    plan = result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="plan not found",
        )
    await db.delete(plan)
    await db.commit()


@router.put("/{plan_id}", response_model=PlanAdminResponse)
async def update_plan(
    plan_id: int,
    payload: PlanAdminUpdate,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> Plan:
    result = await db.execute(select(Plan).where(Plan.id == plan_id))
    plan = result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="plan not found",
        )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(plan, field, value)

    await db.commit()
    result = await db.execute(_plan_query().where(Plan.id == plan.id))
    return result.scalar_one()
