from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.db.engine import get_session
from flexloop.models.ai import AIUsage
from flexloop.schemas.ai import AIUsageResponse

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/usage", response_model=list[AIUsageResponse])
async def get_ai_usage(user_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(AIUsage).where(AIUsage.user_id == user_id).order_by(AIUsage.month.desc())
    )
    return result.scalars().all()
