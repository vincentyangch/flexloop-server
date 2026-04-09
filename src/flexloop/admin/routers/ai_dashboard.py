"""Admin AI usage dashboard endpoints."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import require_admin
from flexloop.admin.pricing import (
    PRICING,
    ModelPricingValues,
    compute_cost,
    get_model_pricing,
)
from flexloop.config import settings
from flexloop.db.engine import get_session
from flexloop.models.admin_user import AdminUser
from flexloop.models.ai import AIUsage
from flexloop.models.model_pricing import ModelPricing

router = APIRouter(prefix="/api/admin/ai", tags=["admin:ai-dashboard"])


class UsageCard(BaseModel):
    month: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    call_count: int
    estimated_cost: float | None


class ChartPoint(BaseModel):
    month: str
    input_tokens: int
    output_tokens: int
    estimated_cost: float | None


class UsageRow(BaseModel):
    id: int
    month: str
    user_id: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    call_count: int
    estimated_cost: float | None


class StatsResponse(BaseModel):
    current_month: UsageCard
    last_12_months: list[ChartPoint]
    rows: list[UsageRow]
    assumed_model: str


class PricingDbEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    model_name: str
    input_per_million: float
    output_per_million: float
    cache_read_per_million: float | None
    cache_write_per_million: float | None


class PricingStaticEntry(BaseModel):
    model_name: str
    input_per_million: float
    output_per_million: float


class PricingListResponse(BaseModel):
    db_entries: list[PricingDbEntry]
    static_entries: list[PricingStaticEntry]


class PricingUpsert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_per_million: float = Field(..., ge=0)
    output_per_million: float = Field(..., ge=0)
    cache_read_per_million: float | None = Field(None, ge=0)
    cache_write_per_million: float | None = Field(None, ge=0)


def _current_month_str() -> str:
    return date.today().strftime("%Y-%m")


def _months_back(count: int) -> list[str]:
    today = date.today().replace(day=1)
    year = today.year
    month = today.month
    months: list[str] = []
    for _ in range(count):
        months.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return list(reversed(months))


def _row_to_model(row: AIUsage, pricing: ModelPricingValues | None) -> UsageRow:
    return UsageRow(
        id=row.id,
        month=row.month,
        user_id=row.user_id,
        input_tokens=row.total_input_tokens,
        output_tokens=row.total_output_tokens,
        cache_read_tokens=row.total_cache_read_tokens,
        cache_write_tokens=row.total_cache_creation_tokens,
        call_count=row.call_count,
        estimated_cost=compute_cost(
            pricing,
            row.total_input_tokens,
            row.total_output_tokens,
            row.total_cache_read_tokens,
            row.total_cache_creation_tokens,
        ),
    )


_ROW_CAP = 1000


@router.get("/usage/stats", response_model=StatsResponse)
async def get_usage_stats(
    month_from: str | None = Query(None, description="YYYY-MM inclusive lower bound"),
    month_to: str | None = Query(None, description="YYYY-MM inclusive upper bound"),
    user_id: int | None = Query(None),
    db: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(require_admin),
) -> StatsResponse:
    pricing = await get_model_pricing(db, settings.ai_model)
    current_month = _current_month_str()

    current_month_query = select(
        func.coalesce(func.sum(AIUsage.total_input_tokens), 0),
        func.coalesce(func.sum(AIUsage.total_output_tokens), 0),
        func.coalesce(func.sum(AIUsage.total_cache_read_tokens), 0),
        func.coalesce(func.sum(AIUsage.total_cache_creation_tokens), 0),
        func.coalesce(func.sum(AIUsage.call_count), 0),
    ).where(AIUsage.month == current_month)
    current_month_result = await db.execute(current_month_query)
    (
        input_tokens,
        output_tokens,
        cache_read_tokens,
        cache_write_tokens,
        call_count,
    ) = current_month_result.one()
    current_card = UsageCard(
        month=current_month,
        input_tokens=int(input_tokens),
        output_tokens=int(output_tokens),
        cache_read_tokens=int(cache_read_tokens),
        cache_write_tokens=int(cache_write_tokens),
        call_count=int(call_count),
        estimated_cost=compute_cost(
            pricing,
            int(input_tokens),
            int(output_tokens),
            int(cache_read_tokens),
            int(cache_write_tokens),
        ),
    )

    last_12_months = _months_back(12)
    chart_query = (
        select(
            AIUsage.month,
            func.coalesce(func.sum(AIUsage.total_input_tokens), 0),
            func.coalesce(func.sum(AIUsage.total_output_tokens), 0),
            func.coalesce(func.sum(AIUsage.total_cache_read_tokens), 0),
            func.coalesce(func.sum(AIUsage.total_cache_creation_tokens), 0),
        )
        .where(AIUsage.month.in_(last_12_months))
        .group_by(AIUsage.month)
    )
    chart_result = await db.execute(chart_query)
    chart_by_month: dict[str, tuple[int, int, int, int]] = {
        month: (
            int(input_total),
            int(output_total),
            int(cache_read_total),
            int(cache_write_total),
        )
        for month, input_total, output_total, cache_read_total, cache_write_total in chart_result.all()
    }

    chart_points: list[ChartPoint] = []
    for month in last_12_months:
        input_total, output_total, cache_read_total, cache_write_total = chart_by_month.get(
            month,
            (0, 0, 0, 0),
        )
        chart_points.append(
            ChartPoint(
                month=month,
                input_tokens=input_total,
                output_tokens=output_total,
                estimated_cost=compute_cost(
                    pricing,
                    input_total,
                    output_total,
                    cache_read_total,
                    cache_write_total,
                ),
            )
        )

    rows_query = select(AIUsage)
    if user_id is not None:
        rows_query = rows_query.where(AIUsage.user_id == user_id)
    if month_from is not None:
        rows_query = rows_query.where(AIUsage.month >= month_from)
    if month_to is not None:
        rows_query = rows_query.where(AIUsage.month <= month_to)
    rows_query = rows_query.order_by(AIUsage.month.desc(), AIUsage.user_id).limit(_ROW_CAP)
    rows_result = await db.execute(rows_query)
    rows = [_row_to_model(row, pricing) for row in rows_result.scalars().all()]

    return StatsResponse(
        current_month=current_card,
        last_12_months=chart_points,
        rows=rows,
        assumed_model=settings.ai_model,
    )


@router.get("/pricing", response_model=PricingListResponse)
async def list_pricing(
    db: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(require_admin),
) -> PricingListResponse:
    rows = (await db.execute(select(ModelPricing))).scalars().all()
    db_entries = [
        PricingDbEntry(
            model_name=row.model_name,
            input_per_million=row.input_per_million,
            output_per_million=row.output_per_million,
            cache_read_per_million=row.cache_read_per_million,
            cache_write_per_million=row.cache_write_per_million,
        )
        for row in rows
    ]
    static_entries = [
        PricingStaticEntry(
            model_name=model_name,
            input_per_million=values["input"],
            output_per_million=values["output"],
        )
        for model_name, values in sorted(PRICING.items())
    ]
    return PricingListResponse(
        db_entries=db_entries,
        static_entries=static_entries,
    )


@router.put("/pricing/{model_name}", response_model=PricingDbEntry)
async def upsert_pricing(
    model_name: str,
    payload: PricingUpsert,
    db: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(require_admin),
) -> PricingDbEntry:
    if not model_name or any(char in model_name for char in "/\\"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid model_name",
        )

    existing = (
        await db.execute(
            select(ModelPricing).where(ModelPricing.model_name == model_name)
        )
    ).scalar_one_or_none()

    if existing is None:
        row = ModelPricing(
            model_name=model_name,
            input_per_million=payload.input_per_million,
            output_per_million=payload.output_per_million,
            cache_read_per_million=payload.cache_read_per_million,
            cache_write_per_million=payload.cache_write_per_million,
        )
        db.add(row)
    else:
        existing.input_per_million = payload.input_per_million
        existing.output_per_million = payload.output_per_million
        existing.cache_read_per_million = payload.cache_read_per_million
        existing.cache_write_per_million = payload.cache_write_per_million
        row = existing

    await db.commit()
    await db.refresh(row)
    return PricingDbEntry(
        model_name=row.model_name,
        input_per_million=row.input_per_million,
        output_per_million=row.output_per_million,
        cache_read_per_million=row.cache_read_per_million,
        cache_write_per_million=row.cache_write_per_million,
    )


@router.delete("/pricing/{model_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pricing(
    model_name: str,
    db: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(require_admin),
) -> None:
    existing = (
        await db.execute(
            select(ModelPricing).where(ModelPricing.model_name == model_name)
        )
    ).scalar_one_or_none()
    if existing is None:
        return None

    await db.delete(existing)
    await db.commit()
