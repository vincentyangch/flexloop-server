from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from flexloop.db.engine import get_session
from flexloop.models.cycle_tracker import CycleTracker
from flexloop.models.plan import ExerciseGroup, Plan, PlanDay, PlanExercise

router = APIRouter(prefix="/api/users", tags=["cycle"])


@router.get("/{user_id}/next-workout")
async def get_next_workout(user_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(CycleTracker).where(CycleTracker.user_id == user_id)
    )
    tracker = result.scalar_one_or_none()
    if not tracker:
        raise HTTPException(status_code=404, detail="No cycle tracker found. Generate or activate a plan first.")

    # Load the plan day matching next_day_number
    day_result = await session.execute(
        select(PlanDay)
        .where(PlanDay.plan_id == tracker.plan_id, PlanDay.day_number == tracker.next_day_number)
        .options(
            selectinload(PlanDay.exercise_groups)
            .selectinload(ExerciseGroup.exercises)
        )
    )
    plan_day = day_result.scalar_one_or_none()
    if not plan_day:
        raise HTTPException(status_code=404, detail="Plan day not found for current cycle position.")

    # Load plan name
    plan_result = await session.execute(select(Plan).where(Plan.id == tracker.plan_id))
    plan = plan_result.scalar_one()

    return {
        "plan_id": tracker.plan_id,
        "plan_name": plan.name,
        "cycle_length": plan.cycle_length,
        "next_day_number": tracker.next_day_number,
        "last_completed_at": tracker.last_completed_at.isoformat() if tracker.last_completed_at else None,
        "day": {
            "id": plan_day.id,
            "day_number": plan_day.day_number,
            "label": plan_day.label,
            "focus": plan_day.focus,
            "exercise_groups": [
                {
                    "id": g.id,
                    "group_type": g.group_type,
                    "order": g.order,
                    "rest_after_group_sec": g.rest_after_group_sec,
                    "exercises": [
                        {
                            "id": e.id,
                            "exercise_id": e.exercise_id,
                            "order": e.order,
                            "sets": e.sets,
                            "reps": e.reps,
                            "weight": e.weight,
                            "rpe_target": e.rpe_target,
                            "sets_json": e.sets_json,
                            "notes": e.notes,
                        }
                        for e in sorted(g.exercises, key=lambda x: x.order)
                    ],
                }
                for g in sorted(plan_day.exercise_groups, key=lambda x: x.order)
            ],
        },
    }


@router.post("/{user_id}/complete-workout")
async def complete_workout(user_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(CycleTracker).where(CycleTracker.user_id == user_id)
    )
    tracker = result.scalar_one_or_none()
    if not tracker:
        raise HTTPException(status_code=404, detail="No cycle tracker found.")

    # Get cycle length from plan
    plan_result = await session.execute(select(Plan).where(Plan.id == tracker.plan_id))
    plan = plan_result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")

    # Advance to next day, wrapping around
    completed_day = tracker.next_day_number
    next_day = (tracker.next_day_number % plan.cycle_length) + 1
    tracker.next_day_number = next_day
    tracker.last_completed_at = datetime.now(UTC)

    await session.commit()

    return {
        "completed_day_number": completed_day,
        "next_day_number": tracker.next_day_number,
        "cycle_length": plan.cycle_length,
    }
