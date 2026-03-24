from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.models.personal_record import PersonalRecord
from flexloop.models.workout import WorkoutSet


def estimate_1rm(weight: float, reps: int) -> float:
    """Estimate 1RM using the Epley formula."""
    if reps == 1:
        return weight
    if reps <= 0 or weight <= 0:
        return 0.0
    return weight * (1 + reps / 30)


async def check_prs(
    user_id: int,
    exercise_id: int,
    weight: float | None,
    reps: int | None,
    session_id: int,
    db: AsyncSession,
) -> list[dict]:
    """Check if a set represents any new personal records. Returns list of new PRs."""
    new_prs = []

    if not weight or not reps or weight <= 0 or reps <= 0:
        return new_prs

    # Check estimated 1RM PR
    estimated_1rm = estimate_1rm(weight, reps)
    result = await db.execute(
        select(PersonalRecord).where(
            PersonalRecord.user_id == user_id,
            PersonalRecord.exercise_id == exercise_id,
            PersonalRecord.pr_type == "estimated_1rm",
        )
    )
    current_1rm_pr = result.scalar_one_or_none()

    if not current_1rm_pr or estimated_1rm > current_1rm_pr.value:
        if current_1rm_pr:
            old_value = current_1rm_pr.value
            current_1rm_pr.value = estimated_1rm
            current_1rm_pr.session_id = session_id
            current_1rm_pr.achieved_at = datetime.now()
        else:
            old_value = 0.0
            pr = PersonalRecord(
                user_id=user_id,
                exercise_id=exercise_id,
                pr_type="estimated_1rm",
                value=estimated_1rm,
                session_id=session_id,
                achieved_at=datetime.now(),
            )
            db.add(pr)

        new_prs.append({
            "type": "estimated_1rm",
            "value": round(estimated_1rm, 1),
            "previous": round(old_value, 1),
            "detail": f"{weight}kg x {reps} reps",
        })

    # Check rep PR at this weight
    result = await db.execute(
        select(PersonalRecord).where(
            PersonalRecord.user_id == user_id,
            PersonalRecord.exercise_id == exercise_id,
            PersonalRecord.pr_type == "rep_at_weight",
        )
    )
    current_rep_pr = result.scalar_one_or_none()

    # Only track rep PR if it's a meaningful weight (working sets)
    if current_rep_pr:
        # PR only if strictly more reps
        if reps > current_rep_pr.value:
            old_reps = current_rep_pr.value
            current_rep_pr.value = reps
            current_rep_pr.session_id = session_id
            current_rep_pr.achieved_at = datetime.now()

            new_prs.append({
                "type": "rep_at_weight",
                "value": reps,
                "previous": int(old_reps),
                "detail": f"{reps} reps at {weight}kg",
            })
    else:
        pr = PersonalRecord(
            user_id=user_id,
            exercise_id=exercise_id,
            pr_type="rep_at_weight",
            value=reps,
            session_id=session_id,
            achieved_at=datetime.now(),
        )
        db.add(pr)
        # Don't alert on first-ever set — it's always a "PR" trivially

    # Check volume PR (weight x reps for a single set)
    volume = weight * reps
    result = await db.execute(
        select(PersonalRecord).where(
            PersonalRecord.user_id == user_id,
            PersonalRecord.exercise_id == exercise_id,
            PersonalRecord.pr_type == "volume",
        )
    )
    current_volume_pr = result.scalar_one_or_none()

    if current_volume_pr:
        if volume > current_volume_pr.value:
            old_volume = current_volume_pr.value
            current_volume_pr.value = volume
            current_volume_pr.session_id = session_id
            current_volume_pr.achieved_at = datetime.now()

            new_prs.append({
                "type": "volume",
                "value": round(volume, 1),
                "previous": round(old_volume, 1),
                "detail": f"{weight}kg x {reps} = {round(volume, 1)}kg volume",
            })
    else:
        pr = PersonalRecord(
            user_id=user_id,
            exercise_id=exercise_id,
            pr_type="volume",
            value=volume,
            session_id=session_id,
            achieved_at=datetime.now(),
        )
        db.add(pr)

    return new_prs
