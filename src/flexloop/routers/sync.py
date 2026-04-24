from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.db.engine import get_session
from flexloop.models.cycle_tracker import CycleTracker
from flexloop.models.plan import Plan, PlanDay
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
    source: str = "plan"
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


async def _advance_cycle_for_synced_workout(
    data: SyncRequest,
    workout_data: SyncWorkoutData,
    session: AsyncSession,
) -> None:
    if (
        workout_data.source != "plan"
        or workout_data.plan_day_id is None
        or workout_data.completed_at is None
    ):
        return

    result = await session.execute(
        select(CycleTracker).where(CycleTracker.user_id == data.user_id)
    )
    tracker = result.scalar_one_or_none()
    if not tracker:
        return

    day_result = await session.execute(
        select(PlanDay).where(
            PlanDay.id == workout_data.plan_day_id,
            PlanDay.plan_id == tracker.plan_id,
            PlanDay.day_number == tracker.next_day_number,
        )
    )
    completed_day = day_result.scalar_one_or_none()
    if not completed_day:
        return

    plan_result = await session.execute(select(Plan).where(Plan.id == tracker.plan_id))
    plan = plan_result.scalar_one_or_none()
    if not plan:
        return

    tracker.next_day_number = (tracker.next_day_number % plan.cycle_length) + 1
    tracker.last_completed_at = datetime.now(UTC)


@router.post("/api/sync", response_model=SyncResponse)
async def sync_data(data: SyncRequest, session: AsyncSession = Depends(get_session)):
    synced = 0

    for workout_data in data.workouts:
        workout = WorkoutSession(
            user_id=data.user_id,
            plan_day_id=workout_data.plan_day_id,
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

        await _advance_cycle_for_synced_workout(data, workout_data, session)
        synced += 1

    await session.commit()
    return SyncResponse(workouts_synced=synced)
