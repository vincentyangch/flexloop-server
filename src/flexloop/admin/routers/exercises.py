"""Admin CRUD endpoints for Exercise."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import require_admin
from flexloop.admin.crud import paginated_response, parse_filter_params, parse_sort_spec
from flexloop.admin.schemas.common import ListQueryParams, PaginatedResponse
from flexloop.admin.schemas.exercises import (
    ExerciseAdminCreate,
    ExerciseAdminResponse,
    ExerciseAdminUpdate,
)
from flexloop.db.engine import get_session
from flexloop.models.exercise import Exercise

router = APIRouter(prefix="/api/admin/exercises", tags=["admin:exercises"])

ALLOWED_SORT = {"id", "name", "muscle_group", "equipment", "category", "difficulty"}
ALLOWED_FILTER = {"muscle_group", "equipment", "category", "difficulty", "source_plugin"}


@router.get("", response_model=PaginatedResponse[ExerciseAdminResponse])
async def list_exercises(
    request: Request,
    params: ListQueryParams = Depends(ListQueryParams.as_dependency),
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> dict:
    query = select(Exercise)
    for key, value in parse_filter_params(request.query_params, allowed=ALLOWED_FILTER).items():
        query = query.where(getattr(Exercise, key) == value)

    if params.search:
        query = query.where(Exercise.name.ilike(f"%{params.search}%"))

    sort_clauses = parse_sort_spec(params.sort, model=Exercise, allowed=ALLOWED_SORT)
    query = query.order_by(*sort_clauses) if sort_clauses else query.order_by(Exercise.name.asc())

    return await paginated_response(
        db, query=query, item_schema=ExerciseAdminResponse,
        page=params.page, per_page=params.per_page,
    )


@router.get("/{exercise_id}", response_model=ExerciseAdminResponse)
async def get_exercise(
    exercise_id: int,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> Exercise:
    result = await db.execute(select(Exercise).where(Exercise.id == exercise_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "exercise not found")
    return row


@router.post("", response_model=ExerciseAdminResponse, status_code=201)
async def create_exercise(
    payload: ExerciseAdminCreate,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> Exercise:
    row = Exercise(**payload.model_dump())
    db.add(row); await db.commit(); await db.refresh(row)
    return row


@router.put("/{exercise_id}", response_model=ExerciseAdminResponse)
async def update_exercise(
    exercise_id: int,
    payload: ExerciseAdminUpdate,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> Exercise:
    result = await db.execute(select(Exercise).where(Exercise.id == exercise_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "exercise not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    await db.commit(); await db.refresh(row)
    return row


@router.delete("/{exercise_id}", status_code=204)
async def delete_exercise(
    exercise_id: int,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> None:
    result = await db.execute(select(Exercise).where(Exercise.id == exercise_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "exercise not found")
    await db.delete(row); await db.commit()
