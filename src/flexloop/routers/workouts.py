from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from flexloop.db.engine import get_session
from flexloop.models.workout import SessionFeedback, WorkoutSession, WorkoutSet
from flexloop.schemas.workout import (
    SessionFeedbackCreate,
    SessionFeedbackResponse,
    WorkoutSessionCreate,
    WorkoutSessionResponse,
    WorkoutSessionUpdate,
)

router = APIRouter(tags=["workouts"])


@router.post("/api/workouts", response_model=WorkoutSessionResponse, status_code=201)
async def create_workout(
    data: WorkoutSessionCreate, session: AsyncSession = Depends(get_session)
):
    workout = WorkoutSession(
        user_id=data.user_id,
        plan_day_id=data.plan_day_id,
        template_id=data.template_id,
        source=data.source,
        started_at=datetime.now(),
        notes=data.notes,
    )
    session.add(workout)
    await session.commit()

    result = await session.execute(
        select(WorkoutSession)
        .where(WorkoutSession.id == workout.id)
        .options(selectinload(WorkoutSession.sets), selectinload(WorkoutSession.feedback))
    )
    return result.scalar_one()


@router.put("/api/workouts/{workout_id}", response_model=WorkoutSessionResponse)
async def update_workout(
    workout_id: int, data: WorkoutSessionUpdate, session: AsyncSession = Depends(get_session)
):
    result = await session.execute(
        select(WorkoutSession)
        .where(WorkoutSession.id == workout_id)
        .options(selectinload(WorkoutSession.sets), selectinload(WorkoutSession.feedback))
    )
    workout = result.scalar_one_or_none()
    if not workout:
        raise HTTPException(status_code=404, detail="Workout session not found")

    if data.completed_at is not None:
        workout.completed_at = data.completed_at
    if data.notes is not None:
        workout.notes = data.notes
    if data.sets is not None:
        for set_data in data.sets:
            workout_set = WorkoutSet(session_id=workout.id, **set_data.model_dump())
            session.add(workout_set)

    await session.commit()
    session.expire_all()

    result = await session.execute(
        select(WorkoutSession)
        .where(WorkoutSession.id == workout_id)
        .options(selectinload(WorkoutSession.sets), selectinload(WorkoutSession.feedback))
    )
    return result.scalar_one()


@router.get("/api/workouts/{workout_id}", response_model=WorkoutSessionResponse)
async def get_workout(workout_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(WorkoutSession)
        .where(WorkoutSession.id == workout_id)
        .options(selectinload(WorkoutSession.sets), selectinload(WorkoutSession.feedback))
    )
    workout = result.scalar_one_or_none()
    if not workout:
        raise HTTPException(status_code=404, detail="Workout session not found")
    return workout


@router.get("/api/users/{user_id}/workouts", response_model=list[WorkoutSessionResponse])
async def list_user_workouts(user_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(WorkoutSession)
        .where(WorkoutSession.user_id == user_id)
        .options(selectinload(WorkoutSession.sets), selectinload(WorkoutSession.feedback))
        .order_by(WorkoutSession.started_at.desc())
    )
    return result.scalars().all()


@router.post(
    "/api/workouts/{workout_id}/feedback",
    response_model=SessionFeedbackResponse,
    status_code=201,
)
async def submit_feedback(
    workout_id: int, data: SessionFeedbackCreate, session: AsyncSession = Depends(get_session)
):
    result = await session.execute(
        select(WorkoutSession).where(WorkoutSession.id == workout_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Workout session not found")

    feedback = SessionFeedback(session_id=workout_id, **data.model_dump(exclude_unset=True))
    session.add(feedback)
    await session.commit()
    await session.refresh(feedback)
    return feedback
