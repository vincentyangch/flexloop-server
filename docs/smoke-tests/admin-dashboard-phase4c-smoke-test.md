# Phase 4c (AI Playground) smoke test

> **Automated Playwright smoke executed 2026-04-08 — all checks ✅.** Script at
> `/tmp/smoke_phase4c.py` (headless chromium) covers: login, page loads, both
> panels render, Send disabled when empty, Send enabled after typing, mode
> toggle to template, template dropdown lists prompts, variable form renders,
> filling variables triggers a render that updates the user prompt textarea
> with the rendered content, navigating from /ai/prompts via "Open in
> playground →" deep link with `?template=` query param, auto-selects
> template mode, iOS-facing `GET /api/plans?user_id=1` regression. The
> manual checklist below remains the definitive acceptance spec.
>
> Note: the headless test does NOT click Send (would hit a real AI provider).
> SSE streaming is covered by the pytest integration tests with monkeypatched
> `create_adapter`.

Manual checklist plus automated Playwright subset.

## Environment setup

- [ ] Backend running: `uv run uvicorn flexloop.main:app --port 8000`
- [ ] Admin UI built: `cd admin-ui && npm run build`
- [ ] At least 2 prompts in `prompts/` (the smoke script uses scratch prompts via `PROMPTS_DIR`)
- [ ] Logged in as admin

## Playground page — free-form mode

- [ ] Navigate to /admin/ai/playground — sidebar item enabled, page loads
- [ ] Two panels visible: input on the left, output on the right
- [ ] System/user textareas present, "Send" button disabled while user prompt is empty
- [ ] Fill in a user prompt, click Send → "streaming…" badge appears, content accumulates in the output pre
- [ ] Token counts (input, output, cache_read) + latency_ms appear in the Usage card after the stream finishes
- [ ] "streaming…" badge disappears after the `done` event

## Try parse as JSON

- [ ] With a response that is NOT valid JSON, toggle "Try parse as JSON" on → parse error appears in red box
- [ ] With a response that IS valid JSON (e.g. `{"hello": "world"}`), the parse result shows formatted `<pre>`
- [ ] Toggle off → JSON view disappears

## Error handling

- [ ] With a garbage provider override, click Send → output shows the error message in a red banner without a 500 page
- [ ] Each subsequent Send clears the previous output before streaming the new response

## Template mode

- [ ] Toggle to "From template" mode
- [ ] Template card appears between Prompt and Advanced cards
- [ ] Template dropdown lists all prompts with their active version in parentheses (e.g. "plan_generation (v2)")
- [ ] Selecting a template populates the variable form
- [ ] Filling in variables triggers a server render and updates the user_prompt textarea with the rendered content
- [ ] Click Send → the rendered content is what gets sent (not the raw template)

## Open in playground (cross-link)

- [ ] From /admin/ai/prompts, select a prompt, click "Open in playground →" — navigates to /admin/ai/playground?template=<name>
- [ ] Playground auto-selects template mode with the pre-picked template
- [ ] Variable form renders, render preview populates on empty vars

## Path traversal security

- [ ] `curl -X POST -b cookies.txt -H "Origin: http://localhost:5173" -H "Content-Type: application/json" -d '{"template_name":"..%2Fetc%2Fpasswd","variables":{}}' http://localhost:8000/api/admin/playground/render` returns 400

## Regression checks

- [ ] iOS-facing endpoints still work: `curl http://localhost:8000/api/plans?user_id=1`
- [ ] Phase 4b Prompts page still loads at /admin/ai/prompts
- [ ] Phase 4a Config page still loads at /admin/ai/config

## Automated

- [ ] `uv run pytest -q` — full suite green (expected 404 tests)
- [ ] `cd admin-ui && npm run build` — succeeds
- [ ] Playwright smoke script at `/tmp/smoke_phase4c.py` — all checks green
