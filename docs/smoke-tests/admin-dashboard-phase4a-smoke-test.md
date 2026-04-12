# Phase 4a (Config editor + audit log) smoke test

> **Automated Playwright smoke executed 2026-04-08 — all checks ✅.** Script at
> `/tmp/smoke_phase4a.py` (headless chromium) covers: login, config page load,
> masked API key pre-populate, Reveal/Hide toggle, Rotate clears field, change
> temperature + save + reload + verify persistence, Test connection button
> produces OK/Error badge, stale test-result clears after save, and iOS-facing
> `GET /api/plans?user_id=1` regression check. Audit log entries were verified
> via direct SQLite query — both before_json and after_json contain the config
> snapshot with `ai_api_key` masked (bullet chars + last 3 chars), never
> plaintext. The manual checklist below remains the definitive acceptance spec.

Manual checklist plus automated subset via Playwright.

## Environment setup

- [ ] Backend running: `uv run uvicorn flexloop.main:app --port 8000`
- [ ] Admin UI built: `cd admin-ui && npm run build`
- [ ] Seed migration has run (verify: `sqlite3 flexloop.db "SELECT COUNT(*) FROM app_settings"` returns 1)
- [ ] Logged in as admin at http://localhost:8000/admin

## Config page

- [ ] Navigate to /admin/ai/config — sidebar item enabled, page loads
- [ ] Page shows "Config" header + "Test connection" card + sectioned form
- [ ] Form pre-populates with current settings (ai_provider, ai_model, etc.)
- [ ] ai_api_key field shows masked value (bullets + last 3 chars), not plaintext
- [ ] Click "Reveal" — field becomes type=text and shows whatever is currently in the input; click "Hide" — reverts
- [ ] Click "Rotate" — field clears to empty AND focus moves into the input
- [ ] Type a new value in the API key field, click Save — toast "Config saved"
- [ ] Re-fetch (refresh page): ai_api_key is masked again. Verify DB via SQLite: the plaintext is actually stored.
- [ ] Leave the masked key as-is (don't touch it), change ai_provider only, Save — DB still has the original plaintext (masked roundtrip doesn't overwrite)
- [ ] After save, form re-populates with server-confirmed values (no stale edit state leaked)

## Test connection

- [ ] Click "Test connection" with a valid API key — shows "OK" badge + latency + response preview (e.g. "Hello")
- [ ] Set ai_api_key to a garbage value (temporarily), Save, then Test connection — shows "Error" badge + latency + error message
- [ ] Test connection with `provider="unknown_xyz"` — shows "Error" badge + error message containing "Unknown provider"
- [ ] After a successful save, any previous test-connection result is cleared from the card
- [ ] (Don't forget to restore the real key)

## Audit log

- [ ] Make a config change via the UI
- [ ] Query DB: `sqlite3 flexloop.db "SELECT action, target_type, target_id, before_json, after_json FROM admin_audit_log ORDER BY id DESC LIMIT 1"`
- [ ] Verify: action="config_update", target_type="app_settings", target_id="1", before_json and after_json both contain the full config snapshot, api_key is masked (not plaintext) in both
- [ ] Submit a PUT with values identical to the current config — no new audit log row appears

## CSRF hot-reload

- [ ] Add a new origin to "Allowed Origins" (CSV), Save
- [ ] From another browser/curl with that new Origin header, hit a protected endpoint — should succeed (was previously rejected)
- [ ] Remove the new origin, Save — subsequent requests with that Origin should 403

## Regression checks

- [ ] iOS-facing endpoints still work: `curl http://localhost:8000/api/plans?user_id=1`
- [ ] Phase 3 Plans page still loads at /admin/plans
- [ ] Phase 2 Workouts page still loads

## Automated

- [ ] `uv run pytest -q` — full suite green (expected 323 tests)
- [ ] `cd admin-ui && npm run build` — succeeds
- [ ] Playwright smoke script at `/tmp/smoke_phase4a.py` — all checks green
