"""Admin CRUD endpoints for Measurement."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import require_admin
from flexloop.admin.crud import paginated_response, parse_filter_params, parse_sort_spec
from flexloop.admin.schemas.common import ListQueryParams, PaginatedResponse
from flexloop.admin.schemas.measurements import (
    MeasurementAdminCreate,
    MeasurementAdminResponse,
    MeasurementAdminUpdate,
)
from flexloop.db.engine import get_session
from flexloop.models.measurement import Measurement

router = APIRouter(prefix="/api/admin/measurements", tags=["admin:measurements"])

ALLOWED_SORT = {"id", "date", "value", "type", "user_id"}
ALLOWED_FILTER = {"user_id", "type"}


@router.get("", response_model=PaginatedResponse[MeasurementAdminResponse])
async def list_measurements(
    request: Request,
    params: ListQueryParams = Depends(ListQueryParams.as_dependency),
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> dict:
    query = select(Measurement)

    for key, value in parse_filter_params(request.query_params, allowed=ALLOWED_FILTER).items():
        query = query.where(getattr(Measurement, key) == value)

    if params.search:
        query = query.where(Measurement.notes.ilike(f"%{params.search}%"))

    sort_clauses = parse_sort_spec(params.sort, model=Measurement, allowed=ALLOWED_SORT)
    query = (
        query.order_by(*sort_clauses)
        if sort_clauses
        else query.order_by(Measurement.date.desc())
    )

    return await paginated_response(
        db,
        query=query,
        item_schema=MeasurementAdminResponse,
        page=params.page,
        per_page=params.per_page,
    )


@router.get("/{measurement_id}", response_model=MeasurementAdminResponse)
async def get_measurement(
    measurement_id: int,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> Measurement:
    result = await db.execute(select(Measurement).where(Measurement.id == measurement_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "measurement not found")
    return row


@router.post("", response_model=MeasurementAdminResponse, status_code=201)
async def create_measurement(
    payload: MeasurementAdminCreate,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> Measurement:
    row = Measurement(**payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.put("/{measurement_id}", response_model=MeasurementAdminResponse)
async def update_measurement(
    measurement_id: int,
    payload: MeasurementAdminUpdate,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> Measurement:
    result = await db.execute(select(Measurement).where(Measurement.id == measurement_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "measurement not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/{measurement_id}", status_code=204)
async def delete_measurement(
    measurement_id: int,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin),
) -> None:
    result = await db.execute(select(Measurement).where(Measurement.id == measurement_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "measurement not found")
    await db.delete(row)
    await db.commit()
