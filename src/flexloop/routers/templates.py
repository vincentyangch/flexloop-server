from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.db.engine import get_session
from flexloop.models.template import Template
from flexloop.schemas.template import TemplateCreate, TemplateResponse, TemplateUpdate

router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.post("", response_model=TemplateResponse, status_code=201)
async def create_template(data: TemplateCreate, session: AsyncSession = Depends(get_session)):
    template = Template(**data.model_dump())
    session.add(template)
    await session.commit()
    await session.refresh(template)
    return template


@router.get("", response_model=list[TemplateResponse])
async def list_templates(user_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Template).where(Template.user_id == user_id).order_by(Template.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(template_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Template).where(Template.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


@router.put("/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: int, data: TemplateUpdate, session: AsyncSession = Depends(get_session)
):
    result = await session.execute(select(Template).where(Template.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(template, field, value)

    await session.commit()
    await session.refresh(template)
    return template


@router.delete("/{template_id}", status_code=204)
async def delete_template(template_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Template).where(Template.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    await session.delete(template)
    await session.commit()
    return Response(status_code=204)
