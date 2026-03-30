from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.db.engine import get_session
from flexloop.models.user import User
from flexloop.services.deload import detect_fatigue

router = APIRouter(prefix="/api/deload", tags=["deload"])


@router.get("/{user_id}/check")
async def check_deload(
    user_id: int,
    lookback_days: int = 14,
    session: AsyncSession = Depends(get_session),
):
    """Check if a deload is recommended based on recent training data."""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    report = await detect_fatigue(user_id, session, lookback_days, weight_unit=user.weight_unit)
    return report
