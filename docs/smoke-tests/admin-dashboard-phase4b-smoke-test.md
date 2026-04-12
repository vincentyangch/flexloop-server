# Phase 4b (Prompt editor) smoke test

> **Automated Playwright smoke executed 2026-04-08 — all checks ✅.** Script at
> `/tmp/smoke_phase4b.py` (headless chromium) covers: login, prompts page,
> auto-select first alphabetical prompt, navigate tree to select a different
> prompt + version, editor loads content, variable inspector lists extracted
> variables, edit → unsaved indicator → Save → indicator clears + disk
> persistence verified, New version clones active + auto-selects the new
> version + v3.md exists on disk, Set as active updates manifest.json on
> disk, Diff dialog opens with colored output and closes, iOS regression
> `GET /api/plans?user_id=1`. The manual checklist below remains the
> definitive acceptance spec.

Manual checklist plus automated Playwright subset.

## Environment setup

- [ ] Backend running: `uv run uvicorn flexloop.main:app --port 8000`
- [ ] Admin UI built: `cd admin-ui && npm run build`
- [ ] `prompts/` directory has at least 2 prompts with at least 1 version each (the real repo has `plan_generation` with v1+v2, `chat`/`block_review`/`session_review`/`plan_refinement` with v1 each)
- [ ] Logged in as admin

## Prompts page

- [ ] Navigate to /admin/ai/prompts — sidebar item enabled, page loads
- [ ] Left tree shows all prompts, expandable via the `▸/▾` chevron
- [ ] Clicking a prompt expands to show versions with a green dot on the active-default version
- [ ] Selecting a version loads its content in the CodeMirror editor on the right
- [ ] Markdown syntax highlighting visible (headings, `{{variables}}`, bold, etc.)
- [ ] Editing the buffer shows the "• unsaved" indicator next to the version header
- [ ] Variables sidebar (right column) updates live as you type `{{foo}}` or `{{user_name}}`

## Save flow

- [ ] Click Save with a dirty buffer — toast "Saved", indicator clears
- [ ] Refresh the page — the saved content persists
- [ ] Save is disabled when the buffer is clean

## Critical: buffer-sync race fix

- [ ] Load a version, type some edits (don't save)
- [ ] Switch to another browser tab for >30 seconds, then switch back
- [ ] Your unsaved edits should STILL BE PRESENT (the buffer-sync ref guard prevents background refetch from wiping them)

## New version (clone active)

- [ ] Click "New version" on a prompt with 2 versions — toast "Created v3"
- [ ] Left tree auto-expands and shows the new v3
- [ ] Selected version auto-switches to v3
- [ ] v3's content matches the previously-active version's content

## Set as active

- [ ] Select a non-active version (no green dot)
- [ ] Click "Set as active" — toast, tree's green dot moves
- [ ] The "Set as active" button becomes disabled (since the version is now already active)
- [ ] `cat prompts/manifest.json` — the `default` field for this prompt shows the new active version

## Diff view

- [ ] Click "Diff…" on a prompt with 2+ versions — modal opens
- [ ] Compare-against dropdown lists all other versions
- [ ] Diff text renders with per-line coloring: `+` green, `-` red, `@@` blue
- [ ] Close button dismisses the modal
- [ ] On a prompt with only ONE version, clicking Diff shows "No other versions to compare against."

## Delete (via direct API — no UI button in phase 4b scope)

- [ ] `curl -X DELETE -b cookies.txt -H "Origin: http://localhost:5173" http://localhost:8000/api/admin/prompts/plan_generation/versions/v1` returns 204 for a non-active version
- [ ] Returns 409 for the active version (message contains "still active")
- [ ] Returns 409 for the last remaining version (message contains "last version")

## Path traversal security

- [ ] `curl http://localhost:8000/api/admin/prompts/..%2Fetc%2Fpasswd/versions/v1` returns 400 (invalid name)
- [ ] `curl http://localhost:8000/api/admin/prompts/plan_generation/versions/..%2F..%2Fetc%2Fpasswd` returns 400 (invalid version)

## Regression checks

- [ ] iOS-facing endpoints still work: `curl http://localhost:8000/api/plans?user_id=1`
- [ ] Phase 4a Config page still loads at /admin/ai/config
- [ ] Existing `PromptManager` still reads from the same filesystem — triggering a plan generation via `/api/plans/generate` should use the current active version

## Automated

- [ ] `uv run pytest -q` — full suite green (expected 383 tests)
- [ ] `cd admin-ui && npm run build` — succeeds
- [ ] Playwright smoke script at `/tmp/smoke_phase4b.py` — all checks green
