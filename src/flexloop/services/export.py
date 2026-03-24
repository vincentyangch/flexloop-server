from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from flexloop.models.measurement import Measurement
from flexloop.models.template import Template
from flexloop.models.user import User
from flexloop.models.workout import WorkoutSession


async def export_user_data(user_id: int, session: AsyncSession) -> dict:
    user_result = await session.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one()

    workouts_result = await session.execute(
        select(WorkoutSession)
        .where(WorkoutSession.user_id == user_id)
        .options(
            selectinload(WorkoutSession.sets),
            selectinload(WorkoutSession.feedback),
        )
        .order_by(WorkoutSession.started_at)
    )
    workouts = workouts_result.scalars().all()

    templates_result = await session.execute(
        select(Template).where(Template.user_id == user_id)
    )
    templates = templates_result.scalars().all()

    measurements_result = await session.execute(
        select(Measurement).where(Measurement.user_id == user_id).order_by(Measurement.date)
    )
    measurements = measurements_result.scalars().all()

    return {
        "user": {
            "name": user.name, "gender": user.gender, "age": user.age,
            "height_cm": user.height_cm, "weight_kg": user.weight_kg,
            "experience_level": user.experience_level, "goals": user.goals,
            "available_equipment": user.available_equipment,
        },
        "workouts": [
            {
                "id": w.id, "source": w.source,
                "started_at": w.started_at.isoformat() if w.started_at else None,
                "completed_at": w.completed_at.isoformat() if w.completed_at else None,
                "notes": w.notes,
                "sets": [
                    {
                        "exercise_id": s.exercise_id, "set_number": s.set_number,
                        "set_type": s.set_type, "weight": s.weight, "reps": s.reps,
                        "rpe": s.rpe, "duration_sec": s.duration_sec,
                        "distance_m": s.distance_m, "rest_sec": s.rest_sec,
                    }
                    for s in w.sets
                ],
            }
            for w in workouts
        ],
        "templates": [
            {"name": t.name, "exercises_json": t.exercises_json}
            for t in templates
        ],
        "measurements": [
            {
                "date": m.date.isoformat(), "type": m.type,
                "value_cm": m.value_cm, "notes": m.notes,
            }
            for m in measurements
        ],
    }


async def export_session(session_id: int, session: AsyncSession) -> dict | None:
    result = await session.execute(
        select(WorkoutSession)
        .where(WorkoutSession.id == session_id)
        .options(
            selectinload(WorkoutSession.sets),
            selectinload(WorkoutSession.feedback),
        )
    )
    workout = result.scalar_one_or_none()
    if not workout:
        return None

    return {
        "id": workout.id, "source": workout.source,
        "started_at": workout.started_at.isoformat() if workout.started_at else None,
        "completed_at": workout.completed_at.isoformat() if workout.completed_at else None,
        "notes": workout.notes,
        "sets": [
            {
                "exercise_id": s.exercise_id, "set_number": s.set_number,
                "set_type": s.set_type, "weight": s.weight, "reps": s.reps,
                "rpe": s.rpe, "duration_sec": s.duration_sec,
                "distance_m": s.distance_m, "rest_sec": s.rest_sec,
            }
            for s in workout.sets
        ],
    }
