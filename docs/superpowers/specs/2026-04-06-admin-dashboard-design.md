# FlexLoop Admin Dashboard — Design

**Date:** 2026-04-06
**Status:** Draft (pending user + reviewer approval)
**Author:** Brainstormed with Claude (Opus 4.6)

## 1. Context

FlexLoop is split across an iOS app, an Apple Watch companion, and a FastAPI backend (`flexloop-server`). The backend currently has no UI surface — all configuration lives in `.env`, all data lives in SQLite, and the only ways to inspect or modify state are direct DB access, ad-hoc Python scripts, or restarting the server with a different `.env`.

This has caused real friction:

- The recent "AI returned invalid plan format" bug took ~30 minutes to diagnose because there was no way to send a test prompt to the configured AI provider and inspect the raw response. (Root cause: an OpenAI-compatible proxy stripped `message.content` from non-streaming responses — see the related fix in `flexloop-server/src/flexloop/ai/openai_adapter.py`.)
- Editing prompts requires SSHing into the server to edit `.md` files, then restarting.
- Inspecting per-user data requires SQL.
- There is no visibility into AI token usage, server health, or recent activity.

The admin dashboard is a web UI that gives the operator (currently a single developer, designed to be VPS-deployable) the ability to configure the backend and manage data without leaving the browser.

## 2. Goals

- **Single-pane operator console** — config, data, AI, ops all in one place
- **Self-debugging features** — AI playground, log viewer, health page exist specifically to make the next "weird bug" easy to investigate
- **Local-first, VPS-ready** — works on `localhost` for daily dev, deploys behind a reverse proxy on a personal VPS without architectural changes
- **Polished web UI** — invest in a real React app, not a server-rendered admin scaffold, because it will be used regularly
- **Phased delivery** — every phase ends with a deployable, useful tool

## 3. Non-Goals (v1)

These are deliberately excluded to keep scope tight:

- Multi-user / role-based access control (single admin only)
- Password reset via email (re-run the bootstrap CLI if you forget)
- 2FA, rate limiting, captcha (single user on a private VPS)
- Audit log for all admin actions (config changes only in v1; can extend later)
- E2E browser tests (Playwright is overkill for an internal tool — manual smoke testing is fine)
- Prompts migrated to the database (kept on disk to preserve git history)
- Soft-delete columns across the existing data model
- Bulk operations beyond the obvious cases
- Localization (English only)
- Custom theming beyond shadcn/ui defaults

## 4. Architecture

### 4.1 Single FastAPI process, three concerns

The existing `flexloop-server` FastAPI process gains two new concerns alongside the existing iOS-facing API:

| Path prefix | Served by | Notes |
|---|---|---|
| `/api/*` | Existing routers | Unchanged |
| `/api/admin/*` | New `flexloop.admin` module | Protected by session middleware |
| `/admin/*` | `StaticFiles` mount | Built SPA bundle with SPA fallback so client-side routing works |

The admin module lives **inside** the existing server package at `src/flexloop/admin/`. Rationale: it needs the same DB engine, the same models, the same settings singleton, and the same logging infrastructure. Splitting it into a separate package would only create import gymnastics for no isolation benefit.

### 4.2 Repository layout

The SPA lives **inside `flexloop-server/`** as a sibling to `src/`:

```
flexloop-server/
├── src/flexloop/
│   ├── admin/                    NEW — admin routers, services, schemas
│   │   ├── __init__.py
│   │   ├── auth.py               login, logout, session middleware
│   │   ├── crud.py               generic CRUD helpers (paginated_response, etc.)
│   │   ├── routers/              one router per resource
│   │   │   ├── users.py
│   │   │   ├── plans.py
│   │   │   ├── workouts.py
│   │   │   ├── exercises.py
│   │   │   ├── measurements.py
│   │   │   ├── prs.py
│   │   │   ├── ai_usage.py
│   │   │   ├── config.py
│   │   │   ├── prompts.py
│   │   │   ├── playground.py
│   │   │   ├── backup.py
│   │   │   ├── health.py
│   │   │   ├── logs.py
│   │   │   └── triggers.py
│   │   ├── audit.py              admin_audit_log helpers
│   │   ├── log_handler.py        ring buffer + rotating JSONL handler
│   │   ├── pricing.py            model pricing constants
│   │   └── bootstrap.py          CLI: create-admin, reset-admin-password
│   ├── static/admin/             NEW — built SPA bundle (gitignored)
│   ├── models/
│   │   ├── admin_user.py         NEW
│   │   ├── admin_session.py      NEW
│   │   ├── admin_audit_log.py    NEW
│   │   ├── app_settings.py       NEW
│   │   └── model_pricing.py      NEW (per-model AI cost overrides, see §10.4)
│   └── main.py                   updated to mount admin router + static
├── admin-ui/                     NEW — Vite + React SPA project
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── routes/
│       ├── components/
│       ├── hooks/
│       ├── lib/
│       │   ├── api.ts            generated TS types from FastAPI's OpenAPI
│       │   └── query.ts          TanStack Query setup
│       └── pages/                one per sidebar item
├── alembic/versions/
│   └── <new>_admin_dashboard.py  migration for new tables
└── pyproject.toml                add `bcrypt`, `python-multipart` deps
```

### 4.3 Dev workflow

Two terminals during development:

1. **Backend**: `uv run uvicorn flexloop.main:app --reload --port 8000` (existing)
2. **Frontend**: `cd admin-ui && npm run dev` — Vite dev server on port 5173, with `vite.config.ts` proxying `/api/*` to `localhost:8000`

You hit `localhost:5173/admin` and get hot reload during development. API requests are same-origin from the frontend's perspective (Vite proxies them).

### 4.4 Production workflow

Build the SPA, then run uvicorn:

```bash
cd flexloop-server/admin-ui && npm ci && npm run build
# Vite outputs to ../src/flexloop/static/admin/

cd flexloop-server
uv run uvicorn flexloop.main:app --host 0.0.0.0 --port 8000
```

A reverse proxy in front (Caddy recommended for auto-TLS — single config file vs nginx's three) handles HTTPS and forwards to uvicorn. Sample Caddyfile is included in the implementation phase.

### 4.5 Generated types

`openapi-typescript` runs as a frontend build step (`npm run codegen`) that fetches `http://localhost:8000/openapi.json` and writes `admin-ui/src/lib/api.ts` with TypeScript types matching all Pydantic schemas. This is the only thing that keeps the frontend in sync with backend changes — no hand-maintained DTOs.

## 5. Auth & user model

### 5.1 New tables

```python
class AdminUser:
    id: int                    # PK
    username: str              # unique
    password_hash: str         # bcrypt
    created_at: datetime
    last_login_at: datetime | None
    is_active: bool            # default True

class AdminSession:
    id: str                    # PK; opaque random 32-byte hex; also the cookie value
    admin_user_id: int         # FK → admin_users.id, ON DELETE CASCADE
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    user_agent: str | None
    ip_address: str | None
```

These are **separate from the existing `User` table**, which represents FlexLoop end-user profile data and has no concept of login.

### 5.2 Bootstrapping the first admin

```bash
uv run python -m flexloop.admin.bootstrap create-admin <username>
```

The CLI prompts for a password, bcrypt-hashes it, and inserts a row. There is no way to create the first admin from the UI (chicken-and-egg). Subsequent admins can be created from the dashboard.

If you forget the password:

```bash
uv run python -m flexloop.admin.bootstrap reset-admin-password <username>
```

### 5.3 Login flow

1. SPA POSTs `/api/admin/auth/login` with `{username, password}`
2. Server bcrypt-verifies, creates an `AdminSession` row, sets cookie:
   `flexloop_admin_session=<token>; HttpOnly; Secure; SameSite=Strict; Max-Age=1209600` (14 days, rolling)
3. SPA receives `{ok: true, username, expires_at}` and navigates to `/admin`
4. All subsequent requests include the cookie automatically

**"Rolling" defined**: every authenticated request bumps both `last_seen_at` and `expires_at` to `now() + 14 days`. The cookie itself is also re-issued with a refreshed `Max-Age`. So a session stays alive as long as you use it at least once every 14 days; after 14 days of idle it's expired and the next request gets 401.

**Token shape**: the cookie value is an opaque random 32-byte hex string (`secrets.token_hex(32)`) used as the primary key of the `admin_sessions` row. There is no signing — the lookup is the validation. This means stealing the cookie is equivalent to stealing the session, and revoking is just deleting the row.

### 5.4 Auth dependency

```python
async def require_admin(request, db) -> AdminUser:
    token = request.cookies.get("flexloop_admin_session")
    # lookup, check expiry, bump last_seen_at, return user or 401
```

Used by every admin endpoint via FastAPI's `Depends`.

### 5.5 CSRF

Belt-and-braces:
- `SameSite=Strict` cookie prevents most CSRF (cross-site requests don't send the cookie)
- Plus an `Origin` header check on POST/PUT/PATCH/DELETE — must match an entry in a configured **allowed-origins list**

The allowed-origins list is a new setting `admin_allowed_origins` in `app_settings` (see §10.1) — it's a list because dev and prod have different values. Defaults: `["http://localhost:5173", "http://localhost:8000"]` for fresh installs; production deployments add their public domain (e.g., `https://flexloop.example.com`) via the config editor after first login.

### 5.6 Auth endpoints

```
POST   /api/admin/auth/login              public — returns 200 + session cookie or 401
POST   /api/admin/auth/logout             auth required — deletes session row, clears cookie
GET    /api/admin/auth/me                 returns {username, expires_at} or 401
POST   /api/admin/auth/change-password    auth required — needs current password
GET    /api/admin/auth/sessions           list active sessions for current user
DELETE /api/admin/auth/sessions/{id}      revoke a specific session ("log out everywhere" feature)
```

### 5.7 UI

- `/admin/login` — single-card form, username + password, no signup link
- `/admin/*` — protected by an `<AuthGate>` component that calls `/api/admin/auth/me` on mount; on 401, redirect to `/admin/login`
- Settings page in the sidebar has "Change password" + "Active sessions" subsections

## 6. Frontend stack

| Layer | Choice | Notes |
|---|---|---|
| Build tool | Vite | |
| Framework | React 18+ | |
| Language | TypeScript | |
| Styling | Tailwind CSS | shadcn/ui prerequisite |
| Components | shadcn/ui (Radix primitives + Tailwind) | Copy-paste components, not a library import |
| Server state | TanStack Query | Caching, refetch, invalidation |
| Forms | react-hook-form + zod | |
| Routing | React Router v6+ | |
| Code editor | CodeMirror 6 | For prompt editor — markdown + Jinja syntax |
| Charts | Recharts (via shadcn/ui Chart) | For AI usage |
| Virtualized lists | react-virtuoso | For log viewer |
| Generated types | openapi-typescript | From FastAPI's `/openapi.json` |

**Why this stack** is captured in the brainstorming session. The short version: shadcn/ui's component set is purpose-built for admin dashboards (DataTable, Form, Dialog, Sheet, Sidebar, Command palette), TanStack Query eliminates a category of cache-invalidation bugs, and React has the best LLM tooling support.

## 7. Navigation IA

Workflow-grouped sidebar (shadcn/ui Sidebar component):

```
FlexLoop Admin
─────────────────────
Dashboard

USER DATA
  Users
  Plans
  Workouts
  Measurements
  Personal Records

CATALOG
  Exercises

AI
  Config
  Prompts
  Playground
  Usage

OPERATIONS
  Backup & Restore
  Logs
  Triggers
─────────────────────
[user menu]
```

Top bar above the main content: breadcrumb + light/dark toggle + user menu (change password, log out).

## 8. Dashboard landing page

Health-first layout — the operator's most common reason to visit is "is anything broken?":

1. **Top**: large system-health card with overall status pill, uptime, DB size, AI provider status, last backup, migrations-up-to-date — all at a glance
2. **Middle**: 4-card stat row: total users, total workouts, this month's tokens, active plans
3. **Bottom**: recent activity feed (last 10 events: plans generated, workouts logged, PRs detected, plans refined, etc.)

Refreshes every 30 seconds via TanStack Query's `refetchInterval`.

## 9. Data CRUD strategy

### 9.1 Standard pattern (90% of resources)

Every "boring" resource (Users, Workouts, Measurements, PRs, Exercises, AdminUsers) gets the same shape.

**Backend** — five endpoints per resource:

```
GET    /api/admin/{resource}              list with pagination/filter/sort/search
GET    /api/admin/{resource}/{id}         detail
POST   /api/admin/{resource}              create
PUT    /api/admin/{resource}/{id}         update
DELETE /api/admin/{resource}/{id}         delete (cascades to children via existing FKs)
```

Standard query params on lists:
- `page=1` (1-indexed), `per_page=50` (default 50, max 200)
- `search=foo` — substring on a per-resource set of indexable columns
- `sort=created_at:desc,name:asc` — comma-separated ordered sort spec
- `filter[user_id]=4` — resource-specific whitelist of filterable columns

Standard response shape:

```json
{
  "items": [...],
  "total": 128,
  "page": 1,
  "per_page": 50,
  "total_pages": 3
}
```

A reusable helper `admin_paginated_response(query, params, schema)` in `flexloop.admin.crud` collapses the boilerplate to ~3 lines per list endpoint.

**Frontend** — every page is built from one shared hook plus shadcn/ui components:

```typescript
const { items, total, isLoading } = useList('users', { page, search, sort });
const { mutate: create } = useCreate('users');
const { mutate: update } = useUpdate('users');
const { mutate: del } = useDelete('users');
```

`useList/useDetail/useCreate/useUpdate/useDelete` are thin wrappers over TanStack Query that handle cache invalidation automatically. Each resource page is `<DataTable>` (shadcn/ui) + `<EditSheet>` (slide-out form drawer) + `<DeleteDialog>` (confirm).

Forms are **not** auto-generated. Each resource gets a hand-written `react-hook-form` + zod component because the existing models have type quirks (`available_equipment` is a JSON list, `goals` is free text, `setsJson` is nested) that auto-generators handle poorly. Roughly 30-50 lines per resource form.

**Hard delete with confirmation** — no soft-delete column proliferation. The Delete button shows an `<AlertDialog>` with a contextual message:

> "Delete workout from 2026-04-05? This will also delete 24 sets. This cannot be undone."

If you delete something by accident, restore from a backup.

### 9.2 Filter affordances (resource-specific)

Worth flagging because they're not all obvious:

| Resource | Filters |
|---|---|
| Workouts | user, date range, **completed/in-progress** (uses existing `completed_at IS NULL` to find sessions that started but never finished) |
| Plans | user, status (active/inactive/archived) |
| PRs | user, exercise |
| AI Usage | month, user |
| Exercises | muscle group, equipment |

(Note: an earlier draft proposed a "synced/unsynced" filter for workouts. That doesn't map to anything server-side — `WorkoutSession` has no `synced` column because unsynced workouts only exist in the iOS app's SwiftData cache, never on the server. "Completed/in-progress" is the closest server-side analogue and uses the existing `completed_at` column without a schema change.)

These are all the standard `filter[...]=` query param on the list endpoint, just with a per-resource whitelist on the backend.

### 9.3 The Plan editor (special case)

`Plan → PlanDay → ExerciseGroup → PlanExercise → sets_json` is too deep for standard CRUD. Three approaches were considered (multi-page navigation, single huge form, hybrid with per-day accordions). The hybrid wins:

**Plan detail page layout**:

```
┌─────────────────────────────────────────────────────────────┐
│ Plan: "Upper / Lower" — Active                               │
│ ─────────────────────────────────────────────────────────── │
│ [Plan metadata form: name, split type, cycle length, status] │
│                                          [Save plan metadata]│
│                                                              │
│ Days                                                         │
│ [v] Day 1 — Upper A — chest, back, shoulders, biceps, tris   │
│     [+ Add exercise group]                                   │
│     Group 1 — straight, rest 120s, order 1            [del]  │
│       Bench Press · 4 sets · 8 reps · RPE 7.5  [edit] [del]  │
│         Set targets grid (inline editable):                  │
│         # | Weight | Reps | RPE                              │
│         1 |   105  |   8  |  7                               │
│         2 |   105  |   8  |  7.5                             │
│         3 |   105  |   8  |  8                               │
│         4 |   105  |   8  |  8.5                             │
│       Overhead Press · 3 sets · 6 reps         [edit] [del]  │
│                                  [+ Add exercise to group]  │
│ [>] Day 2 — Lower A — quads, hamstrings, glutes, calves      │
│ [>] Day 3 — Upper B                                          │
│ [>] Day 4 — Lower B                                          │
│                                                  [+ Add day] │
└─────────────────────────────────────────────────────────────┘
```

**Save semantics**: each day is an atomic save unit. The plan metadata at the top has its own save button. There is **no "save the entire plan" button** — too risky and too easy to lose 30 minutes of edits to a network blip.

**Endpoints beyond the standard five for plans**:

```
POST   /api/admin/plans/{id}/days                    add a new day
PUT    /api/admin/plans/{id}/days/{day_number}       update an entire day (groups + exercises + sets)
DELETE /api/admin/plans/{id}/days/{day_number}       delete a day
```

Days are atomic — the day endpoint takes the full nested day payload and replaces everything within that day. This avoids needing five endpoints per nesting level (groups, exercises, sets).

### 9.4 JSON escape hatch

Every detail page (not just plans) has an **"Advanced → Edit JSON"** tab that lets you edit the raw JSON representation of the resource using `@uiw/react-json-view` (or CodeMirror with JSON syntax). The tab POSTs the parsed JSON to the **same `PUT` endpoint** as the form, which means it goes through the **same Pydantic validation** — there's no "raw bypass" mode that skips validation. If your edit is structurally invalid, the request 422s with the same error messages a form submit would have produced.

This is the feature that lets you patch a mangled AI-generated plan in 30 seconds when the form UI doesn't represent the bad data correctly.

## 10. AI features

### 10.1 Config editor

**Split between `.env` and DB-backed settings**:

| Lives in `.env` (deployment, can't change at runtime) | Lives in `app_settings` table (runtime mutable) |
|---|---|
| `database_url` | `ai_provider` |
| `host`, `port` | `ai_model` |
| | `ai_api_key` |
| | `ai_base_url` |
| | `ai_temperature` |
| | `ai_max_tokens` |
| | `ai_review_frequency` |
| | `ai_review_block_weeks` |
| | `admin_allowed_origins` (JSON list, see §5.5) |

(There is no `admin_session_secret` in `.env` — sessions use opaque DB-keyed tokens, not signed cookies, so no signing key is needed.)

Why: the left column has to be readable *before* the DB is available (you need them to connect to the DB). Everything else can be runtime-mutable.

**Migration path**:

1. New `app_settings` table — single row, one column per setting (typed schema, not key-value)
2. Alembic migration creates the table and **seeds it from current `.env` values** so existing deployments don't reset to defaults
3. `flexloop.config.Settings.__init__` reads from DB at startup, falls back to `.env` defaults if the row is missing
4. Existing call sites (`from flexloop.config import settings; settings.ai_provider`) continue to work unchanged
5. `PUT /api/admin/config` updates the DB row AND refreshes the in-memory singleton in one transaction

**UI**:

- One form, sectioned by logical group ("AI Provider", "Generation Defaults", "Review Schedule")
- API key field is masked (`sk-***xyz`) with a "Reveal" toggle and a separate "Rotate" button
- After save, the cleartext key is never returned to the frontend again
- "**Test connection**" button at the top — fires a tiny round-trip via the playground backend ("Say hello in one word") and shows latency / status / first 200 chars of response
- "Save" persists; success toast confirms

**Audit**: every config change writes a row to `admin_audit_log` with `(timestamp, admin_user_id, action, target_type, target_id, before, after)`. Just for config changes in v1; can extend to other writes later.

### 10.2 Prompt editor

**Storage decision: keep prompts as `.md` files on disk** (not migrated to DB).

Reasoning:
- Existing `PromptManager` works unchanged
- Git history of prompt evolution is preserved
- The file structure remains the source of truth

Cost: requires writable filesystem on the server. If Docker-deploying with a read-only volume becomes a constraint, this can be revisited.

**Backend endpoints**:

```
GET    /api/admin/prompts                                       list all prompts and versions
GET    /api/admin/prompts/{name}/versions/{version}             raw .md content
PUT    /api/admin/prompts/{name}/versions/{version}             save .md content
POST   /api/admin/prompts/{name}/versions                       create a new version (clones current default)
PUT    /api/admin/prompts/{name}/active                         set the active version (updates manifest.json)
GET    /api/admin/prompts/{name}/diff?from=v1&to=v2             unified diff
DELETE /api/admin/prompts/{name}/versions/{version}             delete (block if it's the active one)
```

All write endpoints use `fcntl.flock` to prevent concurrent edits clobbering each other. (Linux/macOS only — FlexLoop's deployment target is Linux VPS, so portability to Windows is explicitly not a concern.)

**UI**:

- Left panel: tree view of prompts and their versions; active version pinned with a green dot
- Right panel: CodeMirror 6 with markdown + Jinja syntax highlighting
- Top toolbar: `Save` · `New version (clone)` · `Set as active` · `Diff against other version` · `Open in playground →`
- Variable inspector: parses `{{variables}}` from the template and shows them in a sidebar so you know what context the prompt expects

### 10.3 AI Playground

Backend endpoints:

```
POST /api/admin/playground/run         {system_prompt, user_prompt, temperature?, max_tokens?, provider_override?, model_override?, stream}
GET  /api/admin/playground/templates   list of registered prompts + their variable schemas
POST /api/admin/playground/render      {template_name, variables} → returns the rendered prompt without sending it
```

If `stream: true`, `/run` returns an SSE stream of `{type: "content", delta: "..."}` events plus a final `{type: "usage", input_tokens, output_tokens, latency_ms}` event.

**UI** (two columns):

- **Left** — input
  - Mode toggle: Free-form vs From template
  - If Free-form: system prompt textarea + user prompt textarea
  - If From template: dropdown of templates → variable form (auto-generated from the template's `{{...}}` parse) → rendered preview shown in the user-prompt textarea (still editable)
  - Advanced options: temperature, max_tokens, provider override, model override
  - `[ Send ]` button
- **Right** — output
  - Streamed response text
  - Token counts (input, output, cache_read, cache_write), latency ms, model used
  - `[ Try parse as JSON ]` toggle — attempts `JSON.parse` and displays as a syntax-highlighted tree below; on parse failure, shows the parse error inline

The "Try parse as JSON" toggle is the feature that catches the empty-response-from-proxy class of bug instantly: parse failure on an empty string surfaces "Unexpected end of input" before you even read the response box.

### 10.4 AI Usage dashboard

Reads from the existing `AIUsage` table (no new schema).

**UI**:

- Top stat cards: this month's totals (input, output, calls, estimated cost)
- Chart: tokens over time, last 12 months, stacked bar (input + output) — shadcn/ui Chart component (Recharts)
- Table: per-user-per-month rows `(month, user, calls, input, output, cache_read, cache_write, est_cost)`, sortable
- Filters: month range, user

**Cost estimation**: `flexloop.admin.pricing.PRICING` is a static dict mapping model name → input/output cost per 1M tokens (a minimal subset). The `model_pricing` table is a superset that also tracks `cache_read_per_million` and `cache_write_per_million` for models that price cache differently — the admin can fill these in via the "Set custom pricing for this model" button. When estimating, the table takes precedence over the static dict; if neither has the model, the cost column shows `—`. Don't pretend to know the cost when you don't.

## 11. Operations features

### 11.1 Backup & Restore

The admin endpoints **call the existing `BackupService`** in `flexloop.services.backup` for the actual file operations — no logic duplication. The original `/api/backup`, `/api/backups`, `/api/restore/{filename}` routes from `flexloop.routers.backup` remain in place unchanged (they're not iOS-callable in practice but they have no admin-auth requirement, so removing them would be a behavior change). The new admin routes coexist under a different prefix and add upload/download/delete:

```
GET    /api/admin/backups                              list backup files
POST   /api/admin/backups                              create new backup now
GET    /api/admin/backups/{filename}/download          stream the .db file
POST   /api/admin/backups/upload                       multipart upload
POST   /api/admin/backups/{filename}/restore           restore (with auto safety backup)
DELETE /api/admin/backups/{filename}                   delete a backup
```

**Restore safety**: `POST .../restore` auto-creates a `pre-restore-<timestamp>.db` backup of current state *before* swapping. Even if you restore the wrong file, you can roll back. The confirm dialog uses **type-to-confirm**:

> "This will replace the current database with `<filename>` (2.4 MB, created 6h ago). A safety backup of current state will be created first. Type the backup filename to confirm."

**UI**: table sorted newest first (filename, size, created, age), top right has `[+ Create backup]` and a drag-and-drop upload area, per-row actions are Download/Restore/Delete.

### 11.2 Health detail page

Single fat backend endpoint runs all checks in parallel:

```
GET /api/admin/health
→ {
    status: "healthy" | "degraded" | "down",
    checked_at: timestamp,
    components: {
      database: {status, ms, db_size_bytes, table_row_counts: {users: 5, workouts: 128, ...}},
      ai_provider: {status, ms, model, last_test_at},
      disk: {free_bytes, used_pct, mount},
      memory: {rss_bytes, vms_bytes},
      backups: {count, last_at, total_bytes},
      migrations: {applied, head, in_sync},
    },
    recent_errors: [{timestamp, level, message, logger}, ...],
    system: {python, fastapi, uvicorn, os, hostname, uptime_seconds},
  }
```

The AI provider check is **cached for 60 seconds** (don't burn tokens on every page refresh). A manual "Re-check now" button forces a fresh check.

**UI**: a single page with one panel per component. Each panel shows the relevant metrics with a green/yellow/red status pill. Recent errors are a tail of the last 20 WARNING+ records, clickable into the full log viewer.

### 11.3 Log viewer

**Where do logs come from?** A custom Python `logging.Handler` (`flexloop.admin.log_handler.RingBufferHandler`) installed in `flexloop.main` **at the very top of the module, before any router imports** so that early-startup errors (init_db failures, prompt loading, etc.) appear in the viewer rather than being lost. The handler does two things:

1. Keeps the **last 10 000 records in an in-memory ring buffer** (`collections.deque(maxlen=10000)`) — used for live tail and instant queries
2. Writes to a **rotating JSONL file** (`logs/flexloop.YYYY-MM-DD.jsonl`, 7-day retention) — used for history queries beyond the ring buffer

Records are stored as structured dicts: `{timestamp, level, logger, message, exception?, extra}`. Existing `logger.warning(...)` calls work unchanged.

**Backend endpoints**:

```
GET /api/admin/logs?level=warning&search=foo&since=...&limit=200    history query
GET /api/admin/logs/stream                                          SSE stream of new records
```

**UI**:

- Top filter bar: severity dropdown · search box · time range picker
- Main: virtualized list of log lines (`react-virtuoso`), color-coded by severity
- Bottom right: `[ ● Live tail ]` toggle — when on, the SSE stream pushes new records and the list auto-scrolls
- Click a line to expand: full message, logger name, exception traceback, extra fields as JSON

### 11.4 Manual triggers

A grid of action cards. Each card has a title, one-line description, an icon, and a `[Run]` button. Click → confirm dialog → run → toast or progress modal.

| Trigger | What it does | Confirm? | Long-running? |
|---|---|---|---|
| Re-seed exercises | Runs `scripts/seed_exercise_details.py` (idempotent) | yes | ~5s |
| Run pending migrations | `alembic upgrade head` | yes | ~1s |
| Backup now | Creates a backup file | no | ~1s |
| Test AI provider | Round-trip to current AI provider | no | ~3s |
| Reload prompts from disk | Clears `PromptManager` cache | no | instant |
| Vacuum database | `VACUUM` to reclaim disk | yes | ~2s |
| Clear all sessions | Deletes all `AdminSession` rows (logs everyone out, including you — confirm dialog explicitly says "you will be logged out and need to sign in again") | strong | instant |
| Recompute PRs | Runs PR detection across all users' workout history | yes | minutes — needs SSE progress |
| Clear AI usage | Wipes `ai_usage` rows | strong | instant |

**Backend**: one endpoint per trigger under `/api/admin/triggers/{name}`. Long-running triggers return SSE progress (`{percent, current_step, message}` events) followed by a final `{done, result}` event.

## 12. Cross-cutting

### 12.1 Visual theme

shadcn/ui defaults — dark mode by default with a light/dark toggle in the user menu. No custom theme work in v1. The admin UI is utilitarian; pixel polish is not the goal.

### 12.2 Mobile

shadcn/ui components are mobile-friendly out of the box (Sidebar collapses to a Sheet, DataTable becomes horizontally scrollable). No custom mobile screens — the desktop layout works in landscape on a phone, and degrades to "scroll horizontally" in portrait. Acceptable for an admin tool used occasionally from a phone via the VPS.

### 12.3 Internationalization

English only.

### 12.4 Testing

- **Backend**: pytest for new admin routers (auth, CRUD, config, prompts, playground, triggers). Reuses existing test infrastructure under `flexloop-server/tests/`. Integration tests against a test SQLite DB. Coverage target: every new endpoint has at least one happy-path and one auth-required test.
- **Frontend**: vitest for hooks and utilities, React Testing Library for component logic. Coverage target: the shared `useList/useDetail/useCreate/useUpdate/useDelete` hooks have unit tests; complex components (Plan editor, Playground, Log viewer) have component tests.
- **No e2e in v1**: Playwright is overkill for an internal tool. Manual smoke testing is sufficient.

### 12.5 Observability

All admin write actions log at INFO with structured extras (`extra={"admin_user": ..., "action": ..., "target": ...}`). These flow through the `RingBufferHandler`, so they're visible in the log viewer.

The AI playground caches the last 50 runs in memory (no DB persistence) so the user can quickly re-run or compare.

### 12.6 Dependency additions

**Python (pyproject.toml)**:

```toml
"bcrypt>=4.0.0",                # admin password hashing
"python-multipart>=0.0.9",      # backup file uploads
```

No new heavy dependencies. The admin uses the existing FastAPI, SQLAlchemy, Alembic, Pydantic stack. CSRF protection is handled by SameSite=Strict cookies + Origin header check (see §5.5), so no signing-key dependency is needed.

**Node.js (admin-ui/package.json)** — partial list:

```json
{
  "dependencies": {
    "react": "^18",
    "react-dom": "^18",
    "react-router-dom": "^6",
    "@tanstack/react-query": "^5",
    "react-hook-form": "^7",
    "zod": "^3",
    "@hookform/resolvers": "^3",
    "@radix-ui/react-*": "...",
    "tailwindcss": "^3",
    "tailwind-merge": "...",
    "class-variance-authority": "...",
    "clsx": "...",
    "lucide-react": "...",
    "@codemirror/lang-markdown": "^6",
    "codemirror": "^6",
    "react-virtuoso": "^4",
    "recharts": "^2",
    "date-fns": "^3"
  },
  "devDependencies": {
    "vite": "^5",
    "@vitejs/plugin-react": "^4",
    "typescript": "^5",
    "openapi-typescript": "^7",
    "vitest": "^1",
    "@testing-library/react": "^14"
  }
}
```

shadcn/ui components are copy-pasted into `admin-ui/src/components/ui/` rather than imported as a package.

## 13. Database migration summary

One Alembic migration creates four new tables:

- `admin_users` (see §5.1)
- `admin_sessions` (see §5.1)
- `admin_audit_log` — `(id, timestamp, admin_user_id, action, target_type, target_id, before_json, after_json)`
- `app_settings` — single-row table with one column per runtime-mutable setting (see §10.1). Migration includes a data step that **reads current `.env` values and inserts the seed row** so existing deployments don't reset to defaults.
- `model_pricing` — `(model_name PK, input_per_million, output_per_million, cache_read_per_million, cache_write_per_million)` for AI usage cost overrides

No changes to existing tables.

## 14. Phasing

The implementation plan will be structured as five phases. Each phase ends with a deployable, useful tool — no phase is "infrastructure with nothing to show".

### Phase 1 — Foundation

- Migrations (admin_users, admin_sessions, admin_audit_log, app_settings, model_pricing)
- Auth module (login, logout, session middleware, bootstrap CLI)
- `flexloop.admin` package skeleton, mounted in `main.py`
- Static file mount at `/admin/*` with SPA fallback
- Vite + React + TS + Tailwind + shadcn/ui project initialized in `admin-ui/`
- App shell: sidebar layout, dark mode, login page, AuthGate, user menu
- Dashboard landing page (health-first)
- Health detail page

**End of Phase 1**: you can `npm run build`, hit `/admin`, log in, and see the dashboard and health pages. Nothing else exists.

### Phase 2 — Boring CRUD

- `flexloop.admin.crud` helpers (`paginated_response`, sort/filter parsing)
- Frontend `useList/useDetail/useCreate/useUpdate/useDelete` hooks
- DataTable / EditSheet / DeleteDialog shared components
- Pages: Users, Workouts, Measurements, Personal Records, Exercises, AI Usage, AdminUsers (own profile + sessions)
- Each page has list + create + edit + delete + JSON escape hatch

**End of Phase 2**: you can browse and edit all your data through the UI.

### Phase 3 — Plans editor

- Standard Plans CRUD endpoints (the five-endpoint pattern)
- Plan-specific endpoints for day-level updates (`POST/PUT/DELETE /plans/{id}/days/{day_number}`)
- Plan detail page with per-day accordions, inline group/exercise/set editing
- "Plans" page in the sidebar wired up

**End of Phase 3**: you can hand-edit any AI-generated plan.

### Phase 4 — AI tools

- `app_settings` migration with `.env` seeding
- `flexloop.config.Settings` refactored to load from DB
- Config editor page (with reveal/rotate API key + Test connection)
- Prompt editor backend (filesystem read/write with file locking)
- Prompt editor page (CodeMirror, version tree, diff, set active)
- AI Playground backend (run, render, templates) with SSE streaming
- AI Playground page (free-form + template modes, JSON parse toggle)
- Audit log writes for all config changes

**End of Phase 4**: you can configure the AI provider, edit prompts, and test prompts without leaving the UI.

### Phase 5 — Operations

- Backup endpoints (list, create, upload, download, restore, delete)
- Backup page (table + drag-drop upload + type-to-confirm restore)
- Log handler (`RingBufferHandler` + JSONL rotating file)
- Log endpoints (history + SSE stream)
- Log viewer page (filter, virtualized list, live tail, expand details)
- Trigger endpoints (one per item in §11.4)
- Triggers page (action card grid + confirm dialogs + SSE progress for long ones)

**End of Phase 5**: full v1 feature parity with this spec.

## 15. Open questions / decisions deferred to implementation

1. **Caddyfile / nginx sample for the VPS deployment** — included in Phase 1's documentation, but the exact form depends on the user's domain choice. Will be authored in Phase 1 and committed to `flexloop-server/deploy/` as a reference.
2. **Static pricing table contents** — `flexloop.admin.pricing.PRICING` will be seeded with current OpenAI / Anthropic / OpenRouter pricing as of 2026-04 in Phase 4. The `model_pricing` table allows runtime overrides for proxied models.
3. **`react-virtuoso` vs `tanstack/virtual`** — both work for the log viewer; final pick made during Phase 5 based on bundle size and integration smoothness.
4. **JSON view library**: `@uiw/react-json-view` vs CodeMirror with JSON mode for the JSON escape hatch tab — final pick made in Phase 2.

These are all small implementation details that don't affect the architecture.

## 16. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Single dev maintaining two stacks (Python + TS) | Auto-generated TS types from OpenAPI reduce drift; phased delivery means each phase is independently shippable. |
| `.env` → DB config migration breaks existing deployment | Migration includes a data step that reads current `.env` values and seeds the table. Settings still fall back to `.env` if the row is missing. |
| Restoring a backup corrupts the live DB | Auto safety-backup before every restore; type-to-confirm UI; restores hold a write lock during the file swap. |
| Prompt editor on read-only filesystem | Document the writable-filesystem requirement in the deployment guide. Migrating prompts to DB is a known fork if this becomes a constraint. |
| Admin session cookie stolen via XSS | `HttpOnly` flag prevents JavaScript access to the cookie. CSP header in admin static mount blocks inline scripts. |
| Bad prompt edit breaks plan generation in production | The "active version" mechanism means a new version doesn't take effect until you explicitly switch. You can switch back to a previous version instantly. |

## 17. Acceptance criteria

The dashboard is considered shipped when, on a fresh checkout:

1. `cd flexloop-server && uv sync && cd admin-ui && npm ci && npm run build && cd .. && uv run python -m flexloop.admin.bootstrap create-admin <username>` works end-to-end
2. `uv run uvicorn flexloop.main:app --port 8000`, then visiting `http://localhost:8000/admin` shows the login page
3. After login, you can: see the dashboard, navigate to every sidebar page (14 total: Dashboard, Users, Plans, Workouts, Measurements, PRs, Exercises, AI Config, Prompts, Playground, AI Usage, Backup, Logs, Triggers), create/edit/delete in every CRUD page, edit a prompt and test it in the playground, edit the AI config and test the connection, create and restore a backup, view live logs, run any manual trigger
4. Existing iOS app continues to work unchanged (regression tested by hitting `/api/health` and a sample plan generation)
5. All new backend endpoints have at least one pytest test
6. `npm run build` produces a bundle under 1 MB gzipped
7. Mobile Safari can render the dashboard and execute basic CRUD without horizontal scroll on a 390px-wide viewport
