from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.db.engine import get_session
from flexloop.models.personal_record import PersonalRecord

router = APIRouter(tags=["personal-records"])


@router.get("/api/users/{user_id}/prs")
async def get_user_prs(
    user_id: int,
    exercise_id: int | None = None,
    pr_type: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    query = select(PersonalRecord).where(PersonalRecord.user_id == user_id)

    if exercise_id:
        query = query.where(PersonalRecord.exercise_id == exercise_id)
    if pr_type:
        query = query.where(PersonalRecord.pr_type == pr_type)

    query = query.order_by(PersonalRecord.achieved_at.desc())
    result = await session.execute(query)
    prs = result.scalars().all()

    return [
        {
            "id": pr.id,
            "exercise_id": pr.exercise_id,
            "pr_type": pr.pr_type,
            "value": pr.value,
            "session_id": pr.session_id,
            "achieved_at": pr.achieved_at.isoformat() if pr.achieved_at else None,
        }
        for pr in prs
    ]


@router.get("/api/exercises/{exercise_id}/prs")
async def get_exercise_prs(
    exercise_id: int,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(PersonalRecord)
        .where(PersonalRecord.exercise_id == exercise_id)
        .order_by(PersonalRecord.pr_type)
    )
    prs = result.scalars().all()

    return [
        {
            "id": pr.id,
            "user_id": pr.user_id,
            "pr_type": pr.pr_type,
            "value": pr.value,
            "achieved_at": pr.achieved_at.isoformat() if pr.achieved_at else None,
        }
        for pr in prs
    ]
