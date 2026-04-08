"""Admin CRUD endpoints for ``WorkoutSession``.

Mirrors the canonical users router pattern (list/get/post/put/delete) with two
workout-specific twists:

1. Sets are embedded in every response. We use ``selectinload(WorkoutSession.sets)``
   on every query path so the ORM eager-loads the sets relationship instead of
   triggering lazy IO inside the Pydantic serializer. After create/update we
   ``db.refresh(..., attribute_names=["sets"])`` to populate the now-empty
   relationship on the freshly inserted/updated row.

2. ``filter[completed]`` is a derived predicate, not a column-equality check:
   ``true`` maps to ``completed_at IS NOT NULL`` and ``false`` maps to
   ``completed_at IS NULL``. Anything else is a 400.
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
from flexloop.admin.schemas.workouts import (
    WorkoutSessionAdminCreate,
    WorkoutSessionAdminResponse,
    WorkoutSessionAdminUpdate,
)
from flexloop.db.engine import get_session
from flexloop.models.workout import WorkoutSession

router = APIRouter(prefix="/api/admin/workouts", tags=["admin:workouts"])

ALLOWED_SORT_COLUMNS = {"id", "started_at", "completed_at", "user_id", "source"}
# ``completed`` is handled specially below (derived from ``completed_at``),
# all others are plain column-equality filters.
ALLOWED_FILTER_COLUMNS = {"user_id", "source", "template_id", "plan_day_id", "completed"}


@router.get("", response_model=PaginatedResponse[WorkoutSessionAdminResponse])
async def list_workouts(
    request: Request,
    params: ListQueryParams = Depends(ListQueryParams.as_dependency),
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> dict:
    query = select(WorkoutSession).options(selectinload(WorkoutSession.sets))

    # Filters
    filters = parse_filter_params(request.query_params, allowed=ALLOWED_FILTER_COLUMNS)
    for key, value in filters.items():
        if key == "completed":
            if value.lower() in ("true", "1", "yes"):
                query = query.where(WorkoutSession.completed_at.is_not(None))
            elif value.lower() in ("false", "0", "no"):
                query = query.where(WorkoutSession.completed_at.is_(None))
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="filter[completed] must be true or false",
                )
        else:
            query = query.where(getattr(WorkoutSession, key) == value)

    # Search — single-column ILIKE on notes
    if params.search:
        like = f"%{params.search}%"
        query = query.where(WorkoutSession.notes.ilike(like))

    # Sort — default to started_at desc so the most recent sessions come first
    sort_clauses = parse_sort_spec(
        params.sort, model=WorkoutSession, allowed=ALLOWED_SORT_COLUMNS
    )
    if sort_clauses:
        query = query.order_by(*sort_clauses)
    else:
        query = query.order_by(WorkoutSession.started_at.desc())

    return await paginated_response(
        db,
        query=query,
        item_schema=WorkoutSessionAdminResponse,
        page=params.page,
        per_page=params.per_page,
    )


@router.get("/{workout_id}", response_model=WorkoutSessionAdminResponse)
async def get_workout(
    workout_id: int,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> WorkoutSession:
    result = await db.execute(
        select(WorkoutSession)
        .options(selectinload(WorkoutSession.sets))
        .where(WorkoutSession.id == workout_id)
    )
    ws = result.scalar_one_or_none()
    if ws is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="workout session not found",
        )
    return ws


@router.post(
    "",
    response_model=WorkoutSessionAdminResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_workout(
    payload: WorkoutSessionAdminCreate,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> WorkoutSession:
    ws = WorkoutSession(**payload.model_dump())
    db.add(ws)
    await db.commit()
    # Populate ``sets`` relationship (empty list for a freshly created session)
    # so the response serializer doesn't lazy-load inside the async context.
    await db.refresh(ws, attribute_names=["sets"])
    return ws


@router.put("/{workout_id}", response_model=WorkoutSessionAdminResponse)
async def update_workout(
    workout_id: int,
    payload: WorkoutSessionAdminUpdate,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> WorkoutSession:
    result = await db.execute(
        select(WorkoutSession)
        .options(selectinload(WorkoutSession.sets))
        .where(WorkoutSession.id == workout_id)
    )
    ws = result.scalar_one_or_none()
    if ws is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="workout session not found",
        )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(ws, field, value)

    await db.commit()
    await db.refresh(ws, attribute_names=["sets"])
    return ws


@router.delete("/{workout_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workout(
    workout_id: int,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> None:
    result = await db.execute(
        select(WorkoutSession).where(WorkoutSession.id == workout_id)
    )
    ws = result.scalar_one_or_none()
    if ws is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="workout session not found",
        )
    await db.delete(ws)
    await db.commit()
