from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from flexloop.db.engine import get_session
from flexloop.models.workout import SessionFeedback, WorkoutSession, WorkoutSet
from flexloop.services.pr_detection import check_prs
from flexloop.schemas.workout import (
    SessionFeedbackCreate,
    SessionFeedbackResponse,
    WorkoutSessionCreate,
    WorkoutSessionResponse,
    WorkoutSessionUpdate,
    WorkoutSetUpdate,
)

router = APIRouter(tags=["workouts"])


@router.post("/api/workouts", response_model=WorkoutSessionResponse, status_code=201)
async def create_workout(
    data: WorkoutSessionCreate, session: AsyncSession = Depends(get_session)
):
    workout = WorkoutSession(
        user_id=data.user_id,
        plan_day_id=data.plan_day_id,
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


@router.put("/api/workouts/{workout_id}/sets/{set_id}", response_model=dict)
async def update_set(
    workout_id: int, set_id: int, data: WorkoutSetUpdate,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(WorkoutSet).where(WorkoutSet.id == set_id, WorkoutSet.session_id == workout_id)
    )
    workout_set = result.scalar_one_or_none()
    if not workout_set:
        raise HTTPException(status_code=404, detail="Set not found")

    if data.weight is not None:
        workout_set.weight = data.weight
    if data.reps is not None:
        workout_set.reps = data.reps
    if data.rpe is not None:
        workout_set.rpe = data.rpe

    await session.commit()
    return {
        "id": workout_set.id,
        "weight": workout_set.weight,
        "reps": workout_set.reps,
        "rpe": workout_set.rpe,
    }


class PRCheckRequest(BaseModel):
    exercise_id: int
    weight: float | None = None
    reps: int | None = None


@router.post("/api/workouts/{workout_id}/check-pr")
async def check_set_pr(
    workout_id: int,
    data: PRCheckRequest,
    session: AsyncSession = Depends(get_session),
):
    """Check if a set represents a new personal record. Call after logging each set."""
    result = await session.execute(
        select(WorkoutSession).where(WorkoutSession.id == workout_id)
    )
    workout = result.scalar_one_or_none()
    if not workout:
        raise HTTPException(status_code=404, detail="Workout session not found")

    new_prs = await check_prs(
        user_id=workout.user_id,
        exercise_id=data.exercise_id,
        weight=data.weight,
        reps=data.reps,
        session_id=workout_id,
        db=session,
    )

    await session.commit()
    return {"new_prs": new_prs}


class PRCheckRequestWithUser(BaseModel):
    user_id: int
    exercise_id: int
    weight: float | None = None
    reps: int | None = None


@router.post("/api/check-pr")
async def check_pr_for_user(
    data: PRCheckRequestWithUser,
    session: AsyncSession = Depends(get_session),
):
    """Check if a set represents a new PR. Accepts user_id in body instead of requiring a workout session."""
    new_prs = await check_prs(
        user_id=data.user_id,
        exercise_id=data.exercise_id,
        weight=data.weight,
        reps=data.reps,
        session_id=None,
        db=session,
    )

    await session.commit()
    return {"new_prs": new_prs}
