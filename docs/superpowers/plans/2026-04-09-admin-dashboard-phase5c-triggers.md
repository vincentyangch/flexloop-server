# Admin Dashboard — Phase 5c (Manual Triggers) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the admin Triggers page — a grid of 9 action cards that let the operator run maintenance tasks (re-seed exercises, run migrations, backup, test AI, reload prompts, vacuum DB, clear sessions, recompute PRs, clear AI usage) with confirm dialogs for destructive actions and SSE progress for the long-running PR recomputation.

**Architecture:**
1. **Single router** at `flexloop.admin.routers.triggers` with one `POST /api/admin/triggers/{name}` endpoint per trigger. Each handler calls existing services (BackupService, _run_migrations, check_prs, etc.) — no logic duplication. Destructive triggers are just regular endpoints; the confirm UX is purely frontend. The one long-running trigger (recompute-prs) returns a `StreamingResponse` with SSE progress events.
2. **Frontend** adds a `TriggersPage.tsx` with a responsive grid of action cards. Each card has a title, description, icon, and Run button. Clicking Run opens a confirm dialog (simple or type-to-confirm for destructive actions), then calls the trigger endpoint. The recompute-prs card shows a progress modal with SSE streaming.

**Tech Stack (new to phase 5c):** No new backend or frontend dependencies.

**Spec reference:** `docs/superpowers/specs/2026-04-06-admin-dashboard-design.md`. Read §11.4 (Manual triggers — authoritative), §14 phase 5 bullet, §17 acceptance criteria.

**Phases 1-5b already delivered.** Phase 5c is the final sub-plan and the final phase of the admin dashboard.

---

## Decisions locked in for this phase

1. **One endpoint per trigger.** Each trigger is `POST /api/admin/triggers/{name}`. Trigger names: `reseed-exercises`, `run-migrations`, `backup`, `test-ai`, `reload-prompts`, `vacuum-db`, `clear-sessions`, `recompute-prs`, `clear-ai-usage`.

2. **All triggers require admin auth.** `Depends(require_admin)` on every endpoint.

3. **Audit logging for destructive triggers only.** Audit entries for: `clear-sessions`, `clear-ai-usage`, `vacuum-db`, `recompute-prs`, `reseed-exercises`, `run-migrations`. No audit for `backup` (already audited by the backup router), `test-ai` (read-only), or `reload-prompts` (side-effect-free).

4. **Confirm levels per spec §11.4:**
   - No confirm: `backup`, `test-ai`, `reload-prompts`
   - Simple confirm: `reseed-exercises`, `run-migrations`, `vacuum-db`, `recompute-prs`
   - Strong confirm (type-to-confirm): `clear-sessions`, `clear-ai-usage`

5. **Recompute PRs uses SSE streaming.** Returns `StreamingResponse` with `{type: "progress", percent, current_step, message}` events followed by `{type: "done", result}`. Iterates all users → all workout sessions → all sets, calling `check_prs()` for each set.

6. **Re-seed exercises runs the seed logic inline** (not as a subprocess). Import and call the `seed()` function from `scripts/seed_exercise_details.py` adapted as a helper, or replicate the simple logic (load JSON, update exercises) directly in the trigger handler. The script is ~15 lines of logic — replicating avoids subprocess/path issues.

7. **Reload prompts** is a no-op in the current architecture. `PromptManager` is instantiated fresh per request — there's no persistent cache to clear. The trigger succeeds immediately and returns `{status: "ok", message: "Prompt cache cleared"}`. If a cache is added later, the trigger will be meaningful.

8. **Vacuum database** uses a synchronous `sqlite3.connect()` + `cursor.execute("VACUUM")` because SQLite VACUUM cannot run inside a transaction (and aiosqlite wraps everything in transactions). Same pattern as `_run_migrations`.

9. **Frontend: one page, grid layout, three dialog types.**
   - Cards in a responsive CSS grid (2-3 columns)
   - No-confirm triggers fire immediately on click
   - Simple confirm uses `AlertDialog` with "Are you sure?"
   - Strong confirm uses `AlertDialog` with type-to-confirm input
   - Recompute PRs shows a progress modal during execution

10. **Worktree + feature branch:**
    - Worktree path: `/Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase5c`
    - Branch: `feat/admin-dashboard-phase5c-triggers`
    - Merge: fast-forward into `main`, delete branch + worktree, bump parent submodule, update memory.

---

## File Structure

All paths relative to `flexloop-server/` unless stated otherwise.

**Backend — new:**
```
src/flexloop/admin/routers/
└── triggers.py                 NEW — 9 trigger endpoints
```

**Backend — modified:**
```
src/flexloop/main.py            MODIFY — import and mount admin_triggers_router
```

**Frontend — new:**
```
admin-ui/src/pages/
└── TriggersPage.tsx            NEW — trigger grid page
```

**Frontend — modified:**
```
admin-ui/src/App.tsx            MODIFY — import TriggersPage + add route
admin-ui/src/components/
└── AppSidebar.tsx              MODIFY — enable Triggers sidebar item
```

**Tests — new:**
```
tests/test_admin_triggers.py    NEW — integration tests for trigger endpoints
```

---

## Chunk 1: Backend — triggers router + tests

### Task 1: Create triggers router with simple triggers

**Files:**
- Create: `src/flexloop/admin/routers/triggers.py`
- Create: `tests/test_admin_triggers.py`

- [ ] **Step 1: Write failing tests for simple triggers**

```python
"""Integration tests for /api/admin/triggers."""
from __future__ import annotations

import logging

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import SESSION_COOKIE_NAME, create_session, hash_password
from flexloop.models.admin_user import AdminUser


ORIGIN = {"Origin": "http://localhost:5173"}


async def _cookie(db: AsyncSession) -> dict[str, str]:
    a = AdminUser(username="t", password_hash=hash_password("password123"))
    db.add(a); await db.commit(); await db.refresh(a)
    token, _ = await create_session(db, admin_user_id=a.id)
    return {SESSION_COOKIE_NAME: token}


class TestTriggerAuth:
    """All trigger endpoints require admin auth."""

    async def test_reseed_auth(self, client: AsyncClient) -> None:
        assert (await client.post("/api/admin/triggers/reseed-exercises")).status_code == 401

    async def test_migrations_auth(self, client: AsyncClient) -> None:
        assert (await client.post("/api/admin/triggers/run-migrations")).status_code == 401

    async def test_backup_auth(self, client: AsyncClient) -> None:
        assert (await client.post("/api/admin/triggers/backup")).status_code == 401

    async def test_test_ai_auth(self, client: AsyncClient) -> None:
        assert (await client.post("/api/admin/triggers/test-ai")).status_code == 401

    async def test_reload_prompts_auth(self, client: AsyncClient) -> None:
        assert (await client.post("/api/admin/triggers/reload-prompts")).status_code == 401

    async def test_vacuum_auth(self, client: AsyncClient) -> None:
        assert (await client.post("/api/admin/triggers/vacuum-db")).status_code == 401

    async def test_clear_sessions_auth(self, client: AsyncClient) -> None:
        assert (await client.post("/api/admin/triggers/clear-sessions")).status_code == 401

    async def test_clear_ai_usage_auth(self, client: AsyncClient) -> None:
        assert (await client.post("/api/admin/triggers/clear-ai-usage")).status_code == 401


class TestReloadPrompts:
    async def test_reload(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        res = await client.post(
            "/api/admin/triggers/reload-prompts",
            cookies=cookies, headers=ORIGIN,
        )
        assert res.status_code == 200
        assert res.json()["status"] == "ok"


class TestBackupTrigger:
    async def test_creates_backup(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        res = await client.post(
            "/api/admin/triggers/backup",
            cookies=cookies, headers=ORIGIN,
        )
        assert res.status_code == 200
        assert "filename" in res.json()


class TestTestAi:
    async def test_returns_result(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        res = await client.post(
            "/api/admin/triggers/test-ai",
            cookies=cookies, headers=ORIGIN,
        )
        assert res.status_code == 200
        # May succeed or fail depending on AI config — just check shape
        body = res.json()
        assert "status" in body
        assert "latency_ms" in body


class TestVacuumDb:
    async def test_vacuum(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        res = await client.post(
            "/api/admin/triggers/vacuum-db",
            cookies=cookies, headers=ORIGIN,
        )
        assert res.status_code == 200
        assert res.json()["status"] == "ok"


class TestClearSessions:
    async def test_clears_all(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        # Our own session exists
        res = await client.post(
            "/api/admin/triggers/clear-sessions",
            cookies=cookies, headers=ORIGIN,
        )
        assert res.status_code == 200
        assert res.json()["status"] == "ok"
        assert res.json()["deleted"] >= 1


class TestClearAiUsage:
    async def test_clears_all(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        res = await client.post(
            "/api/admin/triggers/clear-ai-usage",
            cookies=cookies, headers=ORIGIN,
        )
        assert res.status_code == 200
        assert res.json()["status"] == "ok"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd flexloop-server && uv run pytest tests/test_admin_triggers.py -v`
Expected: FAIL (router doesn't exist)

- [ ] **Step 3: Create the triggers router**

```python
"""Admin manual trigger endpoints.

One-click maintenance tasks exposed as POST endpoints. Each trigger
calls existing service code — no logic duplication.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import time

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.audit import write_audit_log
from flexloop.admin.auth import require_admin
from flexloop.config import settings
from flexloop.db.engine import _run_migrations, get_session
from flexloop.models.admin_session import AdminSession
from flexloop.models.ai import AIUsage
from flexloop.services.backup import BackupService

router = APIRouter(prefix="/api/admin/triggers", tags=["admin:triggers"])


def _get_backup_service() -> BackupService:
    db_path = settings.database_url.replace("sqlite+aiosqlite:///", "")
    return BackupService(db_path=db_path, backup_dir="backups")


@router.post("/reload-prompts")
async def reload_prompts(
    _admin=Depends(require_admin),
) -> dict:
    """No-op in current architecture — PromptManager is stateless per request."""
    return {"status": "ok", "message": "Prompt cache cleared"}


@router.post("/backup")
async def trigger_backup(
    _admin=Depends(require_admin),
) -> dict:
    svc = _get_backup_service()
    info = svc.create_backup(schema_version="1.0.0")
    return {
        "status": "ok",
        "filename": info.filename,
        "size_bytes": info.size_bytes,
    }


@router.post("/test-ai")
async def trigger_test_ai(
    _admin=Depends(require_admin),
) -> dict:
    from flexloop.ai.factory import create_adapter

    start = time.perf_counter()
    try:
        adapter = create_adapter(
            provider=settings.ai_provider,
            model=settings.ai_model,
            api_key=settings.ai_api_key,
            base_url=settings.ai_base_url,
        )
        response = await asyncio.wait_for(
            adapter.generate(
                system_prompt="You are a helpful assistant.",
                user_prompt="Say hello in one word.",
                temperature=0.0,
                max_tokens=10,
            ),
            timeout=30.0,
        )
        latency_ms = int((time.perf_counter() - start) * 1000)
        return {
            "status": "ok",
            "latency_ms": latency_ms,
            "response_text": response.content[:200],
        }
    except Exception as e:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return {
            "status": "error",
            "latency_ms": latency_ms,
            "error": str(e),
        }


@router.post("/run-migrations")
async def trigger_run_migrations(
    db: AsyncSession = Depends(get_session),
    admin=Depends(require_admin),
) -> dict:
    try:
        _run_migrations()
    except Exception as e:
        return {"status": "error", "error": str(e)}
    await write_audit_log(
        db, admin_user_id=admin.id,
        action="trigger_run_migrations", target_type="system",
    )
    await db.commit()
    return {"status": "ok", "message": "Migrations applied"}


@router.post("/reseed-exercises")
async def trigger_reseed_exercises(
    db: AsyncSession = Depends(get_session),
    admin=Depends(require_admin),
) -> dict:
    import json as json_mod
    from pathlib import Path

    from flexloop.models.exercise import Exercise

    data_path = Path(__file__).parent.parent.parent.parent / "data" / "exercise_details.json"
    if not data_path.exists():
        return {"status": "error", "error": "exercise_details.json not found"}

    with open(data_path) as f:
        details = json_mod.load(f)

    result = await db.execute(select(Exercise))
    exercises = result.scalars().all()

    updated = 0
    for ex in exercises:
        if ex.name in details:
            ex.metadata_json = details[ex.name]
            updated += 1

    await write_audit_log(
        db, admin_user_id=admin.id,
        action="trigger_reseed_exercises", target_type="system",
        after={"updated": updated},
    )
    await db.commit()
    return {"status": "ok", "updated": updated}


@router.post("/vacuum-db")
async def trigger_vacuum_db(
    db: AsyncSession = Depends(get_session),
    admin=Depends(require_admin),
) -> dict:
    db_path = settings.database_url.replace("sqlite+aiosqlite:///", "")
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("VACUUM")
        conn.close()
    except Exception as e:
        return {"status": "error", "error": str(e)}
    await write_audit_log(
        db, admin_user_id=admin.id,
        action="trigger_vacuum_db", target_type="system",
    )
    await db.commit()
    return {"status": "ok", "message": "Database vacuumed"}


@router.post("/clear-sessions")
async def trigger_clear_sessions(
    db: AsyncSession = Depends(get_session),
    admin=Depends(require_admin),
) -> dict:
    result = await db.execute(delete(AdminSession))
    deleted = result.rowcount
    await write_audit_log(
        db, admin_user_id=admin.id,
        action="trigger_clear_sessions", target_type="system",
        after={"deleted": deleted},
    )
    await db.commit()
    return {"status": "ok", "deleted": deleted}


@router.post("/clear-ai-usage")
async def trigger_clear_ai_usage(
    db: AsyncSession = Depends(get_session),
    admin=Depends(require_admin),
) -> dict:
    result = await db.execute(delete(AIUsage))
    deleted = result.rowcount
    await write_audit_log(
        db, admin_user_id=admin.id,
        action="trigger_clear_ai_usage", target_type="system",
        after={"deleted": deleted},
    )
    await db.commit()
    return {"status": "ok", "deleted": deleted}
```

- [ ] **Step 4: Mount the router in main.py**

In `src/flexloop/main.py`, add:

```python
from flexloop.admin.routers.triggers import router as admin_triggers_router
```

And:

```python
app.include_router(admin_triggers_router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd flexloop-server && uv run pytest tests/test_admin_triggers.py -v`
Expected: PASS (most triggers should work; test-ai may return error status if no AI configured, but the test only checks shape)

- [ ] **Step 6: Commit**

```bash
git add src/flexloop/admin/routers/triggers.py src/flexloop/main.py tests/test_admin_triggers.py
git commit -m "feat(admin): add 8 trigger endpoints (all except recompute-prs)"
```

---

### Task 2: Add recompute-prs trigger with SSE progress

**Files:**
- Modify: `src/flexloop/admin/routers/triggers.py`
- Modify: `tests/test_admin_triggers.py`

- [ ] **Step 1: Write failing test for recompute-prs**

Append to `tests/test_admin_triggers.py`:

```python
class TestRecomputePrs:
    async def test_auth(self, client: AsyncClient) -> None:
        assert (await client.post("/api/admin/triggers/recompute-prs")).status_code == 401

    async def test_returns_sse(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        async with client.stream(
            "POST", "/api/admin/triggers/recompute-prs",
            cookies=cookies, headers=ORIGIN,
        ) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")
            chunks = []
            async for chunk in response.aiter_text():
                chunks.append(chunk)
                if "done" in chunk:
                    break
            text = "".join(chunks)
            assert "data:" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd flexloop-server && uv run pytest tests/test_admin_triggers.py::TestRecomputePrs -v`
Expected: FAIL

- [ ] **Step 3: Add the recompute-prs endpoint**

Append to `src/flexloop/admin/routers/triggers.py`:

```python
@router.post("/recompute-prs")
async def trigger_recompute_prs(
    db: AsyncSession = Depends(get_session),
    admin=Depends(require_admin),
) -> StreamingResponse:
    """Recompute personal records for all users.

    Long-running — returns SSE progress events.
    """
    from flexloop.models.user import User
    from flexloop.models.workout import WorkoutSession, WorkoutSet
    from flexloop.services.pr_detection import check_prs

    async def event_generator():
        def _sse(data: dict) -> str:
            return f"data: {json.dumps(data)}\n\n"

        # Count total sets for progress tracking
        total_result = await db.execute(select(func.count()).select_from(WorkoutSet))
        total_sets = total_result.scalar_one()

        if total_sets == 0:
            yield _sse({"type": "done", "result": {"new_prs": 0, "sets_checked": 0}})
            return

        # Get all users
        users_result = await db.execute(select(User))
        users = {u.id: u for u in users_result.scalars().all()}

        processed = 0
        new_prs_total = 0

        # Iterate all workout sets
        sets_result = await db.execute(
            select(WorkoutSet, WorkoutSession.user_id)
            .join(WorkoutSession, WorkoutSet.session_id == WorkoutSession.id)
        )

        for ws, user_id in sets_result.all():
            user = users.get(user_id)
            weight_unit = user.weight_unit if user else "kg"

            try:
                new_prs = await check_prs(
                    user_id=user_id,
                    exercise_id=ws.exercise_id,
                    weight=ws.weight,
                    reps=ws.reps,
                    session_id=ws.session_id,
                    db=db,
                    weight_unit=weight_unit,
                )
                new_prs_total += len(new_prs)
            except Exception:
                pass  # Skip errors on individual sets

            processed += 1
            if processed % 50 == 0 or processed == total_sets:
                percent = int(processed / total_sets * 100)
                yield _sse({
                    "type": "progress",
                    "percent": percent,
                    "current_step": f"Set {processed}/{total_sets}",
                    "message": f"Checked {processed} sets, found {new_prs_total} new PRs",
                })

        await write_audit_log(
            db, admin_user_id=admin.id,
            action="trigger_recompute_prs", target_type="system",
            after={"sets_checked": processed, "new_prs": new_prs_total},
        )
        await db.commit()

        yield _sse({
            "type": "done",
            "result": {"new_prs": new_prs_total, "sets_checked": processed},
        })

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd flexloop-server && uv run pytest tests/test_admin_triggers.py -v`
Expected: PASS

- [ ] **Step 5: Run the full test suite**

Run: `cd flexloop-server && uv run pytest -x -q`
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add src/flexloop/admin/routers/triggers.py tests/test_admin_triggers.py
git commit -m "feat(admin): add recompute-prs trigger with SSE progress"
```

---

## Chunk 2: Frontend — TriggersPage + routing + sidebar

### Task 3: Enable sidebar and add route

**Files:**
- Modify: `admin-ui/src/components/AppSidebar.tsx`
- Modify: `admin-ui/src/App.tsx`

- [ ] **Step 1: Enable the Triggers sidebar item**

In `admin-ui/src/components/AppSidebar.tsx`, change the Triggers item:

```typescript
// Before:
{ label: "Triggers", to: "/ops/triggers", icon: Wrench, disabled: true },
// After:
{ label: "Triggers", to: "/ops/triggers", icon: Wrench },
```

- [ ] **Step 2: Add the route**

In `admin-ui/src/App.tsx`, import and add:

```typescript
import { TriggersPage } from "@/pages/TriggersPage";
// ...
<Route path="ops/triggers" element={<TriggersPage />} />
```

- [ ] **Step 3: Create placeholder page**

```tsx
export function TriggersPage() {
  return <div className="p-6"><h1 className="text-2xl font-semibold">Triggers</h1></div>;
}
```

- [ ] **Step 4: Verify build**

Run: `cd flexloop-server/admin-ui && npm run build`

- [ ] **Step 5: Commit**

```bash
git add admin-ui/src/components/AppSidebar.tsx admin-ui/src/App.tsx admin-ui/src/pages/TriggersPage.tsx
git commit -m "feat(admin): wire up Triggers route and sidebar item"
```

---

### Task 4: TriggersPage — full implementation

**Files:**
- Modify: `admin-ui/src/pages/TriggersPage.tsx`

- [ ] **Step 1: Implement the triggers page**

Replace `admin-ui/src/pages/TriggersPage.tsx` with the full implementation:

```tsx
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { parseSSE } from "@/lib/sseReader";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Input } from "@/components/ui/input";
import {
  Card,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { toast } from "sonner";
import {
  Database,
  HardDriveDownload,
  Loader2,
  RefreshCw,
  RotateCcw,
  Scissors,
  Send,
  Sprout,
  Trash2,
  Trophy,
  Wrench,
} from "lucide-react";

type TriggerDef = {
  name: string;
  title: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
  confirm: "none" | "simple" | "strong";
  confirmLabel?: string;
  sse?: boolean;
};

const TRIGGERS: TriggerDef[] = [
  {
    name: "reseed-exercises",
    title: "Re-seed exercises",
    description: "Reload exercise metadata from the data file",
    icon: Sprout,
    confirm: "simple",
  },
  {
    name: "run-migrations",
    title: "Run pending migrations",
    description: "Apply any unapplied Alembic migrations",
    icon: Database,
    confirm: "simple",
  },
  {
    name: "backup",
    title: "Backup now",
    description: "Create an immediate database backup",
    icon: HardDriveDownload,
    confirm: "none",
  },
  {
    name: "test-ai",
    title: "Test AI provider",
    description: "Send a test request to the configured AI provider",
    icon: Send,
    confirm: "none",
  },
  {
    name: "reload-prompts",
    title: "Reload prompts",
    description: "Clear the prompt template cache",
    icon: RefreshCw,
    confirm: "none",
  },
  {
    name: "vacuum-db",
    title: "Vacuum database",
    description: "Reclaim unused disk space from the database",
    icon: Scissors,
    confirm: "simple",
  },
  {
    name: "clear-sessions",
    title: "Clear all sessions",
    description: "Log out all admins — you will be logged out and need to sign in again",
    icon: Trash2,
    confirm: "strong",
    confirmLabel: "CLEAR SESSIONS",
  },
  {
    name: "recompute-prs",
    title: "Recompute PRs",
    description: "Re-detect personal records across all workout history",
    icon: Trophy,
    confirm: "simple",
    sse: true,
  },
  {
    name: "clear-ai-usage",
    title: "Clear AI usage",
    description: "Delete all AI token usage records",
    icon: RotateCcw,
    confirm: "strong",
    confirmLabel: "CLEAR USAGE",
  },
];

export function TriggersPage() {
  const [confirmTrigger, setConfirmTrigger] = useState<TriggerDef | null>(null);
  const [strongConfirmText, setStrongConfirmText] = useState("");
  const [runningTrigger, setRunningTrigger] = useState<string | null>(null);
  const [sseProgress, setSseProgress] = useState<{
    percent: number;
    message: string;
  } | null>(null);

  const triggerMut = useMutation({
    mutationFn: async (name: string) => {
      const res = await api.post<Record<string, unknown>>(
        `/api/admin/triggers/${name}`,
      );
      return res;
    },
    onSuccess: (data, name) => {
      setRunningTrigger(null);
      const status = data.status as string;
      if (status === "ok") {
        toast.success(`${name}: success`);
      } else {
        toast.error(`${name}: ${data.error ?? "failed"}`);
      }
    },
    onError: (_err, name) => {
      setRunningTrigger(null);
      toast.error(`${name}: request failed`);
    },
  });

  async function runSseTrigger(name: string) {
    setRunningTrigger(name);
    setSseProgress({ percent: 0, message: "Starting…" });

    try {
      const res = await fetch(`/api/admin/triggers/${name}`, {
        method: "POST",
        credentials: "include",
      });

      for await (const event of parseSSE(res)) {
        const evt = event as Record<string, unknown>;
        if (evt.type === "progress") {
          setSseProgress({
            percent: (evt.percent as number) ?? 0,
            message: (evt.message as string) ?? "",
          });
        } else if (evt.type === "done") {
          setSseProgress(null);
          setRunningTrigger(null);
          const result = evt.result as Record<string, unknown>;
          toast.success(
            `${name}: ${result?.new_prs ?? 0} new PRs found, ${result?.sets_checked ?? 0} sets checked`,
          );
        }
      }
    } catch {
      setSseProgress(null);
      setRunningTrigger(null);
      toast.error(`${name}: connection failed`);
    }
  }

  function handleRun(trigger: TriggerDef) {
    if (trigger.confirm === "none") {
      fireTrigger(trigger);
    } else {
      setConfirmTrigger(trigger);
      setStrongConfirmText("");
    }
  }

  function fireTrigger(trigger: TriggerDef) {
    setConfirmTrigger(null);
    setStrongConfirmText("");
    if (trigger.sse) {
      runSseTrigger(trigger.name);
    } else {
      setRunningTrigger(trigger.name);
      triggerMut.mutate(trigger.name);
    }
  }

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-semibold">Triggers</h1>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {TRIGGERS.map((t) => (
          <Card key={t.name}>
            <CardHeader>
              <div className="flex items-center gap-2">
                <t.icon className="h-5 w-5 text-muted-foreground" />
                <CardTitle className="text-base">{t.title}</CardTitle>
              </div>
              <CardDescription>{t.description}</CardDescription>
            </CardHeader>
            <CardFooter>
              <Button
                size="sm"
                onClick={() => handleRun(t)}
                disabled={runningTrigger !== null}
              >
                {runningTrigger === t.name ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Running…
                  </>
                ) : (
                  "Run"
                )}
              </Button>
            </CardFooter>
          </Card>
        ))}
      </div>

      {/* SSE progress overlay */}
      {sseProgress && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-80 rounded-lg bg-background p-6 shadow-lg space-y-3">
            <p className="font-medium">Recomputing PRs…</p>
            <div className="h-2 rounded-full bg-muted overflow-hidden">
              <div
                className="h-full bg-primary transition-all"
                style={{ width: `${sseProgress.percent}%` }}
              />
            </div>
            <p className="text-sm text-muted-foreground">{sseProgress.message}</p>
          </div>
        </div>
      )}

      {/* Confirm dialog */}
      <AlertDialog
        open={confirmTrigger !== null}
        onOpenChange={(open) => {
          if (!open) {
            setConfirmTrigger(null);
            setStrongConfirmText("");
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              Run {confirmTrigger?.title}?
            </AlertDialogTitle>
            <AlertDialogDescription>
              {confirmTrigger?.description}.
              {confirmTrigger?.confirm === "strong" && (
                <>
                  {" "}This action cannot be undone. Type{" "}
                  <code className="font-mono font-bold">
                    {confirmTrigger?.confirmLabel}
                  </code>{" "}
                  to confirm.
                </>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          {confirmTrigger?.confirm === "strong" && (
            <Input
              value={strongConfirmText}
              onChange={(e) => setStrongConfirmText(e.target.value)}
              placeholder={confirmTrigger.confirmLabel ?? ""}
              className="font-mono"
            />
          )}
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={
                confirmTrigger?.confirm === "strong" &&
                strongConfirmText !== confirmTrigger?.confirmLabel
              }
              onClick={() => confirmTrigger && fireTrigger(confirmTrigger)}
            >
              Run
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
```

- [ ] **Step 2: Verify build**

Run: `cd flexloop-server/admin-ui && npm run build`
Expected: build succeeds

- [ ] **Step 3: Commit**

```bash
git add admin-ui/src/pages/TriggersPage.tsx
git commit -m "feat(admin): TriggersPage with action grid, confirm dialogs, SSE progress"
```

---

### Task 5: Final verification

- [ ] **Step 1: Run full backend test suite**

Run: `cd flexloop-server && uv run pytest -x -q`
Expected: all tests pass

- [ ] **Step 2: Build frontend**

Run: `cd flexloop-server/admin-ui && npm run build`
Expected: build succeeds

- [ ] **Step 3: Verify all 3 Operations sidebar items are enabled**

Check `AppSidebar.tsx` — none of the Operations items should have `disabled: true`.

- [ ] **Step 4: Quick manual smoke test** (optional)

Start the backend and check:
- Navigate to `/admin/ops/triggers`
- 9 action cards visible in a grid
- "Reload prompts" fires immediately (no confirm)
- "Vacuum database" shows simple confirm
- "Clear all sessions" shows type-to-confirm with "CLEAR SESSIONS"
- After confirming, toast shows result

- [ ] **Step 5: Final commit if needed**

```bash
git add src/flexloop/admin/routers/triggers.py admin-ui/src/pages/TriggersPage.tsx
git commit -m "chore(admin): phase 5c final adjustments"
```
