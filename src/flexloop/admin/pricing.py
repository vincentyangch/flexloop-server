"""Model pricing and cost computation.

The dashboard answers "how much did this month cost" by combining
per-user-per-month token totals from ``ai_usage`` with a pricing lookup:
1. ``model_pricing`` DB table (admin-managed custom overrides)
2. Static ``PRICING`` dict below (common built-in models)
3. ``None`` (unknown model - UI shows "—")

All prices are USD per million tokens. The numbers in ``PRICING`` are
rounded to the nearest published tier as of 2026-04; admins who need
different values can override via the admin UI.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.models.model_pricing import ModelPricing


PRICING: dict[str, dict[str, float]] = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
    "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.00},
    "claude-3-opus-20240229": {"input": 15.00, "output": 75.00},
    "deepseek-chat": {"input": 0.27, "output": 1.10},
}


@dataclass
class ModelPricingValues:
    input_per_million: float
    output_per_million: float
    cache_read_per_million: float | None
    cache_write_per_million: float | None


async def get_model_pricing(
    db: AsyncSession,
    model_name: str,
) -> ModelPricingValues | None:
    result = await db.execute(
        select(ModelPricing).where(ModelPricing.model_name == model_name)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        return ModelPricingValues(
            input_per_million=row.input_per_million,
            output_per_million=row.output_per_million,
            cache_read_per_million=row.cache_read_per_million,
            cache_write_per_million=row.cache_write_per_million,
        )

    static_entry = PRICING.get(model_name)
    if static_entry is None:
        return None

    return ModelPricingValues(
        input_per_million=static_entry["input"],
        output_per_million=static_entry["output"],
        cache_read_per_million=None,
        cache_write_per_million=None,
    )


def compute_cost(
    pricing: ModelPricingValues | None,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float | None:
    if pricing is None:
        return None

    cost = (
        (input_tokens / 1_000_000) * pricing.input_per_million
        + (output_tokens / 1_000_000) * pricing.output_per_million
    )
    if pricing.cache_read_per_million is not None:
        cost += (cache_read_tokens / 1_000_000) * pricing.cache_read_per_million
    if pricing.cache_write_per_million is not None:
        cost += (cache_write_tokens / 1_000_000) * pricing.cache_write_per_million
    return cost
