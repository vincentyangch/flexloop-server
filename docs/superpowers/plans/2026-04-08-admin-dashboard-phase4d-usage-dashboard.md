# Admin Dashboard — Phase 4d (AI Usage dashboard) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the basic phase-2 AI Usage CRUD page with a real dashboard — top stat cards for the current month's totals, a 12-month stacked bar chart of token usage, and a filterable per-user-per-month table with live cost estimates. Also ships the `flexloop.admin.pricing` module (static PRICING dict + DB overrides) and a small CRUD UI for managing custom model pricing, so the operator can answer "how much did this month cost" in one glance and add pricing for proxied/custom models when needed.

**Architecture:**
1. **Read-time cost computation.** The existing `ai_usage` table stores per-user-per-month token totals but does NOT track the model per row (that information is lost by aggregation). The dashboard assumes all logged usage was against the **currently configured** `settings.ai_model` and computes cost on the fly via a lookup chain: `model_pricing` DB row → static `PRICING` dict → `None`. When neither source has the model, the cost column shows `—` (the UI never pretends to know). This is an intentional approximation, documented in the stats endpoint's response and on the page.
2. **New backend module `flexloop.admin.pricing`.** Contains a static `PRICING` dict for common models (OpenAI gpt-4o*, Anthropic Claude 3.5, etc.) as USD per million tokens, plus `get_model_pricing(db, model_name)` and `compute_cost(pricing, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens)` helpers. No new DB schema — `model_pricing` table already exists from phase 1.
3. **New admin endpoints.** Stats endpoint (`GET /api/admin/ai/usage/stats`) returns the full dashboard payload in one shot: current-month card values, 12-month chart array, and a filtered/sorted table rows list. Three pricing-CRUD endpoints (`GET /api/admin/ai/pricing`, `PUT /api/admin/ai/pricing/{model_name}`, `DELETE /api/admin/ai/pricing/{model_name}`) for managing the `model_pricing` table. Alongside phase 2's existing CRUD — don't remove the old endpoints.
4. **Frontend dashboard replaces the old CRUD page.** The existing `AIUsagePage.tsx` is rewritten as a read-oriented dashboard with stat cards, a `recharts` stacked bar chart (via shadcn/ui's `chart` component, which wraps Recharts), a simple filterable sortable table, and an expandable "Model pricing" section for CRUD on custom pricing rows. The old `DataTable`/`EditSheet`/`DeleteDialog` flow is removed from this page — if an admin wants raw CRUD on ai_usage rows, the backend endpoints still exist and they can hit them via curl or a future debugging page.
5. **shadcn/ui chart component.** Installed via `npx shadcn@latest add chart`, which pulls in Recharts and generates a small wrapper at `admin-ui/src/components/ui/chart.tsx`. No manual Recharts integration.

**Tech Stack (new to phase 4d):**
- **Backend:** no new dependencies. Uses stdlib `datetime` for month math and existing SQLAlchemy for queries.
- **Frontend:** `recharts` (pulled in as a dependency of shadcn's chart component) + a new `chart.tsx` from the shadcn registry. No other new packages.

**Spec reference:** `docs/superpowers/specs/2026-04-06-admin-dashboard-design.md`. Read §10.4 (AI Usage dashboard — authoritative), §14 phase 4 bullet, §15 open question 2 ("static pricing table contents"), §17 acceptance criterion 3.

**Phases 1-3 + 4a + 4b + 4c already delivered.** Phase 2 shipped a basic CRUD page for `ai_usage` at `/admin/ai/usage`; phase 4d rewrites that page into a dashboard. The existing CRUD router (`flexloop.admin.routers.ai_usage`) stays in place — phase 4d adds new endpoints next to it, does not remove it. The `model_pricing` table and the `AIUsage` model already exist from phase 1.

**Phase 5 is out of scope.**

---

## Decisions locked in for this phase

These choices are fixed. Do not re-litigate mid-execution.

1. **Cost is computed at READ time, not WRITE time.** The stored `estimated_cost` column on `ai_usage` is ignored by the dashboard (the existing iOS writer path stores `0.0` anyway). The stats endpoint computes cost live using `settings.ai_model` as the assumed model for ALL rows. If the admin changes the model in phase 4a's config editor, past usage gets retroactively re-priced the next time the dashboard loads. This is the pragmatic choice given the lossy aggregation schema.

2. **Unknown-model cost shows `—` (null in the API).** `compute_cost` returns `None` when no pricing row is found. The stats endpoint serializes `None` as JSON `null`. The frontend table renders `null` cost as an em-dash `—`. Never guess, never default to zero.

3. **Static `PRICING` dict contents.** Minimal subset covering common OpenAI + Anthropic + DeepSeek models as of 2026-04. Values are USD per million tokens. Exact contents locked in Task 1. The dict is the fallback; admins add custom models via the UI.

4. **`get_model_pricing` precedence:** `model_pricing` DB table first → static `PRICING` dict second → `None` third. An entry with `model_name="gpt-4o-mini"` in the DB completely replaces the static dict's entry (no field merging).

5. **Stats endpoint shape (single payload).** One endpoint returns `{current_month, last_12_months, rows}`. Clients don't chain calls. The endpoint accepts optional `month_from`, `month_to`, `user_id` query params that filter the `rows` list (but NOT `current_month` or `last_12_months`, which always reflect the full dataset). Unfiltered rows are capped at 1000 so a bad filter doesn't return the whole DB.

6. **12-month chart window.** "Last 12 months" is computed from the current server date: `today.replace(day=1)` minus 11 months, inclusive. Months with zero usage are emitted as `{month: "YYYY-MM", input_tokens: 0, output_tokens: 0, estimated_cost: 0 | null}` so the chart has a flat line instead of a gap.

7. **Cost in `last_12_months` reflects pricing at READ time.** If pricing for `settings.ai_model` is missing, each month's `estimated_cost` is `null` and the chart's cost axis is hidden or shows `—`.

8. **Pricing CRUD endpoints: 3 endpoints, no list-all paginated shape.** `GET /pricing` returns `{db_entries: [...], static_entries: [{model_name, input_per_million, output_per_million}, ...]}` — two separate arrays so the UI can label which source each pricing row came from. `PUT /pricing/{model_name}` is an UPSERT on the `model_pricing` table. `DELETE /pricing/{model_name}` deletes the DB row (silently succeeds if not present — static fallback kicks in on the next read).

9. **No validation on pricing values beyond "non-negative number".** Admins can set prices to zero (free tier) or high values. The UI warns if the value exceeds a sanity threshold but does not block.

10. **Phase 2's AI Usage CRUD router stays untouched.** New endpoints go in a new router file `flexloop.admin.routers.ai_dashboard` to keep the surface areas separate. The new router is mounted under the same `/api/admin/ai/*` umbrella but with distinct sub-paths.

11. **Frontend: rewrite `AIUsagePage.tsx` entirely.** The old CRUD shell is deleted. The new page:
    - Top: 4 stat cards (Input tokens, Output tokens, Calls, Estimated cost) for the current month
    - Middle: Recharts stacked bar chart (12 months × input+output, stacked)
    - Middle-lower: filter bar (month_from date input, month_to date input, user_id input) + a simple table with sortable headers
    - Bottom: expandable "Model pricing" section with a small table of current pricing entries + "Add / Edit" dialog + Delete button
    - No `DataTable` / `EditSheet` / `DeleteDialog` — this page's UX is different enough that reusing them is forced.

12. **Delete the old `AIUsageForm.tsx`** — it's no longer referenced.

13. **`shadcn@latest add chart`** installs `recharts` and generates a wrapper at `admin-ui/src/components/ui/chart.tsx`. Do NOT manually install recharts separately — let shadcn handle the dependency.

14. **No audit log for pricing changes in phase 4d.** Per spec §10.1 "v1 only audits config changes". The helper exists but stays reserved.

15. **Worktree + branch:**
    - Worktree: `/Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase4d`
    - Branch: `feat/admin-dashboard-phase4d-usage-dashboard`
    - Merge: fast-forward into `main`, delete branch + worktree, bump parent submodule, update memory.

---

## File Structure

All paths relative to `flexloop-server/` unless stated otherwise.

**Backend — new:**
```
src/flexloop/admin/
├── pricing.py                      NEW — PRICING dict + lookup/compute helpers
└── routers/
    └── ai_dashboard.py              NEW — stats endpoint + pricing CRUD
```

**Backend — modified:**
```
src/flexloop/main.py                 add import + include_router for admin_ai_dashboard_router
```

**Backend — tests:**
```
tests/
├── test_admin_pricing.py            NEW — unit tests for pricing module
└── test_admin_ai_dashboard.py       NEW — integration tests for stats + pricing CRUD
```

**Frontend — new:**
```
admin-ui/src/
└── components/ui/chart.tsx          NEW (generated by shadcn add chart)
```

**Frontend — modified (heavy rewrite):**
```
admin-ui/src/
├── pages/AIUsagePage.tsx            REWRITE — dashboard (stat cards + chart + table + pricing section)
└── lib/api.types.ts                 regenerated
```

**Frontend — deleted:**
```
admin-ui/src/components/forms/AIUsageForm.tsx    DELETE — no longer referenced
```

**Docs:**
```
docs/admin-dashboard-phase4d-smoke-test.md       NEW — manual + automated checklist
```

---

## Execution setup

```bash
cd /Users/flyingchickens/Projects/FlexLoop/flexloop-server
git worktree add /Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase4d -b feat/admin-dashboard-phase4d-usage-dashboard
cd /Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase4d
uv sync --extra dev
uv pip install -e .
cd admin-ui && npm install --legacy-peer-deps && cd ..
```

Verify baseline:

```bash
uv run pytest -q
```

Expected: 404 tests passing (phase 4c baseline).

```bash
cd admin-ui && npx tsc --noEmit && npm run build && cd ..
```

Expected: both green.

---

## Chunk 1: Backend — pricing module

### Task 1: `flexloop.admin.pricing` + failing unit tests

**Files:**
- Create: `src/flexloop/admin/pricing.py`
- Create: `tests/test_admin_pricing.py`

- [ ] **Step 1: Write the failing tests**

```python
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
        # 500_000 input tokens * $1/M = $0.50
        # 250_000 output tokens * $2/M = $0.50
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
        # 3 + 15 + 0.30 + 3.75 = 22.05
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
            cache_read_tokens=1_000_000,  # ignored
            cache_write_tokens=1_000_000,  # ignored
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
        self, db_session: AsyncSession
    ) -> None:
        # "gpt-4o-mini" should be in the static PRICING dict
        result = await get_model_pricing(db_session, "gpt-4o-mini")
        assert result is not None
        assert result.input_per_million == PRICING["gpt-4o-mini"]["input"]
        assert result.output_per_million == PRICING["gpt-4o-mini"]["output"]
        assert result.cache_read_per_million is None
        assert result.cache_write_per_million is None

    async def test_db_row_overrides_static(
        self, db_session: AsyncSession
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
        self, db_session: AsyncSession
    ) -> None:
        """Admin-added pricing for a model not in the static dict."""
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
```

- [ ] **Step 2: Run the tests to confirm failure**

```bash
uv run pytest tests/test_admin_pricing.py -v
```

Expected: all fail with `ModuleNotFoundError: flexloop.admin.pricing`.

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_admin_pricing.py
git commit -m "test(admin): failing tests for pricing module"
```

---

### Task 2: Implement the pricing module

**Files:**
- Create: `src/flexloop/admin/pricing.py`

- [ ] **Step 1: Write the module**

```python
"""Model pricing and cost computation.

The dashboard answers "how much did this month cost" by combining
per-user-per-month token totals from ``ai_usage`` with a pricing lookup:
1. ``model_pricing`` DB table (admin-managed custom overrides)
2. Static ``PRICING`` dict below (common built-in models)
3. ``None`` (unknown model — UI shows "—")

All prices are USD per million tokens. The numbers in ``PRICING`` are
rounded to the nearest published tier as of 2026-04; admins who need
different values can override via the admin UI.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.models.model_pricing import ModelPricing


# ---------------------------------------------------------------------------
# Static pricing dict — USD per million tokens
# ---------------------------------------------------------------------------

PRICING: dict[str, dict[str, float]] = {
    # OpenAI — https://openai.com/api/pricing
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    # Anthropic — https://www.anthropic.com/pricing
    "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
    "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.00},
    "claude-3-opus-20240229": {"input": 15.00, "output": 75.00},
    # DeepSeek (proxy-friendly, cheap)
    "deepseek-chat": {"input": 0.27, "output": 1.10},
}


# ---------------------------------------------------------------------------
# Resolved pricing for a specific model — merges DB override with static default
# ---------------------------------------------------------------------------


@dataclass
class ModelPricingValues:
    """Pricing for a single model — per-million-token rates.

    ``cache_read_per_million`` and ``cache_write_per_million`` are
    optional because static entries don't track them (only Anthropic's
    Claude models price cache separately, and the admin can add custom
    DB entries for other providers).
    """
    input_per_million: float
    output_per_million: float
    cache_read_per_million: float | None
    cache_write_per_million: float | None


async def get_model_pricing(
    db: AsyncSession,
    model_name: str,
) -> ModelPricingValues | None:
    """Resolve pricing for ``model_name``.

    Lookup order:
    1. ``model_pricing`` DB row (if any) — full override, including optional cache rates
    2. Static ``PRICING`` dict entry — input/output only, cache rates None
    3. ``None`` — unknown model
    """
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
    """Return USD cost for the given token counts.

    Returns ``None`` if ``pricing`` is None — do NOT guess. Cache token
    costs are only included when the pricing row has a corresponding
    per-million rate; otherwise cache tokens contribute zero (they're
    counted in the display, but not billed).
    """
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
```

- [ ] **Step 2: Run the tests**

```bash
uv run pytest tests/test_admin_pricing.py -v
```

Expected: all ~13 tests pass.

- [ ] **Step 3: Full suite**

```bash
uv run pytest -q
```

Expected: 417 tests green (404 + 13 new).

- [ ] **Step 4: Commit**

```bash
git add src/flexloop/admin/pricing.py
git commit -m "feat(admin): pricing module with static PRICING dict + DB override lookup"
```

---

**End of Chunk 1.** Pricing module is unit-tested and ready for the dashboard endpoints to use.

---

## Chunk 2: Backend — stats endpoint + pricing CRUD

### Task 3: Failing tests for `GET /api/admin/ai/usage/stats`

**Files:**
- Create: `tests/test_admin_ai_dashboard.py`

- [ ] **Step 1: Write the test file**

```python
"""Integration tests for /api/admin/ai/usage/stats + /api/admin/ai/pricing."""
from __future__ import annotations

from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import SESSION_COOKIE_NAME, create_session, hash_password
from flexloop.models.admin_user import AdminUser
from flexloop.models.ai import AIUsage
from flexloop.models.model_pricing import ModelPricing
from flexloop.models.user import User


ORIGIN = "http://localhost:5173"


async def _make_admin_and_cookie(db: AsyncSession) -> dict[str, str]:
    admin = AdminUser(username="tester", password_hash=hash_password("password123"))
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    token, _ = await create_session(db, admin_user_id=admin.id)
    return {SESSION_COOKIE_NAME: token}


async def _make_user(db: AsyncSession, name: str = "Usage User") -> User:
    user = User(
        name=name, gender="other", age=30, height=180, weight=80,
        weight_unit="kg", height_unit="cm", experience_level="intermediate",
        goals="", available_equipment=[],
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _current_month() -> str:
    """The current month as YYYY-MM, matching the backend's convention."""
    return date.today().strftime("%Y-%m")


class TestStatsCurrentMonth:
    async def test_requires_auth(self, client: AsyncClient) -> None:
        assert (await client.get("/api/admin/ai/usage/stats")).status_code == 401

    async def test_empty_returns_zero_totals(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.get("/api/admin/ai/usage/stats", cookies=cookies)
        assert res.status_code == 200
        body = res.json()
        assert "current_month" in body
        cm = body["current_month"]
        assert cm["month"] == _current_month()
        assert cm["input_tokens"] == 0
        assert cm["output_tokens"] == 0
        assert cm["call_count"] == 0

    async def test_aggregates_across_users(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        u1 = await _make_user(db_session, "u1")
        u2 = await _make_user(db_session, "u2")
        month = _current_month()
        db_session.add_all([
            AIUsage(
                user_id=u1.id, month=month,
                total_input_tokens=100, total_output_tokens=50,
                total_cache_read_tokens=0, total_cache_creation_tokens=0,
                estimated_cost=0, call_count=3,
            ),
            AIUsage(
                user_id=u2.id, month=month,
                total_input_tokens=200, total_output_tokens=70,
                total_cache_read_tokens=10, total_cache_creation_tokens=5,
                estimated_cost=0, call_count=4,
            ),
        ])
        await db_session.commit()

        res = await client.get("/api/admin/ai/usage/stats", cookies=cookies)
        body = res.json()
        cm = body["current_month"]
        assert cm["input_tokens"] == 300
        assert cm["output_tokens"] == 120
        assert cm["cache_read_tokens"] == 10
        assert cm["cache_write_tokens"] == 5
        assert cm["call_count"] == 7

    async def test_current_month_includes_cost_when_pricing_known(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """With the default ai_model=gpt-4o-mini and 1M input/1M output
        tokens, cost should be 0.15 + 0.60 = 0.75 USD.
        """
        cookies = await _make_admin_and_cookie(db_session)
        user = await _make_user(db_session)
        month = _current_month()
        db_session.add(
            AIUsage(
                user_id=user.id, month=month,
                total_input_tokens=1_000_000, total_output_tokens=1_000_000,
                total_cache_read_tokens=0, total_cache_creation_tokens=0,
                estimated_cost=0, call_count=1,
            )
        )
        await db_session.commit()

        res = await client.get("/api/admin/ai/usage/stats", cookies=cookies)
        body = res.json()
        assert body["current_month"]["estimated_cost"] == pytest.approx(0.75, abs=1e-9)

    async def test_unknown_model_returns_null_cost(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from flexloop.config import settings
        # Point the in-memory settings at a model nobody knows
        monkeypatch.setattr(settings, "ai_model", "never-heard-of-this-model")

        cookies = await _make_admin_and_cookie(db_session)
        user = await _make_user(db_session)
        db_session.add(
            AIUsage(
                user_id=user.id, month=_current_month(),
                total_input_tokens=1_000, total_output_tokens=500,
                total_cache_read_tokens=0, total_cache_creation_tokens=0,
                estimated_cost=0, call_count=1,
            )
        )
        await db_session.commit()

        res = await client.get("/api/admin/ai/usage/stats", cookies=cookies)
        assert res.status_code == 200
        assert res.json()["current_month"]["estimated_cost"] is None


class TestStatsLast12Months:
    async def test_returns_12_entries(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.get("/api/admin/ai/usage/stats", cookies=cookies)
        body = res.json()
        assert len(body["last_12_months"]) == 12

    async def test_oldest_first_ordering(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.get("/api/admin/ai/usage/stats", cookies=cookies)
        months = [m["month"] for m in res.json()["last_12_months"]]
        # Months should be in ascending order, most recent = current month
        assert months == sorted(months)
        assert months[-1] == _current_month()

    async def test_months_with_no_usage_show_zero(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Zero-usage months must still appear so the chart has a flat line."""
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.get("/api/admin/ai/usage/stats", cookies=cookies)
        for m in res.json()["last_12_months"]:
            assert "input_tokens" in m
            assert m["input_tokens"] >= 0


class TestStatsRows:
    async def test_returns_all_rows_by_default(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        u1 = await _make_user(db_session, "u1")
        u2 = await _make_user(db_session, "u2")
        db_session.add_all([
            AIUsage(
                user_id=u1.id, month="2026-01",
                total_input_tokens=100, total_output_tokens=50,
                total_cache_read_tokens=0, total_cache_creation_tokens=0,
                estimated_cost=0, call_count=1,
            ),
            AIUsage(
                user_id=u2.id, month="2026-02",
                total_input_tokens=200, total_output_tokens=100,
                total_cache_read_tokens=0, total_cache_creation_tokens=0,
                estimated_cost=0, call_count=2,
            ),
        ])
        await db_session.commit()

        res = await client.get("/api/admin/ai/usage/stats", cookies=cookies)
        rows = res.json()["rows"]
        assert len(rows) == 2

    async def test_filter_by_user_id(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        u1 = await _make_user(db_session, "u1")
        u2 = await _make_user(db_session, "u2")
        db_session.add_all([
            AIUsage(
                user_id=u1.id, month="2026-01",
                total_input_tokens=100, total_output_tokens=50,
                total_cache_read_tokens=0, total_cache_creation_tokens=0,
                estimated_cost=0, call_count=1,
            ),
            AIUsage(
                user_id=u2.id, month="2026-01",
                total_input_tokens=200, total_output_tokens=100,
                total_cache_read_tokens=0, total_cache_creation_tokens=0,
                estimated_cost=0, call_count=2,
            ),
        ])
        await db_session.commit()

        res = await client.get(
            f"/api/admin/ai/usage/stats?user_id={u1.id}", cookies=cookies
        )
        rows = res.json()["rows"]
        assert len(rows) == 1
        assert rows[0]["user_id"] == u1.id

    async def test_filter_by_month_range(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        user = await _make_user(db_session)
        db_session.add_all([
            AIUsage(
                user_id=user.id, month="2025-12",
                total_input_tokens=10, total_output_tokens=5,
                total_cache_read_tokens=0, total_cache_creation_tokens=0,
                estimated_cost=0, call_count=1,
            ),
            AIUsage(
                user_id=user.id, month="2026-02",
                total_input_tokens=20, total_output_tokens=10,
                total_cache_read_tokens=0, total_cache_creation_tokens=0,
                estimated_cost=0, call_count=1,
            ),
            AIUsage(
                user_id=user.id, month="2026-04",
                total_input_tokens=30, total_output_tokens=15,
                total_cache_read_tokens=0, total_cache_creation_tokens=0,
                estimated_cost=0, call_count=1,
            ),
        ])
        await db_session.commit()

        res = await client.get(
            "/api/admin/ai/usage/stats?month_from=2026-01&month_to=2026-03",
            cookies=cookies,
        )
        rows = res.json()["rows"]
        assert len(rows) == 1
        assert rows[0]["month"] == "2026-02"
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/test_admin_ai_dashboard.py -v
```

Expected: all fail (router doesn't exist, 404/401).

- [ ] **Step 3: Commit**

```bash
git add tests/test_admin_ai_dashboard.py
git commit -m "test(admin): failing tests for AI usage dashboard stats endpoint"
```

---

### Task 4: Implement the dashboard router + stats endpoint

**Files:**
- Create: `src/flexloop/admin/routers/ai_dashboard.py`
- Modify: `src/flexloop/main.py`

- [ ] **Step 1: Write the router**

```python
"""Admin AI usage dashboard endpoints.

Two groups:
- ``GET /api/admin/ai/usage/stats`` — dashboard payload (current month card
  values, 12-month chart array, filtered row list)
- ``GET/PUT/DELETE /api/admin/ai/pricing`` — CRUD on the ``model_pricing``
  override table

Cost estimation runs at READ time using ``settings.ai_model`` as the
assumed model. See ``flexloop.admin.pricing`` for the lookup chain.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
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


# --- Schemas --------------------------------------------------------------


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


# --- Helpers --------------------------------------------------------------


def _current_month_str() -> str:
    return date.today().strftime("%Y-%m")


def _months_back(n: int) -> list[str]:
    """Return the last ``n`` months as YYYY-MM strings, oldest first.

    ``n=12`` starting from 2026-04 returns
    ``["2025-05", "2025-06", ..., "2026-04"]``.
    """
    today = date.today().replace(day=1)
    months: list[str] = []
    # Walk back n-1 times to include the current month as the last entry.
    year, month = today.year, today.month
    for _ in range(n):
        months.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return list(reversed(months))


def _row_to_model(row: AIUsage, pricing: ModelPricingValues | None) -> UsageRow:
    cost = compute_cost(
        pricing,
        row.total_input_tokens,
        row.total_output_tokens,
        row.total_cache_read_tokens,
        row.total_cache_creation_tokens,
    )
    return UsageRow(
        id=row.id,
        month=row.month,
        user_id=row.user_id,
        input_tokens=row.total_input_tokens,
        output_tokens=row.total_output_tokens,
        cache_read_tokens=row.total_cache_read_tokens,
        cache_write_tokens=row.total_cache_creation_tokens,
        call_count=row.call_count,
        estimated_cost=cost,
    )


# --- GET /usage/stats -----------------------------------------------------


_ROW_CAP = 1000  # safety cap on returned rows — bad filter shouldn't dump the DB


@router.get("/usage/stats", response_model=StatsResponse)
async def get_usage_stats(
    month_from: str | None = Query(None, description="YYYY-MM inclusive lower bound"),
    month_to: str | None = Query(None, description="YYYY-MM inclusive upper bound"),
    user_id: int | None = Query(None),
    db: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(require_admin),
) -> StatsResponse:
    # Resolve pricing once for the assumed model — used across all rows.
    pricing = await get_model_pricing(db, settings.ai_model)

    # 1) Current-month card — SUM over all rows where month == current_month
    current_month = _current_month_str()
    cm_query = select(
        func.coalesce(func.sum(AIUsage.total_input_tokens), 0),
        func.coalesce(func.sum(AIUsage.total_output_tokens), 0),
        func.coalesce(func.sum(AIUsage.total_cache_read_tokens), 0),
        func.coalesce(func.sum(AIUsage.total_cache_creation_tokens), 0),
        func.coalesce(func.sum(AIUsage.call_count), 0),
    ).where(AIUsage.month == current_month)
    cm_result = await db.execute(cm_query)
    cm_row = cm_result.one()
    cm_input, cm_output, cm_cache_read, cm_cache_write, cm_calls = (
        int(cm_row[0]), int(cm_row[1]), int(cm_row[2]), int(cm_row[3]), int(cm_row[4])
    )
    cm_cost = compute_cost(pricing, cm_input, cm_output, cm_cache_read, cm_cache_write)

    current_card = UsageCard(
        month=current_month,
        input_tokens=cm_input,
        output_tokens=cm_output,
        cache_read_tokens=cm_cache_read,
        cache_write_tokens=cm_cache_write,
        call_count=cm_calls,
        estimated_cost=cm_cost,
    )

    # 2) Last 12 months — one ChartPoint per month, zero-filled
    last_12 = _months_back(12)
    chart_query = select(
        AIUsage.month,
        func.coalesce(func.sum(AIUsage.total_input_tokens), 0),
        func.coalesce(func.sum(AIUsage.total_output_tokens), 0),
        func.coalesce(func.sum(AIUsage.total_cache_read_tokens), 0),
        func.coalesce(func.sum(AIUsage.total_cache_creation_tokens), 0),
    ).where(AIUsage.month.in_(last_12)).group_by(AIUsage.month)
    chart_result = await db.execute(chart_query)
    by_month: dict[str, tuple[int, int, int, int]] = {}
    for m, i, o, cr, cw in chart_result.all():
        by_month[m] = (int(i), int(o), int(cr), int(cw))

    chart_points: list[ChartPoint] = []
    for m in last_12:
        i, o, cr, cw = by_month.get(m, (0, 0, 0, 0))
        chart_points.append(
            ChartPoint(
                month=m,
                input_tokens=i,
                output_tokens=o,
                estimated_cost=compute_cost(pricing, i, o, cr, cw),
            )
        )

    # 3) Filtered rows for the table
    rows_query = select(AIUsage)
    if user_id is not None:
        rows_query = rows_query.where(AIUsage.user_id == user_id)
    if month_from is not None:
        rows_query = rows_query.where(AIUsage.month >= month_from)
    if month_to is not None:
        rows_query = rows_query.where(AIUsage.month <= month_to)
    rows_query = rows_query.order_by(AIUsage.month.desc(), AIUsage.user_id).limit(_ROW_CAP)
    rows_result = await db.execute(rows_query)
    rows = [_row_to_model(r, pricing) for r in rows_result.scalars().all()]

    return StatsResponse(
        current_month=current_card,
        last_12_months=chart_points,
        rows=rows,
        assumed_model=settings.ai_model,
    )
```

- [ ] **Step 2: Mount the router in `main.py`**

Add the import:
```python
from flexloop.admin.routers.ai_dashboard import router as admin_ai_dashboard_router
```

And `app.include_router(admin_ai_dashboard_router)` next to the other admin routers.

- [ ] **Step 3: Run the stats tests**

```bash
uv run pytest tests/test_admin_ai_dashboard.py -v
```

Expected: all stats tests pass (the pricing CRUD tests come later).

- [ ] **Step 4: Full suite**

```bash
uv run pytest -q
```

Expected: 428 tests green (417 + 11 new stats tests — if count differs, verify the test classes match the plan).

- [ ] **Step 5: Commit**

```bash
git add src/flexloop/admin/routers/ai_dashboard.py src/flexloop/main.py
git commit -m "feat(admin): GET /api/admin/ai/usage/stats dashboard endpoint"
```

---

### Task 5: Failing tests for pricing CRUD

**Files:**
- Modify: `tests/test_admin_ai_dashboard.py`

- [ ] **Step 1: Append pricing CRUD tests**

```python
class TestGetPricing:
    async def test_requires_auth(self, client: AsyncClient) -> None:
        assert (await client.get("/api/admin/ai/pricing")).status_code == 401

    async def test_returns_static_and_db_entries(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        db_session.add(
            ModelPricing(
                model_name="custom-proxy",
                input_per_million=0.50,
                output_per_million=1.00,
                cache_read_per_million=None,
                cache_write_per_million=None,
            )
        )
        await db_session.commit()

        res = await client.get("/api/admin/ai/pricing", cookies=cookies)
        assert res.status_code == 200
        body = res.json()
        assert "db_entries" in body
        assert "static_entries" in body
        db_names = {e["model_name"] for e in body["db_entries"]}
        assert "custom-proxy" in db_names
        static_names = {e["model_name"] for e in body["static_entries"]}
        assert "gpt-4o-mini" in static_names


class TestUpsertPricing:
    async def test_requires_auth(self, client: AsyncClient) -> None:
        res = await client.put(
            "/api/admin/ai/pricing/custom-model",
            json={"input_per_million": 1.0, "output_per_million": 2.0},
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 401

    async def test_creates_new_entry(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.put(
            "/api/admin/ai/pricing/new-model",
            json={
                "input_per_million": 0.25,
                "output_per_million": 0.50,
                "cache_read_per_million": 0.05,
                "cache_write_per_million": 0.60,
            },
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["model_name"] == "new-model"
        assert body["input_per_million"] == 0.25
        assert body["output_per_million"] == 0.50

        # Verify DB
        row = (
            await db_session.execute(
                select(ModelPricing).where(ModelPricing.model_name == "new-model")
            )
        ).scalar_one_or_none()
        assert row is not None
        assert row.input_per_million == 0.25

    async def test_updates_existing_entry(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        db_session.add(
            ModelPricing(
                model_name="existing",
                input_per_million=1.0,
                output_per_million=2.0,
                cache_read_per_million=None,
                cache_write_per_million=None,
            )
        )
        await db_session.commit()

        res = await client.put(
            "/api/admin/ai/pricing/existing",
            json={"input_per_million": 99.0, "output_per_million": 199.0},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 200
        row = (
            await db_session.execute(
                select(ModelPricing).where(ModelPricing.model_name == "existing")
            )
        ).scalar_one()
        assert row.input_per_million == 99.0
        assert row.output_per_million == 199.0

    async def test_rejects_negative(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.put(
            "/api/admin/ai/pricing/bad",
            json={"input_per_million": -1.0, "output_per_million": 1.0},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 422

    async def test_rejects_unknown_field(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.put(
            "/api/admin/ai/pricing/bad",
            json={
                "input_per_million": 1.0,
                "output_per_million": 2.0,
                "wrong_field": 99,
            },
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 422


class TestDeletePricing:
    async def test_requires_auth(self, client: AsyncClient) -> None:
        res = await client.delete(
            "/api/admin/ai/pricing/whatever", headers={"Origin": ORIGIN}
        )
        assert res.status_code == 401

    async def test_deletes_existing(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        db_session.add(
            ModelPricing(
                model_name="to-delete",
                input_per_million=1.0,
                output_per_million=2.0,
                cache_read_per_million=None,
                cache_write_per_million=None,
            )
        )
        await db_session.commit()

        res = await client.delete(
            "/api/admin/ai/pricing/to-delete",
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 204

        row = (
            await db_session.execute(
                select(ModelPricing).where(ModelPricing.model_name == "to-delete")
            )
        ).scalar_one_or_none()
        assert row is None

    async def test_nonexistent_silently_succeeds(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Deleting a model_name that has no DB row returns 204 — the
        static fallback takes over on the next read, and the operation
        is idempotent.
        """
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.delete(
            "/api/admin/ai/pricing/never-existed",
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 204
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/test_admin_ai_dashboard.py::TestGetPricing tests/test_admin_ai_dashboard.py::TestUpsertPricing tests/test_admin_ai_dashboard.py::TestDeletePricing -v
```

Expected: 9 fail.

- [ ] **Step 3: Commit**

```bash
git add tests/test_admin_ai_dashboard.py
git commit -m "test(admin): failing tests for pricing CRUD endpoints"
```

---

### Task 6: Implement the pricing CRUD endpoints

**Files:**
- Modify: `src/flexloop/admin/routers/ai_dashboard.py`

- [ ] **Step 1: Append schemas + handlers**

```python
# --- Pricing CRUD schemas -------------------------------------------------


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

    input_per_million: float = Query(..., ge=0)
    output_per_million: float = Query(..., ge=0)
    cache_read_per_million: float | None = None
    cache_write_per_million: float | None = None


# --- GET /pricing ---------------------------------------------------------


@router.get("/pricing", response_model=PricingListResponse)
async def list_pricing(
    db: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(require_admin),
) -> PricingListResponse:
    rows = (await db.execute(select(ModelPricing))).scalars().all()
    db_entries = [
        PricingDbEntry(
            model_name=r.model_name,
            input_per_million=r.input_per_million,
            output_per_million=r.output_per_million,
            cache_read_per_million=r.cache_read_per_million,
            cache_write_per_million=r.cache_write_per_million,
        )
        for r in rows
    ]
    static_entries = [
        PricingStaticEntry(
            model_name=name,
            input_per_million=values["input"],
            output_per_million=values["output"],
        )
        for name, values in sorted(PRICING.items())
    ]
    return PricingListResponse(db_entries=db_entries, static_entries=static_entries)


# --- PUT /pricing/{model_name} --------------------------------------------


@router.put("/pricing/{model_name}", response_model=PricingDbEntry)
async def upsert_pricing(
    model_name: str,
    payload: PricingUpsert,
    db: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(require_admin),
) -> PricingDbEntry:
    # Reject names with path-traversal-ish characters — not security-critical
    # here (it's not a filesystem path) but keeps the DB clean.
    if not model_name or any(c in model_name for c in "/\\"):
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


# --- DELETE /pricing/{model_name} -----------------------------------------


@router.delete(
    "/pricing/{model_name}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_pricing(
    model_name: str,
    db: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(require_admin),
) -> None:
    """Delete a DB pricing row. Idempotent — nonexistent rows return 204."""
    existing = (
        await db.execute(
            select(ModelPricing).where(ModelPricing.model_name == model_name)
        )
    ).scalar_one_or_none()
    if existing is not None:
        await db.delete(existing)
        await db.commit()
```

**Note on `PricingUpsert` validation:** the plan uses `Query(..., ge=0)` on Pydantic fields — this is INCORRECT syntax. Pydantic v2 uses `Field(..., ge=0)` from the `pydantic` package, not `Query` from FastAPI. Replace with:

```python
from pydantic import BaseModel, ConfigDict, Field

class PricingUpsert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_per_million: float = Field(..., ge=0)
    output_per_million: float = Field(..., ge=0)
    cache_read_per_million: float | None = Field(None, ge=0)
    cache_write_per_million: float | None = Field(None, ge=0)
```

Make sure `Field` is imported from pydantic in the file.

- [ ] **Step 2: Run the pricing CRUD tests**

```bash
uv run pytest tests/test_admin_ai_dashboard.py::TestGetPricing tests/test_admin_ai_dashboard.py::TestUpsertPricing tests/test_admin_ai_dashboard.py::TestDeletePricing -v
```

Expected: all 9 pass.

- [ ] **Step 3: Full suite**

```bash
uv run pytest -q
```

Expected: 437 tests green.

- [ ] **Step 4: Commit**

```bash
git add src/flexloop/admin/routers/ai_dashboard.py
git commit -m "feat(admin): pricing CRUD endpoints (list/upsert/delete)"
```

---

**End of Chunk 2.** Backend is complete: stats endpoint + pricing CRUD + unit-tested pricing module.

---

## Chunk 3: Frontend — dashboard page rewrite

### Task 7: Regenerate `api.types.ts` + install shadcn chart

**Files:**
- Modify: `admin-ui/src/lib/api.types.ts`
- Create: `admin-ui/src/components/ui/chart.tsx`

- [ ] **Step 1: Start backend + regenerate types**

Use `run_in_background: true`:
```bash
cd /Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase4d
uv run uvicorn flexloop.main:app --port 8000
```

Then in foreground:
```bash
cd admin-ui && sleep 2 && npm run codegen
```

Expected: diff adds `StatsResponse`, `UsageCard`, `ChartPoint`, `UsageRow`, `PricingListResponse`, `PricingDbEntry`, `PricingStaticEntry`, `PricingUpsert`.

- [ ] **Step 2: Stop the backend**

Kill the background uvicorn.

- [ ] **Step 3: Install shadcn chart component**

```bash
cd admin-ui
npx shadcn@latest add chart
```

Accept any prompts. This installs `recharts` as a dependency and generates `src/components/ui/chart.tsx`.

- [ ] **Step 4: Verify `recharts` is in package.json**

```bash
grep recharts package.json
```

Expected: `"recharts": "^..."` entry present.

- [ ] **Step 5: Verify the build**

```bash
npm run build
```

Expected: succeeds. Bundle size grows.

- [ ] **Step 6: Commit**

```bash
cd ..
git add admin-ui/src/lib/api.types.ts admin-ui/src/components/ui/chart.tsx admin-ui/package.json admin-ui/package-lock.json
git commit -m "chore(admin-ui): regenerate types + install shadcn chart (recharts)"
```

---

### Task 8: Rewrite `AIUsagePage.tsx` — stat cards + chart + table

**Files:**
- Modify: `admin-ui/src/pages/AIUsagePage.tsx` (complete rewrite)
- Delete: `admin-ui/src/components/forms/AIUsageForm.tsx`

- [ ] **Step 1: Delete the old form**

```bash
rm admin-ui/src/components/forms/AIUsageForm.tsx
```

- [ ] **Step 2: Rewrite `AIUsagePage.tsx`**

Open the file and replace its entire contents with:

```tsx
/**
 * AI Usage dashboard.
 *
 * Replaces the phase-2 CRUD shell with a read-oriented dashboard:
 * - Stat cards for the current month's totals
 * - 12-month stacked bar chart of input/output tokens
 * - Filterable, sortable per-user-per-month table
 * - Expandable "Model pricing" section (added in Chunk 4)
 *
 * Cost is computed at read time on the server using settings.ai_model.
 * Unknown models show "—" — the UI never pretends to know.
 */
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import type { components } from "@/lib/api.types";

type StatsResponse = components["schemas"]["StatsResponse"];
type UsageRow = components["schemas"]["UsageRow"];

type SortKey =
  | "month"
  | "user_id"
  | "input_tokens"
  | "output_tokens"
  | "call_count"
  | "estimated_cost";

type SortDir = "asc" | "desc";

function formatCost(cost: number | null | undefined): string {
  if (cost === null || cost === undefined) return "—";
  if (cost === 0) return "$0.00";
  if (cost < 0.01) return `<$0.01`;
  return `$${cost.toFixed(2)}`;
}

function formatTokens(n: number): string {
  return n.toLocaleString("en-US");
}

export function AIUsagePage() {
  const [monthFrom, setMonthFrom] = useState("");
  const [monthTo, setMonthTo] = useState("");
  const [userFilter, setUserFilter] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("month");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const statsQuery = useQuery({
    queryKey: [
      "admin",
      "ai",
      "usage",
      "stats",
      { month_from: monthFrom, month_to: monthTo, user_id: userFilter },
    ],
    queryFn: () => {
      const params = new URLSearchParams();
      if (monthFrom) params.set("month_from", monthFrom);
      if (monthTo) params.set("month_to", monthTo);
      if (userFilter) params.set("user_id", userFilter);
      const qs = params.toString();
      return api.get<StatsResponse>(
        qs ? `/api/admin/ai/usage/stats?${qs}` : "/api/admin/ai/usage/stats",
      );
    },
  });

  const sortedRows = useMemo<UsageRow[]>(() => {
    if (!statsQuery.data?.rows) return [];
    const rows = [...statsQuery.data.rows];
    rows.sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      // null cost sorts last in asc, first in desc
      if (av === null && bv === null) return 0;
      if (av === null) return sortDir === "asc" ? 1 : -1;
      if (bv === null) return sortDir === "asc" ? -1 : 1;
      if (typeof av === "number" && typeof bv === "number") {
        return sortDir === "asc" ? av - bv : bv - av;
      }
      const as = String(av);
      const bs = String(bv);
      return sortDir === "asc" ? as.localeCompare(bs) : bs.localeCompare(as);
    });
    return rows;
  }, [statsQuery.data, sortKey, sortDir]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  if (statsQuery.isLoading) {
    return <div className="p-6">Loading AI usage…</div>;
  }
  if (statsQuery.isError || !statsQuery.data) {
    return <div className="p-6">Failed to load AI usage.</div>;
  }

  const { current_month, last_12_months, assumed_model } = statsQuery.data;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">AI Usage</h1>
        <p className="text-sm text-muted-foreground">
          Cost estimates assume all usage was against{" "}
          <Badge variant="secondary" className="font-mono">
            {assumed_model}
          </Badge>
          . Change the model in{" "}
          <a href="#/ai/config" className="underline">
            Config
          </a>{" "}
          to retrospectively re-price.
        </p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">
              Input tokens ({current_month.month})
            </CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold tabular-nums">
            {formatTokens(current_month.input_tokens)}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">
              Output tokens ({current_month.month})
            </CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold tabular-nums">
            {formatTokens(current_month.output_tokens)}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">
              Calls ({current_month.month})
            </CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold tabular-nums">
            {formatTokens(current_month.call_count)}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">
              Estimated cost ({current_month.month})
            </CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold tabular-nums">
            {formatCost(current_month.estimated_cost)}
          </CardContent>
        </Card>
      </div>

      {/* 12-month chart */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Last 12 months</CardTitle>
        </CardHeader>
        <CardContent className="h-[280px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={last_12_months}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="month" />
              <YAxis />
              <Tooltip
                formatter={(value: number) => formatTokens(value)}
                labelStyle={{ color: "#000" }}
              />
              <Legend />
              <Bar
                dataKey="input_tokens"
                stackId="tokens"
                fill="#3b82f6"
                name="Input"
              />
              <Bar
                dataKey="output_tokens"
                stackId="tokens"
                fill="#10b981"
                name="Output"
              />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* Filters */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Filter</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="month_from">From month (YYYY-MM)</Label>
            <Input
              id="month_from"
              placeholder="2025-05"
              value={monthFrom}
              onChange={(e) => setMonthFrom(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="month_to">To month (YYYY-MM)</Label>
            <Input
              id="month_to"
              placeholder="2026-04"
              value={monthTo}
              onChange={(e) => setMonthTo(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="user_id_filter">User ID</Label>
            <Input
              id="user_id_filter"
              type="number"
              placeholder="(any)"
              value={userFilter}
              onChange={(e) => setUserFilter(e.target.value)}
            />
          </div>
        </CardContent>
      </Card>

      {/* Table */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">
            Rows ({sortedRows.length})
          </CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left">
                <th
                  className="p-2 cursor-pointer hover:bg-muted"
                  onClick={() => toggleSort("month")}
                >
                  Month{sortKey === "month" ? (sortDir === "asc" ? " ▲" : " ▼") : ""}
                </th>
                <th
                  className="p-2 cursor-pointer hover:bg-muted"
                  onClick={() => toggleSort("user_id")}
                >
                  User{sortKey === "user_id" ? (sortDir === "asc" ? " ▲" : " ▼") : ""}
                </th>
                <th
                  className="p-2 cursor-pointer hover:bg-muted text-right"
                  onClick={() => toggleSort("call_count")}
                >
                  Calls{sortKey === "call_count" ? (sortDir === "asc" ? " ▲" : " ▼") : ""}
                </th>
                <th
                  className="p-2 cursor-pointer hover:bg-muted text-right"
                  onClick={() => toggleSort("input_tokens")}
                >
                  Input{sortKey === "input_tokens" ? (sortDir === "asc" ? " ▲" : " ▼") : ""}
                </th>
                <th
                  className="p-2 cursor-pointer hover:bg-muted text-right"
                  onClick={() => toggleSort("output_tokens")}
                >
                  Output{sortKey === "output_tokens" ? (sortDir === "asc" ? " ▲" : " ▼") : ""}
                </th>
                <th className="p-2 text-right">Cache read</th>
                <th className="p-2 text-right">Cache write</th>
                <th
                  className="p-2 cursor-pointer hover:bg-muted text-right"
                  onClick={() => toggleSort("estimated_cost")}
                >
                  Est. cost{sortKey === "estimated_cost" ? (sortDir === "asc" ? " ▲" : " ▼") : ""}
                </th>
              </tr>
            </thead>
            <tbody>
              {sortedRows.map((r) => (
                <tr key={r.id} className="border-b hover:bg-muted/40">
                  <td className="p-2 tabular-nums">{r.month}</td>
                  <td className="p-2 tabular-nums">{r.user_id}</td>
                  <td className="p-2 tabular-nums text-right">
                    {formatTokens(r.call_count)}
                  </td>
                  <td className="p-2 tabular-nums text-right">
                    {formatTokens(r.input_tokens)}
                  </td>
                  <td className="p-2 tabular-nums text-right">
                    {formatTokens(r.output_tokens)}
                  </td>
                  <td className="p-2 tabular-nums text-right">
                    {formatTokens(r.cache_read_tokens)}
                  </td>
                  <td className="p-2 tabular-nums text-right">
                    {formatTokens(r.cache_write_tokens)}
                  </td>
                  <td className="p-2 tabular-nums text-right">
                    {formatCost(r.estimated_cost)}
                  </td>
                </tr>
              ))}
              {sortedRows.length === 0 && (
                <tr>
                  <td
                    colSpan={8}
                    className="p-4 text-center text-muted-foreground"
                  >
                    No usage data for the current filter.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </CardContent>
      </Card>

      {/* Pricing management section — added in the next task */}
    </div>
  );
}
```

- [ ] **Step 3: Type-check + build**

```bash
cd admin-ui && npx tsc --noEmit && npm run build
```

Expected: both green. If TypeScript complains about the `useCrud` hooks (imported in the old version), delete the stale imports.

- [ ] **Step 4: Commit**

```bash
cd ..
git add admin-ui/src/pages/AIUsagePage.tsx admin-ui/src/components/forms/AIUsageForm.tsx
git commit -m "feat(admin-ui): rewrite AIUsagePage as dashboard with stat cards + chart + filtered table"
```

(The `git add` for the deleted form picks up the deletion.)

---

### Task 9: Pricing management section

**Files:**
- Modify: `admin-ui/src/pages/AIUsagePage.tsx`

- [ ] **Step 1: Add pricing query + upsert/delete mutations + UI**

Inside `AIUsagePage`, after the existing `statsQuery`, add:

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

type PricingListResponse = components["schemas"]["PricingListResponse"];
type PricingDbEntry = components["schemas"]["PricingDbEntry"];

// ... inside the AIUsagePage component, after statsQuery:

const qc = useQueryClient();
const [pricingOpen, setPricingOpen] = useState(false);
const [editTarget, setEditTarget] = useState<PricingDbEntry | "new" | null>(null);
const [editName, setEditName] = useState("");
const [editInput, setEditInput] = useState("");
const [editOutput, setEditOutput] = useState("");
const [editCacheRead, setEditCacheRead] = useState("");
const [editCacheWrite, setEditCacheWrite] = useState("");

const pricingQuery = useQuery({
  queryKey: ["admin", "ai", "pricing"],
  queryFn: () => api.get<PricingListResponse>("/api/admin/ai/pricing"),
  enabled: pricingOpen,
});

const upsertPricing = useMutation({
  mutationFn: (args: {
    model_name: string;
    input_per_million: number;
    output_per_million: number;
    cache_read_per_million: number | null;
    cache_write_per_million: number | null;
  }) =>
    api.put<PricingDbEntry>(`/api/admin/ai/pricing/${encodeURIComponent(args.model_name)}`, {
      input_per_million: args.input_per_million,
      output_per_million: args.output_per_million,
      cache_read_per_million: args.cache_read_per_million,
      cache_write_per_million: args.cache_write_per_million,
    }),
  onSuccess: () => {
    toast.success("Pricing saved");
    qc.invalidateQueries({ queryKey: ["admin", "ai", "pricing"] });
    qc.invalidateQueries({ queryKey: ["admin", "ai", "usage", "stats"] });
    setEditTarget(null);
  },
  onError: (e) =>
    toast.error(e instanceof Error ? e.message : "Pricing save failed"),
});

const deletePricing = useMutation({
  mutationFn: (model_name: string) =>
    api.delete(`/api/admin/ai/pricing/${encodeURIComponent(model_name)}`),
  onSuccess: () => {
    toast.success("Pricing deleted");
    qc.invalidateQueries({ queryKey: ["admin", "ai", "pricing"] });
    qc.invalidateQueries({ queryKey: ["admin", "ai", "usage", "stats"] });
  },
  onError: (e) =>
    toast.error(e instanceof Error ? e.message : "Pricing delete failed"),
});

const openEdit = (entry: PricingDbEntry | "new") => {
  setEditTarget(entry);
  if (entry === "new") {
    setEditName("");
    setEditInput("");
    setEditOutput("");
    setEditCacheRead("");
    setEditCacheWrite("");
  } else {
    setEditName(entry.model_name);
    setEditInput(String(entry.input_per_million));
    setEditOutput(String(entry.output_per_million));
    setEditCacheRead(entry.cache_read_per_million?.toString() ?? "");
    setEditCacheWrite(entry.cache_write_per_million?.toString() ?? "");
  }
};

const submitEdit = () => {
  if (!editName.trim()) {
    toast.error("Model name is required");
    return;
  }
  upsertPricing.mutate({
    model_name: editName.trim(),
    input_per_million: Number(editInput),
    output_per_million: Number(editOutput),
    cache_read_per_million: editCacheRead === "" ? null : Number(editCacheRead),
    cache_write_per_million: editCacheWrite === "" ? null : Number(editCacheWrite),
  });
};
```

Then add the pricing UI block at the end of the JSX (after the table's closing `</Card>`, before the final `</div>`):

```tsx
{/* Pricing management section */}
<Card>
  <CardHeader className="flex flex-row items-center justify-between pb-2">
    <CardTitle className="text-base">Model pricing</CardTitle>
    <Button
      size="sm"
      variant="outline"
      onClick={() => setPricingOpen((o) => !o)}
    >
      {pricingOpen ? "Hide" : "Manage"}
    </Button>
  </CardHeader>
  {pricingOpen && (
    <CardContent className="space-y-3">
      <div className="flex justify-end">
        <Button size="sm" onClick={() => openEdit("new")}>
          + Add custom pricing
        </Button>
      </div>
      {pricingQuery.isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {pricingQuery.data && (
        <>
          <div>
            <h4 className="font-medium text-sm mb-2">Custom (DB)</h4>
            {pricingQuery.data.db_entries.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No custom pricing rows.
              </p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left">
                    <th className="p-2">Model</th>
                    <th className="p-2 text-right">Input $/M</th>
                    <th className="p-2 text-right">Output $/M</th>
                    <th className="p-2 text-right">Cache read $/M</th>
                    <th className="p-2 text-right">Cache write $/M</th>
                    <th className="p-2" />
                  </tr>
                </thead>
                <tbody>
                  {pricingQuery.data.db_entries.map((e) => (
                    <tr key={e.model_name} className="border-b">
                      <td className="p-2 font-mono">{e.model_name}</td>
                      <td className="p-2 text-right tabular-nums">
                        {e.input_per_million.toFixed(2)}
                      </td>
                      <td className="p-2 text-right tabular-nums">
                        {e.output_per_million.toFixed(2)}
                      </td>
                      <td className="p-2 text-right tabular-nums">
                        {e.cache_read_per_million?.toFixed(2) ?? "—"}
                      </td>
                      <td className="p-2 text-right tabular-nums">
                        {e.cache_write_per_million?.toFixed(2) ?? "—"}
                      </td>
                      <td className="p-2 text-right space-x-1">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => openEdit(e)}
                        >
                          Edit
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => deletePricing.mutate(e.model_name)}
                          disabled={deletePricing.isPending}
                        >
                          Delete
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
          <div>
            <h4 className="font-medium text-sm mb-2 mt-4">Built-in (static)</h4>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left">
                  <th className="p-2">Model</th>
                  <th className="p-2 text-right">Input $/M</th>
                  <th className="p-2 text-right">Output $/M</th>
                </tr>
              </thead>
              <tbody>
                {pricingQuery.data.static_entries.map((e) => (
                  <tr key={e.model_name} className="border-b">
                    <td className="p-2 font-mono">{e.model_name}</td>
                    <td className="p-2 text-right tabular-nums">
                      {e.input_per_million.toFixed(2)}
                    </td>
                    <td className="p-2 text-right tabular-nums">
                      {e.output_per_million.toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </CardContent>
  )}
</Card>

{/* Pricing upsert dialog */}
<Dialog
  open={editTarget !== null}
  onOpenChange={(o) => !o && setEditTarget(null)}
>
  <DialogContent>
    <DialogHeader>
      <DialogTitle>
        {editTarget === "new" ? "Add custom pricing" : `Edit ${editName}`}
      </DialogTitle>
    </DialogHeader>
    <div className="space-y-3">
      <div className="space-y-1.5">
        <Label htmlFor="pricing_model_name">Model name</Label>
        <Input
          id="pricing_model_name"
          value={editName}
          onChange={(e) => setEditName(e.target.value)}
          disabled={editTarget !== "new"}
          placeholder="gpt-4.5-preview"
        />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="pricing_input">Input $/M</Label>
          <Input
            id="pricing_input"
            type="number"
            step="0.01"
            value={editInput}
            onChange={(e) => setEditInput(e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="pricing_output">Output $/M</Label>
          <Input
            id="pricing_output"
            type="number"
            step="0.01"
            value={editOutput}
            onChange={(e) => setEditOutput(e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="pricing_cache_read">Cache read $/M (optional)</Label>
          <Input
            id="pricing_cache_read"
            type="number"
            step="0.01"
            value={editCacheRead}
            onChange={(e) => setEditCacheRead(e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="pricing_cache_write">Cache write $/M (optional)</Label>
          <Input
            id="pricing_cache_write"
            type="number"
            step="0.01"
            value={editCacheWrite}
            onChange={(e) => setEditCacheWrite(e.target.value)}
          />
        </div>
      </div>
    </div>
    <DialogFooter>
      <Button variant="outline" onClick={() => setEditTarget(null)}>
        Cancel
      </Button>
      <Button onClick={submitEdit} disabled={upsertPricing.isPending}>
        {upsertPricing.isPending ? "Saving…" : "Save"}
      </Button>
    </DialogFooter>
  </DialogContent>
</Dialog>
```

Add the missing imports at the top of the file if not already present:
- `useMutation`, `useQueryClient` from `@tanstack/react-query`
- `toast` from `sonner`
- `Button` from `@/components/ui/button`
- `Dialog`, `DialogContent`, `DialogFooter`, `DialogHeader`, `DialogTitle` from `@/components/ui/dialog`

- [ ] **Step 2: Type-check + build**

```bash
cd admin-ui && npx tsc --noEmit && npm run build
```

Expected: both green.

- [ ] **Step 3: Commit**

```bash
cd ..
git add admin-ui/src/pages/AIUsagePage.tsx
git commit -m "feat(admin-ui): pricing management section on AI usage dashboard"
```

---

**End of Chunk 3.** Dashboard is feature-complete: stat cards, chart, filtered table, pricing CRUD.

---

## Chunk 4: Smoke test and merge

### Task 10: Write the smoke test checklist

**Files:**
- Create: `docs/admin-dashboard-phase4d-smoke-test.md` (at parent FlexLoop level)

- [ ] **Step 1: Write the checklist**

```markdown
# Phase 4d (AI Usage dashboard) smoke test

Manual checklist plus automated Playwright subset.

## Environment

- [ ] Backend running
- [ ] Admin UI built
- [ ] `ai_model` in `app_settings` is set to something in the static PRICING dict (e.g. `gpt-4o-mini`) for cost tests, OR to a custom model that has a `model_pricing` DB row
- [ ] At least one `ai_usage` row exists for the current month (seed via the smoke script)
- [ ] Logged in as admin

## Dashboard

- [ ] Navigate to /admin/ai/usage — page loads
- [ ] "Assumed model" badge shows the current `settings.ai_model`
- [ ] Four stat cards at the top show current-month totals (input, output, calls, estimated cost)
- [ ] Estimated cost shows either a dollar value or "—" (never a bare zero for unknown models)
- [ ] 12-month stacked bar chart renders with input (blue) + output (green) bars
- [ ] Zero-usage months appear as empty bars (flat line), not gaps

## Filter + table

- [ ] The table shows rows for the seeded usage data
- [ ] Clicking a column header toggles the sort direction (▲/▼ indicator updates)
- [ ] Filtering by month_from / month_to narrows the row set
- [ ] Filtering by user_id narrows the row set
- [ ] Invalid month format (e.g. "April 2026") returns all rows or a clean response (not a 500)

## Pricing management

- [ ] Click "Manage" on the Model pricing card — section expands
- [ ] Built-in (static) table shows the PRICING dict entries (gpt-4o-mini etc.)
- [ ] Custom (DB) table shows any model_pricing rows
- [ ] Click "+ Add custom pricing" — dialog opens
- [ ] Fill in model_name + input/output prices, click Save — toast "Pricing saved", row appears in the Custom table
- [ ] Click "Edit" on a custom row — dialog opens with values pre-filled, model name disabled
- [ ] Click "Delete" on a custom row — toast "Pricing deleted", row disappears
- [ ] Negative input/output values are rejected by the backend (422 surfaced as a toast error)

## Retroactive re-pricing

- [ ] Add a custom pricing row for the currently-configured ai_model with $1 input and $2 output
- [ ] Refresh the dashboard — stat cards' estimated cost and chart cost lines update to reflect the new pricing
- [ ] Delete the custom row — cost reverts to the static PRICING value

## Regression checks

- [ ] iOS-facing endpoints still work: `curl http://localhost:8000/api/plans?user_id=1`
- [ ] Phase 4c Playground still loads at /admin/ai/playground
- [ ] Phase 4b Prompts still loads at /admin/ai/prompts
- [ ] Phase 4a Config still loads at /admin/ai/config
- [ ] Phase 2's CRUD endpoints for ai_usage are still reachable (`curl -b cookies /api/admin/ai/usage`)

## Automated

- [ ] `uv run pytest -q` — full suite green (expected 437 tests)
- [ ] `cd admin-ui && npm run build` — succeeds
- [ ] Playwright smoke script at `/tmp/smoke_phase4d.py` — all checks green
```

- [ ] **Step 2: Commit to parent**

```bash
cd /Users/flyingchickens/Projects/FlexLoop
git add docs/admin-dashboard-phase4d-smoke-test.md
git commit -m "docs(admin): phase 4d smoke test checklist"
cd /Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase4d
```

---

### Task 11: Run the automated Playwright smoke

The smoke script should cover the visible UI + a seeded usage row to make the dashboard non-empty. The seed script creates: admin user, 1 test user, 2 ai_usage rows (current month + 3 months ago).

- [ ] **Step 1: Recreate or reuse the playwright venv**

```bash
if [ ! -x /tmp/phase4c-playwright-venv/bin/python3 ]; then
  python3 -m venv /tmp/phase4d-playwright-venv
  /tmp/phase4d-playwright-venv/bin/pip install playwright
  /tmp/phase4d-playwright-venv/bin/playwright install chromium
else
  ln -sf /tmp/phase4c-playwright-venv /tmp/phase4d-playwright-venv
fi
```

- [ ] **Step 2: Create `/tmp/seed_phase4d_smoke.py`** that creates the admin user + 1 user + 2 ai_usage rows (current month + 3 months ago).

- [ ] **Step 3: Create `/tmp/smoke_phase4d.py`** covering:
  1. Login
  2. Navigate to /ai/usage
  3. Verify page loads with "AI Usage" heading
  4. Verify four stat card titles are visible
  5. Verify the chart container renders (look for an SVG inside the chart card)
  6. Verify the table has rows
  7. Click the "Month" header to toggle sort
  8. Click "Manage" → pricing section expands
  9. Verify the Built-in table shows "gpt-4o-mini"
  10. Click "+ Add custom pricing" → dialog opens
  11. Fill in a test model + prices → Save → toast appears → new row in Custom table
  12. Click Delete on the new row → toast → row gone
  13. iOS regression check

- [ ] **Step 4: Run the smoke**

```bash
cd /Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase4d
rm -f /tmp/flexloop-phase4d-smoke.db
DATABASE_URL='sqlite+aiosqlite:////tmp/flexloop-phase4d-smoke.db' \
  uv run python /tmp/seed_phase4d_smoke.py
DATABASE_URL='sqlite+aiosqlite:////tmp/flexloop-phase4d-smoke.db' \
  python3 /Users/flyingchickens/.claude/plugins/cache/anthropic-agent-skills/example-skills/b0cbd3df1533/skills/webapp-testing/scripts/with_server.py \
  --server 'uv run uvicorn flexloop.main:app --port 8000' \
  --port 8000 --timeout 60 \
  -- /tmp/phase4d-playwright-venv/bin/python3 /tmp/smoke_phase4d.py
```

Expected: ALL SMOKE TESTS PASSED.

- [ ] **Step 5: Mark checklist as executed**

Prepend to `docs/admin-dashboard-phase4d-smoke-test.md`:

```markdown
> **Automated Playwright smoke executed 2026-MM-DD — all checks ✅.**
```

Commit the update to the parent FlexLoop repo.

---

### Task 12: Merge `feat/admin-dashboard-phase4d-usage-dashboard` to main

- [ ] **Step 1: Verify clean**

```bash
cd /Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase4d
git status
git log --oneline main..HEAD | wc -l
```

Expected: clean, ~12 commits.

- [ ] **Step 2: Fast-forward merge**

```bash
cd /Users/flyingchickens/Projects/FlexLoop/flexloop-server
git checkout main
git merge --ff-only feat/admin-dashboard-phase4d-usage-dashboard
```

- [ ] **Step 3: Full suite on main**

```bash
uv run pytest -q
```

Expected: 437 tests green.

- [ ] **Step 4: Push main**

```bash
git push origin main
```

- [ ] **Step 5: Bump parent submodule**

```bash
cd /Users/flyingchickens/Projects/FlexLoop
git add flexloop-server
git commit -m "chore: bump flexloop-server to admin dashboard phase 4d"
```

- [ ] **Step 6: Clean up worktree + feature branch**

```bash
cd /Users/flyingchickens/Projects/FlexLoop/flexloop-server
git worktree remove /Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase4d
git branch -d feat/admin-dashboard-phase4d-usage-dashboard
```

- [ ] **Step 7: Update memory status file**

Edit `/Users/flyingchickens/.claude/projects/-Users-flyingchickens-Projects-FlexLoop/memory/project_admin_dashboard_status.md`:
- Mark phase 4d COMPLETE → phase 4 (all sub-plans) COMPLETE
- Move phase 5 (Operations) into "next up"

---

**End of Chunk 4.** Plan 4d is shipped. The AI Usage dashboard replaces the phase 2 CRUD page with stat cards + 12-month chart + filterable table + pricing management.

---

## Summary

**Backend deliverables:**
- `src/flexloop/admin/pricing.py` — `PRICING` static dict + `ModelPricingValues` dataclass + `get_model_pricing` DB-first lookup + `compute_cost` helper
- `src/flexloop/admin/routers/ai_dashboard.py` — 4 endpoints (stats + pricing list/upsert/delete)
- `src/flexloop/main.py` — register router
- 2 test files (~22 tests): `test_admin_pricing.py` (13 unit), `test_admin_ai_dashboard.py` (20 integration)

**Frontend deliverables:**
- `admin-ui/src/components/ui/chart.tsx` — shadcn-generated recharts wrapper
- `admin-ui/src/pages/AIUsagePage.tsx` — rewritten dashboard with stat cards + Recharts stacked bar chart + filterable sortable table + expandable pricing management section with upsert/delete dialog
- `admin-ui/src/components/forms/AIUsageForm.tsx` — DELETED (no longer referenced)
- `admin-ui/package.json` — `recharts` added transitively via shadcn

**Docs:** `docs/admin-dashboard-phase4d-smoke-test.md`

**End state:** operators can see "how much did this month cost" in one glance, watch the 12-month token trend, drill into per-user-per-month rows with filters and sorting, and manage custom pricing for models not in the static dict. Phase 4 is complete (4a config + 4b prompts + 4c playground + 4d usage dashboard) — phase 5 (Operations: backup, logs, triggers) is the only remaining phase.
