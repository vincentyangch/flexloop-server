from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.db.engine import get_session
from flexloop.models.workout import WorkoutSession, WorkoutSet


class SyncSetData(BaseModel):
    exercise_id: int
    exercise_group_id: int | None = None
    set_number: int
    set_type: str = "working"
    weight: float | None = None
    reps: int | None = None
    rpe: float | None = None
    duration_sec: int | None = None
    distance_m: float | None = None
    rest_sec: int | None = None


class SyncWorkoutData(BaseModel):
    plan_day_id: int | None = None
    template_id: int | None = None
    source: str = "ad_hoc"
    started_at: datetime
    completed_at: datetime | None = None
    notes: str | None = None
    sets: list[SyncSetData] = []


class SyncRequest(BaseModel):
    user_id: int
    workouts: list[SyncWorkoutData] = []


class SyncResponse(BaseModel):
    workouts_synced: int


router = APIRouter(tags=["sync"])


@router.post("/api/sync", response_model=SyncResponse)
async def sync_data(data: SyncRequest, session: AsyncSession = Depends(get_session)):
    synced = 0

    for workout_data in data.workouts:
        workout = WorkoutSession(
            user_id=data.user_id,
            plan_day_id=workout_data.plan_day_id,
            template_id=workout_data.template_id,
            source=workout_data.source,
            started_at=workout_data.started_at,
            completed_at=workout_data.completed_at,
            notes=workout_data.notes,
        )
        session.add(workout)
        await session.flush()

        for set_data in workout_data.sets:
            workout_set = WorkoutSet(
                session_id=workout.id,
                **set_data.model_dump(),
            )
            session.add(workout_set)

        synced += 1

    await session.commit()
    return SyncResponse(workouts_synced=synced)
