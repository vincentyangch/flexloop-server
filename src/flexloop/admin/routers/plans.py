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
    PlanDayAdminCreate,
    PlanDayAdminResponse,
    PlanDayAdminUpdate,
)
from flexloop.db.engine import get_session
from flexloop.models.plan import ExerciseGroup, Plan, PlanDay, PlanExercise

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


def _day_query(plan_id: int, day_number: int):
    """Eager-loaded SELECT for a single day on a specific plan."""
    return (
        select(PlanDay)
        .options(
            selectinload(PlanDay.exercise_groups).selectinload(ExerciseGroup.exercises)
        )
        .where(PlanDay.plan_id == plan_id, PlanDay.day_number == day_number)
    )


async def _apply_groups_to_day(
    db: AsyncSession, day: PlanDay, groups_payload: list
) -> None:
    """Add a list of ExerciseGroupAdminCreate payloads onto a clean day.

    Uses explicit db.add() + flush per group (rather than relationship
    .append()) to avoid triggering lazy-load IO outside greenlet context.
    Caller is responsible for clearing the day's existing groups/exercises
    first (for PUT) — this helper only adds.
    """
    for group_payload in groups_payload:
        group = ExerciseGroup(
            plan_day_id=day.id,
            group_type=group_payload.group_type,
            order=group_payload.order,
            rest_after_group_sec=group_payload.rest_after_group_sec,
        )
        db.add(group)
        await db.flush()  # populates group.id for PlanExercise FK
        for ex_payload in group_payload.exercises:
            plan_ex = PlanExercise(
                plan_day_id=day.id,
                exercise_group_id=group.id,
                exercise_id=ex_payload.exercise_id,
                order=ex_payload.order,
                sets=ex_payload.sets,
                reps=ex_payload.reps,
                weight=ex_payload.weight,
                rpe_target=ex_payload.rpe_target,
                sets_json=(
                    [s.model_dump() for s in ex_payload.sets_json]
                    if ex_payload.sets_json
                    else None
                ),
                notes=ex_payload.notes,
            )
            db.add(plan_ex)


@router.post(
    "/{plan_id}/days",
    response_model=PlanDayAdminResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_plan_day(
    plan_id: int,
    payload: PlanDayAdminCreate,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> PlanDay:
    # Verify the plan exists (we don't need the eager-load here).
    plan_result = await db.execute(select(Plan).where(Plan.id == plan_id))
    plan = plan_result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="plan not found",
        )

    # Reject duplicate day_number — no auto-renumbering.
    existing = await db.execute(
        select(PlanDay).where(
            PlanDay.plan_id == plan_id, PlanDay.day_number == payload.day_number
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"day_number {payload.day_number} already exists on this plan",
        )

    day = PlanDay(
        plan_id=plan_id,
        day_number=payload.day_number,
        label=payload.label,
        focus=payload.focus,
    )
    db.add(day)
    await db.flush()  # gives us day.id for the nested appends

    await _apply_groups_to_day(db, day, payload.exercise_groups)

    await db.commit()

    # Re-query with the full eager-load for a clean response payload.
    result = await db.execute(_day_query(plan_id, payload.day_number))
    return result.scalar_one()


@router.put(
    "/{plan_id}/days/{day_number}",
    response_model=PlanDayAdminResponse,
)
async def replace_plan_day(
    plan_id: int,
    day_number: int,
    payload: PlanDayAdminUpdate,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> PlanDay:
    # Verify the plan exists separately from the day so we can return
    # "plan not found" vs "day not found" accurately.
    plan_result = await db.execute(select(Plan).where(Plan.id == plan_id))
    plan = plan_result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="plan not found",
        )

    day_result = await db.execute(_day_query(plan_id, day_number))
    day = day_result.scalar_one_or_none()
    if day is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"day_number {day_number} not found on plan {plan_id}",
        )

    # Apply optional metadata updates.
    if payload.label is not None:
        day.label = payload.label
    if payload.focus is not None:
        day.focus = payload.focus

    # Clear existing nested structure. Both collections have
    # cascade="all, delete-orphan" on PlanDay, so clearing triggers deletes.
    # We clear exercises first (child) then groups (parent) to avoid FK issues.
    for group in list(day.exercise_groups):
        for ex in list(group.exercises):
            await db.delete(ex)
    await db.flush()
    for group in list(day.exercise_groups):
        await db.delete(group)
    await db.flush()

    # Append new groups/exercises from the payload.
    await _apply_groups_to_day(db, day, payload.exercise_groups)

    await db.commit()

    # Expire the day so the identity map re-fetches it fresh on re-query.
    db.expire(day)
    result = await db.execute(_day_query(plan_id, day_number))
    return result.scalar_one()


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
    result = await db.execute(_plan_query().where(Plan.id == plan_id))
    plan = result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="plan not found",
        )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(plan, field, value)

    await db.commit()
    await db.refresh(plan)
    return plan
