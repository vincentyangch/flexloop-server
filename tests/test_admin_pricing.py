"""Unit tests for flexloop.admin.pricing."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.pricing import (
    PRICING,
    ModelPricingValues,
    compute_cost,
    get_model_pricing,
)
from flexloop.models.model_pricing import ModelPricing


class TestStaticPricingDict:
    def test_contains_common_openai_models(self) -> None:
        assert "gpt-4o-mini" in PRICING
        assert "gpt-4o" in PRICING

    def test_contains_common_anthropic_models(self) -> None:
        assert any(k.startswith("claude-3-5-sonnet") for k in PRICING)
        assert any(k.startswith("claude-3-5-haiku") for k in PRICING)

    def test_all_entries_have_input_and_output(self) -> None:
        for model_name, values in PRICING.items():
            assert "input" in values, f"{model_name} missing 'input'"
            assert "output" in values, f"{model_name} missing 'output'"
            assert values["input"] >= 0
            assert values["output"] >= 0


class TestComputeCost:
    def test_simple_cost(self) -> None:
        pricing = ModelPricingValues(
            input_per_million=1.0,
            output_per_million=2.0,
            cache_read_per_million=None,
            cache_write_per_million=None,
        )
        cost = compute_cost(
            pricing,
            input_tokens=500_000,
            output_tokens=250_000,
            cache_read_tokens=0,
            cache_write_tokens=0,
        )
        assert cost == pytest.approx(1.00, abs=1e-9)

    def test_cache_tokens_priced_when_available(self) -> None:
        pricing = ModelPricingValues(
            input_per_million=3.0,
            output_per_million=15.0,
            cache_read_per_million=0.30,
            cache_write_per_million=3.75,
        )
        cost = compute_cost(
            pricing,
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            cache_read_tokens=1_000_000,
            cache_write_tokens=1_000_000,
        )
        assert cost == pytest.approx(22.05, abs=1e-9)

    def test_cache_tokens_ignored_when_pricing_missing(self) -> None:
        pricing = ModelPricingValues(
            input_per_million=1.0,
            output_per_million=2.0,
            cache_read_per_million=None,
            cache_write_per_million=None,
        )
        cost = compute_cost(
            pricing,
            input_tokens=1_000_000,
            output_tokens=0,
            cache_read_tokens=1_000_000,
            cache_write_tokens=1_000_000,
        )
        assert cost == pytest.approx(1.00, abs=1e-9)

    def test_none_pricing_returns_none(self) -> None:
        assert compute_cost(None, 1_000_000, 1_000_000, 0, 0) is None

    def test_zero_tokens_returns_zero(self) -> None:
        pricing = ModelPricingValues(
            input_per_million=1.0,
            output_per_million=2.0,
            cache_read_per_million=None,
            cache_write_per_million=None,
        )
        assert compute_cost(pricing, 0, 0, 0, 0) == 0.0


class TestGetModelPricing:
    async def test_returns_none_when_unknown(self, db_session: AsyncSession) -> None:
        result = await get_model_pricing(db_session, "definitely-not-a-real-model")
        assert result is None

    async def test_returns_static_entry_when_no_db_row(
        self,
        db_session: AsyncSession,
    ) -> None:
        result = await get_model_pricing(db_session, "gpt-4o-mini")
        assert result is not None
        assert result.input_per_million == PRICING["gpt-4o-mini"]["input"]
        assert result.output_per_million == PRICING["gpt-4o-mini"]["output"]
        assert result.cache_read_per_million is None
        assert result.cache_write_per_million is None

    async def test_db_row_overrides_static(
        self,
        db_session: AsyncSession,
    ) -> None:
        db_session.add(
            ModelPricing(
                model_name="gpt-4o-mini",
                input_per_million=99.99,
                output_per_million=199.99,
                cache_read_per_million=9.99,
                cache_write_per_million=19.99,
            )
        )
        await db_session.commit()

        result = await get_model_pricing(db_session, "gpt-4o-mini")
        assert result is not None
        assert result.input_per_million == 99.99
        assert result.output_per_million == 199.99
        assert result.cache_read_per_million == 9.99
        assert result.cache_write_per_million == 19.99

    async def test_db_row_for_unknown_model(
        self,
        db_session: AsyncSession,
    ) -> None:
        db_session.add(
            ModelPricing(
                model_name="custom-proxy-model",
                input_per_million=0.50,
                output_per_million=1.00,
                cache_read_per_million=None,
                cache_write_per_million=None,
            )
        )
        await db_session.commit()

        result = await get_model_pricing(db_session, "custom-proxy-model")
        assert result is not None
        assert result.input_per_million == 0.50
        assert result.output_per_million == 1.00
