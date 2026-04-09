"""Admin AI usage dashboard endpoints."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import require_admin
from flexloop.admin.pricing import ModelPricingValues, compute_cost, get_model_pricing
from flexloop.config import settings
from flexloop.db.engine import get_session
from flexloop.models.admin_user import AdminUser
from flexloop.models.ai import AIUsage

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
