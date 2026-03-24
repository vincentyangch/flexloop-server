from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.db.engine import get_session
from flexloop.models.measurement import Measurement
from flexloop.schemas.measurement import MeasurementCreate, MeasurementResponse

router = APIRouter(tags=["measurements"])


@router.post("/api/measurements", response_model=MeasurementResponse, status_code=201)
async def create_measurement(
    data: MeasurementCreate, session: AsyncSession = Depends(get_session)
):
    measurement = Measurement(**data.model_dump())
    session.add(measurement)
    await session.commit()
    await session.refresh(measurement)
    return measurement


@router.get(
    "/api/users/{user_id}/measurements", response_model=list[MeasurementResponse]
)
async def list_measurements(
    user_id: int,
    type: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    query = select(Measurement).where(Measurement.user_id == user_id)
    if type:
        query = query.where(Measurement.type == type)
    query = query.order_by(Measurement.date.desc())

    result = await session.execute(query)
    return result.scalars().all()
