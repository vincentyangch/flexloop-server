from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.db.engine import get_session
from flexloop.models.exercise import Exercise
from flexloop.models.workout import WorkoutSession, WorkoutSet

router = APIRouter(prefix="/api/progress", tags=["progress"])


@router.get("/{user_id}/estimated-1rm")
async def get_estimated_1rm_progression(
    user_id: int,
    exercise_id: int | None = None,
    days: int = 90,
    session: AsyncSession = Depends(get_session),
):
    """Get estimated 1RM progression over time for one or all exercises."""
    cutoff = date.today() - timedelta(days=days)

    query = (
        select(
            WorkoutSet.exercise_id,
            Exercise.name,
            WorkoutSession.started_at,
            WorkoutSet.weight,
            WorkoutSet.reps,
        )
        .join(WorkoutSession, WorkoutSet.session_id == WorkoutSession.id)
        .join(Exercise, WorkoutSet.exercise_id == Exercise.id)
        .where(
            WorkoutSession.user_id == user_id,
            WorkoutSession.started_at >= cutoff,
            WorkoutSet.weight > 0,
            WorkoutSet.reps > 0,
            WorkoutSet.set_type == "working",
        )
    )

    if exercise_id:
        query = query.where(WorkoutSet.exercise_id == exercise_id)

    query = query.order_by(WorkoutSession.started_at)
    result = await session.execute(query)
    rows = result.all()

    # Group by exercise and calculate estimated 1RM per session
    data: dict[int, dict] = {}
    for ex_id, ex_name, started_at, weight, reps in rows:
        if ex_id not in data:
            data[ex_id] = {"exercise_id": ex_id, "exercise_name": ex_name, "points": []}

        e1rm = weight * (1 + reps / 30)  # Epley formula
        session_date = started_at.strftime("%Y-%m-%d") if started_at else ""

        # Keep the best 1RM per session date
        points = data[ex_id]["points"]
        existing = next((p for p in points if p["date"] == session_date), None)
        if existing:
            if e1rm > existing["value"]:
                existing["value"] = round(e1rm, 1)
        else:
            points.append({"date": session_date, "value": round(e1rm, 1)})

    return list(data.values())


@router.get("/{user_id}/volume")
async def get_volume_by_muscle_group(
    user_id: int,
    days: int = 7,
    session: AsyncSession = Depends(get_session),
):
    """Get weekly volume (total sets) per muscle group."""
    cutoff = date.today() - timedelta(days=days)

    query = (
        select(
            Exercise.muscle_group,
            func.count(WorkoutSet.id).label("total_sets"),
        )
        .join(WorkoutSession, WorkoutSet.session_id == WorkoutSession.id)
        .join(Exercise, WorkoutSet.exercise_id == Exercise.id)
        .where(
            WorkoutSession.user_id == user_id,
            WorkoutSession.started_at >= cutoff,
            WorkoutSet.set_type == "working",
        )
        .group_by(Exercise.muscle_group)
        .order_by(func.count(WorkoutSet.id).desc())
    )

    result = await session.execute(query)
    rows = result.all()

    return [
        {"muscle_group": mg, "total_sets": ts}
        for mg, ts in rows
    ]


@router.get("/{user_id}/bodyweight")
async def get_bodyweight_trend(
    user_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Get bodyweight trend from measurements."""
    from flexloop.models.measurement import Measurement

    result = await session.execute(
        select(Measurement)
        .where(Measurement.user_id == user_id, Measurement.type == "bodyweight")
        .order_by(Measurement.date)
    )
    measurements = result.scalars().all()

    return [
        {"date": m.date.isoformat(), "value": m.value}
        for m in measurements
    ]
