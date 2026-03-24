from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.db.engine import get_session
from flexloop.services.export import export_session, export_user_data

router = APIRouter(prefix="/api/export", tags=["data"])


@router.get("")
async def export_data(
    user_id: int, format: str = "json", session: AsyncSession = Depends(get_session)
):
    data = await export_user_data(user_id, session)
    return data


@router.get("/session/{session_id}")
async def export_single_session(
    session_id: int, session: AsyncSession = Depends(get_session)
):
    data = await export_session(session_id, session)
    if not data:
        raise HTTPException(status_code=404, detail="Session not found")
    return data
