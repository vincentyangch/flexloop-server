from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.db.engine import get_session
from flexloop.models.exercise import Exercise
from flexloop.schemas.exercise import ExerciseListResponse, ExerciseResponse

router = APIRouter(prefix="/api/exercises", tags=["exercises"])


@router.get("", response_model=ExerciseListResponse)
async def list_exercises(
    muscle_group: str | None = None,
    equipment: str | None = None,
    category: str | None = None,
    difficulty: str | None = None,
    q: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    query = select(Exercise)

    if muscle_group:
        query = query.where(Exercise.muscle_group == muscle_group)
    if equipment:
        query = query.where(Exercise.equipment == equipment)
    if category:
        query = query.where(Exercise.category == category)
    if difficulty:
        query = query.where(Exercise.difficulty == difficulty)
    if q:
        query = query.where(Exercise.name.ilike(f"%{q}%"))

    result = await session.execute(query)
    exercises = result.scalars().all()
    return ExerciseListResponse(exercises=exercises, total=len(exercises))


@router.get("/{exercise_id}", response_model=ExerciseResponse)
async def get_exercise(exercise_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Exercise).where(Exercise.id == exercise_id))
    exercise = result.scalar_one_or_none()
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")
    return exercise
