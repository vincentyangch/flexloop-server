from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.db.engine import get_session
from flexloop.models.exercise import Exercise
from flexloop.services.warmup import generate_warmup_sets

router = APIRouter(prefix="/api/warmup", tags=["warmup"])


@router.get("/{exercise_id}")
async def get_warmup_sets(
    exercise_id: int,
    working_weight: float,
    session: AsyncSession = Depends(get_session),
):
    """Get suggested warm-up sets for an exercise at a given working weight."""
    result = await session.execute(select(Exercise).where(Exercise.id == exercise_id))
    exercise = result.scalar_one_or_none()
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")

    sets = generate_warmup_sets(
        working_weight=working_weight,
        exercise_category=exercise.category,
        equipment=exercise.equipment,
    )

    return {
        "exercise_id": exercise_id,
        "exercise_name": exercise.name,
        "working_weight": working_weight,
        "category": exercise.category,
        "warmup_sets": sets,
    }
