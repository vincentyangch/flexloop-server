> **Automated Playwright smoke executed 2026-04-08 — all checks ✅.**

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
- [ ] Built-in (static) table shows the PRICING dict entries (`gpt-4o-mini` etc.)
- [ ] Custom (DB) table shows any `model_pricing` rows
- [ ] Click "+ Add custom pricing" — dialog opens
- [ ] Fill in `model_name` + input/output prices, click Save — toast "Pricing saved", row appears in the Custom table
- [ ] Click "Edit" on a custom row — dialog opens with values pre-filled, model name disabled
- [ ] Click "Delete" on a custom row — toast "Pricing deleted", row disappears
- [ ] Negative input/output values are rejected by the backend (422 surfaced as a toast error)

## Retroactive re-pricing

- [ ] Add a custom pricing row for the currently-configured `ai_model` with $1 input and $2 output
- [ ] Refresh the dashboard — stat cards' estimated cost and chart cost lines update to reflect the new pricing
- [ ] Delete the custom row — cost reverts to the static PRICING value

## Regression checks

- [ ] iOS-facing endpoints still work: `curl http://localhost:8000/api/plans?user_id=1`
- [ ] Phase 4c Playground still loads at /admin/ai/playground
- [ ] Phase 4b Prompts still loads at /admin/ai/prompts
- [ ] Phase 4a Config still loads at /admin/ai/config
- [ ] Phase 2's CRUD endpoints for `ai_usage` are still reachable (`curl -b cookies /api/admin/ai/usage`)

## Automated

- [ ] `uv run pytest -q` — full suite green (expected 437 tests)
- [ ] `cd admin-ui && npm run build` — succeeds
- [ ] Playwright smoke script at `/tmp/smoke_phase4d.py` — all checks green
