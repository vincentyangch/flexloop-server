# Admin Dashboard — Phase 5a (Backup & Restore) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the admin Backup & Restore page — list/create/download/upload/restore/delete backups through the admin dashboard with type-to-confirm safety for destructive operations and audit logging for every mutation.

**Architecture:**
1. **Reuses existing `BackupService`** in `flexloop.services.backup`. The admin router is a thin wrapper that adds auth, audit logging, download streaming, and multipart upload. The existing non-admin `/api/backup` and `/api/backups` routes remain untouched.
2. **New admin router** at `flexloop.admin.routers.backup` exposes 6 endpoints under `/api/admin/backups`. Download streams the `.db` file via `FileResponse`. Upload accepts `multipart/form-data` and saves to the backup directory. Restore calls `BackupService.restore()` which already creates a pre-restore safety backup. All mutations write audit log entries.
3. **Frontend** replaces the disabled "Backup & Restore" sidebar item with a live page at `/ops/backup`. The page has a backup table (sorted newest first), a "Create backup" button, a drag-and-drop upload zone, and per-row actions (Download, Restore with type-to-confirm, Delete with confirm).

**Tech Stack (new to phase 5a):** No new backend dependencies. No new frontend dependencies (reuses existing shadcn components + `sonner` toasts).

**Spec reference:** `docs/superpowers/specs/2026-04-06-admin-dashboard-design.md`. Read §11.1 (Backup & Restore — authoritative), §14 phase 5 bullet, §17 acceptance criteria 3 and 5.

**Phases 1-4d already delivered.** Phase 5a is the first of three phase-5 sub-plans (5a Backup, 5b Logs, 5c Triggers). Phases 5b and 5c are out of scope.

---

## Decisions locked in for this phase

These choices are fixed. Do not re-litigate mid-execution.

1. **`BackupService` is reused as-is.** No changes to `flexloop/services/backup.py`. The admin router instantiates it with the same `db_path` / `backup_dir` derivation as the existing non-admin `flexloop.routers.backup`. The `get_backup_service()` factory is duplicated in the admin router (one-liner, not worth an abstraction).

2. **`db_path` derivation:** Extract the file path from `settings.database_url` by stripping the `sqlite+aiosqlite:///` prefix: `settings.database_url.replace("sqlite+aiosqlite:///", "")`. Same approach as `flexloop.db.engine._run_migrations`.

3. **Download uses `FileResponse`.** The endpoint returns `FileResponse(path, media_type="application/octet-stream", filename=filename)`. No chunked streaming needed — SQLite backups are small (typically < 50 MB).

4. **Upload uses `UploadFile` (multipart/form-data).** The file is written to the backup directory with the original filename. If a file with the same name already exists, the endpoint returns 409 Conflict. Filename is validated: must match `*.db` pattern and not contain path separators. Max upload size is enforced by reading in chunks and aborting at 200 MB.

5. **Restore runs Alembic migrations after copy.** After `BackupService.restore()` copies the backup over the live DB, the endpoint calls `_run_migrations()` from `flexloop.db.engine` — same as the existing non-admin restore route. This ensures a restored backup from an older schema version gets migrated up.

6. **Audit log entries for all mutations:**
   - `action="backup_create"`, `target_type="backup"`, `target_id=filename`
   - `action="backup_upload"`, `target_type="backup"`, `target_id=filename`, `after={size_bytes}`
   - `action="backup_restore"`, `target_type="backup"`, `target_id=filename` — written BEFORE the restore, because restore replaces the DB file and the session's connection becomes stale afterward
   - `action="backup_delete"`, `target_type="backup"`, `target_id=filename`
   Download is read-only — no audit entry.

7. **No new database migration.** The `backups` model table already exists from phase 1. However, the admin router does NOT use the `Backup` ORM model — it calls `BackupService` which works directly with the filesystem. The `backups` table is unused by this phase (it was created by the original non-admin backup system but never populated in practice). This phase is filesystem-only.

8. **Frontend page is custom, not DataTable/EditSheet.** The backup page uses a simple `<table>` (or shadcn `Table`) with manual rows. No pagination needed (backup count is small). No `useList` hook — a custom `useQuery` fetches the flat list. Upload uses a hidden `<input type="file">` triggered by a drop zone.

9. **Type-to-confirm for Restore.** The confirm dialog shows the backup filename and requires the user to type the filename to proceed. Same pattern as the spec's "strong confirm" — uses an `AlertDialog` with an input field that enables the action button only when the typed text matches.

10. **Simple confirm for Delete.** Standard `AlertDialog` with "Are you sure?" — not type-to-confirm. Backups are recoverable by re-creating.

11. **Worktree + feature branch:**
    - Worktree path: `/Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase5a`
    - Branch: `feat/admin-dashboard-phase5a-backup`
    - Merge: fast-forward into `main`, delete branch + worktree, bump parent submodule, update memory.

---

## File Structure

All paths relative to `flexloop-server/` unless stated otherwise.

**Backend — new:**
```
src/flexloop/admin/
├── schemas/
│   └── backup.py                   NEW — response/upload schemas
└── routers/
    └── backup.py                   NEW — 6 admin backup endpoints
```

**Backend — modified:**
```
src/flexloop/main.py                MODIFY — import and mount admin_backup_router
```

**Frontend — new:**
```
admin-ui/src/pages/
└── BackupPage.tsx                  NEW — full backup & restore page
```

**Frontend — modified:**
```
admin-ui/src/App.tsx                MODIFY — import BackupPage + add route
admin-ui/src/components/
└── AppSidebar.tsx                  MODIFY — enable Backup & Restore sidebar item
```

**Tests — new:**
```
tests/test_admin_backup.py          NEW — integration tests for all 6 endpoints
```

---

## Chunk 1: Backend — schemas + router + mounting

### Task 1: Backend schemas

**Files:**
- Create: `src/flexloop/admin/schemas/backup.py`

- [ ] **Step 1: Create the backup response and upload schemas**

```python
"""Admin backup schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class BackupResponse(BaseModel):
    filename: str
    size_bytes: int
    created_at: datetime


class BackupRestoreResponse(BaseModel):
    status: str
    restored_from: str
    safety_backup: str
```

- [ ] **Step 2: Commit**

```bash
git add src/flexloop/admin/schemas/backup.py
git commit -m "feat(admin): add backup response schemas for phase 5a"
```

---

### Task 2: Backend router — list and create endpoints

**Files:**
- Create: `src/flexloop/admin/routers/backup.py`
- Test: `tests/test_admin_backup.py`

- [ ] **Step 1: Write failing tests for list and create**

```python
"""Integration tests for /api/admin/backups."""
from __future__ import annotations

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


class TestListBackups:
    async def test_auth(self, client: AsyncClient) -> None:
        assert (await client.get("/api/admin/backups")).status_code == 401

    async def test_list_empty(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        res = await client.get("/api/admin/backups", cookies=cookies)
        assert res.status_code == 200
        assert res.json() == []


class TestCreateBackup:
    async def test_auth(self, client: AsyncClient) -> None:
        assert (await client.post("/api/admin/backups")).status_code == 401

    async def test_create(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        res = await client.post(
            "/api/admin/backups", cookies=cookies, headers=ORIGIN,
        )
        assert res.status_code == 201
        body = res.json()
        assert body["filename"].startswith("flexloop_backup_")
        assert body["size_bytes"] > 0

        # Verify it shows up in the list
        res2 = await client.get("/api/admin/backups", cookies=cookies)
        assert len(res2.json()) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd flexloop-server && uv run pytest tests/test_admin_backup.py -v`
Expected: FAIL (import error — router doesn't exist yet)

- [ ] **Step 3: Create the router with list and create endpoints**

```python
"""Admin backup endpoints.

Wraps the existing ``BackupService`` with admin auth, audit logging,
download streaming, and multipart upload. The non-admin backup routes
in ``flexloop.routers.backup`` remain unchanged.

The list endpoint scans ``*.db`` in the backup directory (not just
``flexloop_backup_*.db``) so that uploaded files with custom names
are visible. All ``/{filename}`` endpoints validate the filename
for path-traversal safety.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.audit import write_audit_log
from flexloop.admin.auth import require_admin
from flexloop.admin.schemas.backup import BackupResponse, BackupRestoreResponse
from flexloop.config import settings
from flexloop.db.engine import _run_migrations, get_session
from flexloop.services.backup import BackupService

router = APIRouter(prefix="/api/admin/backups", tags=["admin:backups"])

_MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB


def _get_backup_service() -> BackupService:
    db_path = settings.database_url.replace("sqlite+aiosqlite:///", "")
    return BackupService(db_path=db_path, backup_dir="backups")


def _validate_filename(filename: str) -> None:
    """Reject path-traversal attempts and non-.db files."""
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(422, "invalid filename")
    if not filename.endswith(".db"):
        raise HTTPException(422, "filename must end with .db")


@router.get("", response_model=list[BackupResponse])
async def list_backups(
    _admin=Depends(require_admin),
) -> list[dict]:
    """List all *.db files in the backup directory, sorted newest first.

    Uses a direct directory scan instead of BackupService.list_backups()
    which only finds ``flexloop_backup_*.db`` files. This ensures uploaded
    files with custom names are visible.
    """
    svc = _get_backup_service()
    svc.backup_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(svc.backup_dir.glob("*.db"), key=lambda f: f.stat().st_mtime, reverse=True)
    return [
        {
            "filename": f.name,
            "size_bytes": f.stat().st_size,
            "created_at": datetime.fromtimestamp(f.stat().st_mtime),
        }
        for f in files
    ]


@router.post("", response_model=BackupResponse, status_code=201)
async def create_backup(
    db: AsyncSession = Depends(get_session),
    admin=Depends(require_admin),
) -> dict:
    svc = _get_backup_service()
    info = svc.create_backup(schema_version="1.0.0")
    await write_audit_log(
        db,
        admin_user_id=admin.id,
        action="backup_create",
        target_type="backup",
        target_id=info.filename,
    )
    await db.commit()
    return {
        "filename": info.filename,
        "size_bytes": info.size_bytes,
        "created_at": info.created_at,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd flexloop-server && uv run pytest tests/test_admin_backup.py -v`
Expected: FAIL (router not mounted yet — 404s)

- [ ] **Step 5: Mount the router in main.py**

In `src/flexloop/main.py`, add the import alongside the other admin router imports:

```python
from flexloop.admin.routers.backup import router as admin_backup_router
```

And add the include alongside the other admin includes:

```python
app.include_router(admin_backup_router)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd flexloop-server && uv run pytest tests/test_admin_backup.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/flexloop/admin/routers/backup.py src/flexloop/main.py tests/test_admin_backup.py
git commit -m "feat(admin): add backup list + create endpoints with audit logging"
```

---

### Task 3: Backend router — download endpoint

**Files:**
- Modify: `src/flexloop/admin/routers/backup.py`
- Modify: `tests/test_admin_backup.py`

- [ ] **Step 1: Write failing test for download**

Append to `tests/test_admin_backup.py`:

```python
class TestDownloadBackup:
    async def test_auth(self, client: AsyncClient) -> None:
        assert (await client.get("/api/admin/backups/x.db/download")).status_code == 401

    async def test_download(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        # Create a backup first
        res = await client.post(
            "/api/admin/backups", cookies=cookies, headers=ORIGIN,
        )
        filename = res.json()["filename"]

        res2 = await client.get(
            f"/api/admin/backups/{filename}/download", cookies=cookies,
        )
        assert res2.status_code == 200
        assert res2.headers["content-type"] == "application/octet-stream"
        assert len(res2.content) > 0

    async def test_download_not_found(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        res = await client.get(
            "/api/admin/backups/nonexistent.db/download", cookies=cookies,
        )
        assert res.status_code == 404
```

- [ ] **Step 2: Run tests to verify the new tests fail**

Run: `cd flexloop-server && uv run pytest tests/test_admin_backup.py::TestDownloadBackup -v`
Expected: FAIL (endpoint not defined)

- [ ] **Step 3: Add the download endpoint**

Append to the router in `src/flexloop/admin/routers/backup.py`:

```python
@router.get("/{filename}/download")
async def download_backup(
    filename: str,
    _admin=Depends(require_admin),
) -> FileResponse:
    _validate_filename(filename)
    svc = _get_backup_service()
    filepath = svc.backup_dir / filename
    if not filepath.exists():
        raise HTTPException(404, "backup not found")
    return FileResponse(
        filepath,
        media_type="application/octet-stream",
        filename=filename,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd flexloop-server && uv run pytest tests/test_admin_backup.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/flexloop/admin/routers/backup.py tests/test_admin_backup.py
git commit -m "feat(admin): add backup download endpoint"
```

---

### Task 4: Backend router — upload endpoint

**Files:**
- Modify: `src/flexloop/admin/routers/backup.py`
- Modify: `tests/test_admin_backup.py`

- [ ] **Step 1: Write failing tests for upload**

Append to `tests/test_admin_backup.py`:

```python
class TestUploadBackup:
    async def test_auth(self, client: AsyncClient) -> None:
        assert (await client.post("/api/admin/backups/upload")).status_code == 401

    async def test_upload(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        fake_db = b"SQLite format 3\x00" + b"\x00" * 100
        res = await client.post(
            "/api/admin/backups/upload",
            cookies=cookies,
            headers=ORIGIN,
            files={"file": ("my_backup.db", fake_db, "application/octet-stream")},
        )
        assert res.status_code == 201
        assert res.json()["filename"] == "my_backup.db"

        # Should appear in list
        res2 = await client.get("/api/admin/backups", cookies=cookies)
        filenames = [b["filename"] for b in res2.json()]
        assert "my_backup.db" in filenames

    async def test_upload_duplicate(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        fake_db = b"SQLite format 3\x00" + b"\x00" * 100
        await client.post(
            "/api/admin/backups/upload",
            cookies=cookies, headers=ORIGIN,
            files={"file": ("dup.db", fake_db, "application/octet-stream")},
        )
        res = await client.post(
            "/api/admin/backups/upload",
            cookies=cookies, headers=ORIGIN,
            files={"file": ("dup.db", fake_db, "application/octet-stream")},
        )
        assert res.status_code == 409

    async def test_upload_invalid_extension(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        res = await client.post(
            "/api/admin/backups/upload",
            cookies=cookies, headers=ORIGIN,
            files={"file": ("bad.txt", b"hello", "application/octet-stream")},
        )
        assert res.status_code == 422

    async def test_upload_path_traversal(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        res = await client.post(
            "/api/admin/backups/upload",
            cookies=cookies, headers=ORIGIN,
            files={"file": ("../evil.db", b"x", "application/octet-stream")},
        )
        assert res.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd flexloop-server && uv run pytest tests/test_admin_backup.py::TestUploadBackup -v`
Expected: FAIL

- [ ] **Step 3: Add the upload endpoint**

Append to `src/flexloop/admin/routers/backup.py` (all imports are already at the top from Task 2):

```python
@router.post("/upload", response_model=BackupResponse, status_code=201)
async def upload_backup(
    file: UploadFile,
    db: AsyncSession = Depends(get_session),
    admin=Depends(require_admin),
) -> dict:
    filename = file.filename or "upload.db"
    _validate_filename(filename)

    svc = _get_backup_service()
    dest = svc.backup_dir / filename
    if dest.exists():
        raise HTTPException(409, "backup with this filename already exists")

    total = 0
    with open(dest, "wb") as f:
        while chunk := await file.read(64 * 1024):
            total += len(chunk)
            if total > _MAX_UPLOAD_BYTES:
                dest.unlink(missing_ok=True)
                raise HTTPException(413, "file too large (max 200 MB)")
            f.write(chunk)

    stat = dest.stat()
    await write_audit_log(
        db,
        admin_user_id=admin.id,
        action="backup_upload",
        target_type="backup",
        target_id=filename,
        after={"size_bytes": stat.st_size},
    )
    await db.commit()

    return {
        "filename": filename,
        "size_bytes": stat.st_size,
        "created_at": datetime.fromtimestamp(stat.st_mtime),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd flexloop-server && uv run pytest tests/test_admin_backup.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/flexloop/admin/routers/backup.py tests/test_admin_backup.py
git commit -m "feat(admin): add backup upload endpoint with validation"
```

---

### Task 5: Backend router — restore endpoint

**Files:**
- Modify: `src/flexloop/admin/routers/backup.py`
- Modify: `tests/test_admin_backup.py`

- [ ] **Step 1: Write failing tests for restore**

Append to `tests/test_admin_backup.py`:

```python
class TestRestoreBackup:
    async def test_auth(self, client: AsyncClient) -> None:
        assert (await client.post("/api/admin/backups/x.db/restore")).status_code == 401

    async def test_restore(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        # Create a backup
        res = await client.post(
            "/api/admin/backups", cookies=cookies, headers=ORIGIN,
        )
        filename = res.json()["filename"]

        res2 = await client.post(
            f"/api/admin/backups/{filename}/restore",
            cookies=cookies, headers=ORIGIN,
        )
        assert res2.status_code == 200
        body = res2.json()
        assert body["status"] == "restored"
        assert body["restored_from"] == filename
        assert body["safety_backup"].startswith("flexloop_backup_")

    async def test_restore_not_found(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        res = await client.post(
            "/api/admin/backups/nonexistent.db/restore",
            cookies=cookies, headers=ORIGIN,
        )
        assert res.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd flexloop-server && uv run pytest tests/test_admin_backup.py::TestRestoreBackup -v`
Expected: FAIL

- [ ] **Step 3: Add the restore endpoint**

Append to `src/flexloop/admin/routers/backup.py` (all imports are already at the top from Task 2):

```python
@router.post("/{filename}/restore", response_model=BackupRestoreResponse)
async def restore_backup(
    filename: str,
    db: AsyncSession = Depends(get_session),
    admin=Depends(require_admin),
) -> dict:
    _validate_filename(filename)
    svc = _get_backup_service()
    if not (svc.backup_dir / filename).exists():
        raise HTTPException(404, "backup not found")

    # Write the audit log BEFORE the restore. After restore, the DB file
    # is replaced and the current session's connection is stale.
    await write_audit_log(
        db,
        admin_user_id=admin.id,
        action="backup_restore",
        target_type="backup",
        target_id=filename,
    )
    await db.commit()

    # Capture filenames before restore to identify the safety backup.
    existing = {f.name for f in svc.backup_dir.glob("*.db")}

    success = svc.restore(filename)
    if not success:
        raise HTTPException(404, "backup not found")

    # Run migrations on restored DB (may be older schema)
    try:
        _run_migrations()
    except Exception:
        pass  # best-effort — don't fail the restore

    # Find the safety backup (the new file that wasn't there before)
    after = {f.name for f in svc.backup_dir.glob("*.db")}
    safety_filename = next(iter(after - existing), "unknown")

    return {
        "status": "restored",
        "restored_from": filename,
        "safety_backup": safety_filename,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd flexloop-server && uv run pytest tests/test_admin_backup.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/flexloop/admin/routers/backup.py tests/test_admin_backup.py
git commit -m "feat(admin): add backup restore endpoint with safety backup + migrations"
```

---

### Task 6: Backend router — delete endpoint

**Files:**
- Modify: `src/flexloop/admin/routers/backup.py`
- Modify: `tests/test_admin_backup.py`

- [ ] **Step 1: Write failing tests for delete**

Append to `tests/test_admin_backup.py`:

```python
class TestDeleteBackup:
    async def test_auth(self, client: AsyncClient) -> None:
        assert (await client.delete("/api/admin/backups/x.db")).status_code == 401

    async def test_delete(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        # Create a backup
        res = await client.post(
            "/api/admin/backups", cookies=cookies, headers=ORIGIN,
        )
        filename = res.json()["filename"]

        res2 = await client.delete(
            f"/api/admin/backups/{filename}",
            cookies=cookies, headers=ORIGIN,
        )
        assert res2.status_code == 204

        # Verify it's gone from the list
        res3 = await client.get("/api/admin/backups", cookies=cookies)
        filenames = [b["filename"] for b in res3.json()]
        assert filename not in filenames

    async def test_delete_not_found(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        res = await client.delete(
            "/api/admin/backups/nonexistent.db",
            cookies=cookies, headers=ORIGIN,
        )
        assert res.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd flexloop-server && uv run pytest tests/test_admin_backup.py::TestDeleteBackup -v`
Expected: FAIL

- [ ] **Step 3: Add the delete endpoint**

Append to `src/flexloop/admin/routers/backup.py`:

```python
@router.delete("/{filename}", status_code=204)
async def delete_backup(
    filename: str,
    db: AsyncSession = Depends(get_session),
    admin=Depends(require_admin),
) -> None:
    _validate_filename(filename)
    svc = _get_backup_service()
    filepath = svc.backup_dir / filename
    if not filepath.exists():
        raise HTTPException(404, "backup not found")
    filepath.unlink()
    await write_audit_log(
        db,
        admin_user_id=admin.id,
        action="backup_delete",
        target_type="backup",
        target_id=filename,
    )
    await db.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd flexloop-server && uv run pytest tests/test_admin_backup.py -v`
Expected: PASS

- [ ] **Step 5: Run the full test suite to check for regressions**

Run: `cd flexloop-server && uv run pytest -x -q`
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add src/flexloop/admin/routers/backup.py tests/test_admin_backup.py
git commit -m "feat(admin): add backup delete endpoint, complete backend"
```

---

## Chunk 2: Frontend — BackupPage + routing + sidebar

### Task 7: Enable sidebar item and add route

**Files:**
- Modify: `admin-ui/src/components/AppSidebar.tsx`
- Modify: `admin-ui/src/App.tsx`

- [ ] **Step 1: Enable the Backup & Restore sidebar item**

In `admin-ui/src/components/AppSidebar.tsx`, change line 75:

```typescript
// Before:
{ label: "Backup & Restore", to: "/ops/backup", icon: HardDriveDownload, disabled: true },
// After:
{ label: "Backup & Restore", to: "/ops/backup", icon: HardDriveDownload },
```

- [ ] **Step 2: Add the route in App.tsx**

In `admin-ui/src/App.tsx`, add the import:

```typescript
import { BackupPage } from "@/pages/BackupPage";
```

Add the route inside the authenticated layout, after the `admin-users` route:

```typescript
<Route path="ops/backup" element={<BackupPage />} />
```

- [ ] **Step 3: Create a placeholder BackupPage**

Create `admin-ui/src/pages/BackupPage.tsx` with a minimal placeholder so the app compiles:

```tsx
export function BackupPage() {
  return <div className="p-6"><h1 className="text-2xl font-semibold">Backup & Restore</h1></div>;
}
```

- [ ] **Step 4: Verify the frontend builds**

Run: `cd flexloop-server/admin-ui && npm run build`
Expected: build succeeds

- [ ] **Step 5: Commit**

```bash
git add admin-ui/src/components/AppSidebar.tsx admin-ui/src/App.tsx admin-ui/src/pages/BackupPage.tsx
git commit -m "feat(admin): wire up Backup & Restore route and sidebar item"
```

---

### Task 8: BackupPage — backup table and create button

**Files:**
- Modify: `admin-ui/src/pages/BackupPage.tsx`

- [ ] **Step 1: Implement the backup table with create functionality**

Replace `admin-ui/src/pages/BackupPage.tsx` with:

```tsx
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { toast } from "sonner";
import { HardDriveDownload, Plus, Trash2, RotateCcw } from "lucide-react";

type Backup = {
  filename: string;
  size_bytes: number;
  created_at: string;
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatAge(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

export function BackupPage() {
  const qc = useQueryClient();

  const { data: backups = [], isLoading } = useQuery({
    queryKey: ["admin", "backups"],
    queryFn: () => api.get<Backup[]>("/api/admin/backups"),
  });

  const createMut = useMutation({
    mutationFn: () => api.post<Backup>("/api/admin/backups"),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["admin", "backups"] });
      toast.success(`Backup created: ${data.filename}`);
    },
    onError: () => toast.error("Failed to create backup"),
  });

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Backup & Restore</h1>
        <div className="flex gap-2">
          {/* Upload drop zone will be added in Task 9 */}
          <Button
            onClick={() => createMut.mutate()}
            disabled={createMut.isPending}
          >
            <Plus className="h-4 w-4 mr-2" />
            {createMut.isPending ? "Creating…" : "Create backup"}
          </Button>
        </div>
      </div>

      {isLoading ? (
        <p className="text-muted-foreground">Loading…</p>
      ) : backups.length === 0 ? (
        <p className="text-muted-foreground">No backups yet.</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Filename</TableHead>
              <TableHead>Size</TableHead>
              <TableHead>Created</TableHead>
              <TableHead>Age</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {backups.map((b) => (
              <TableRow key={b.filename}>
                <TableCell className="font-mono text-sm">{b.filename}</TableCell>
                <TableCell>{formatBytes(b.size_bytes)}</TableCell>
                <TableCell>
                  {new Date(b.created_at).toLocaleString()}
                </TableCell>
                <TableCell>{formatAge(b.created_at)}</TableCell>
                <TableCell className="text-right space-x-1">
                  {/* Download, Restore, Delete buttons added in Tasks 9-10 */}
                  <Button variant="ghost" size="icon" asChild>
                    <a
                      href={`/api/admin/backups/${b.filename}/download`}
                      download
                    >
                      <HardDriveDownload className="h-4 w-4" />
                    </a>
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify the frontend builds**

Run: `cd flexloop-server/admin-ui && npm run build`
Expected: build succeeds

- [ ] **Step 3: Commit**

```bash
git add admin-ui/src/pages/BackupPage.tsx
git commit -m "feat(admin): backup table with create + download + list"
```

---

### Task 9: BackupPage — upload drop zone

**Files:**
- Modify: `admin-ui/src/pages/BackupPage.tsx`

- [ ] **Step 1: Add the upload drop zone and mutation**

Add the upload mutation and drop zone to `BackupPage.tsx`. Add the following inside the component, after the `createMut`:

```tsx
const [dragOver, setDragOver] = useState(false);

const uploadMut = useMutation({
  mutationFn: async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch("/api/admin/backups/upload", {
      method: "POST",
      credentials: "include",
      body: form,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail);
    }
    return res.json();
  },
  onSuccess: (data) => {
    qc.invalidateQueries({ queryKey: ["admin", "backups"] });
    toast.success(`Uploaded: ${data.filename}`);
  },
  onError: (err: Error) => toast.error(`Upload failed: ${err.message}`),
});

function handleDrop(e: React.DragEvent) {
  e.preventDefault();
  setDragOver(false);
  const file = e.dataTransfer.files[0];
  if (file) uploadMut.mutate(file);
}

function handleFileInput(e: React.ChangeEvent<HTMLInputElement>) {
  const file = e.target.files?.[0];
  if (file) uploadMut.mutate(file);
  e.target.value = "";
}
```

Add the drop zone UI between the header and the table:

```tsx
<div
  onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
  onDragLeave={() => setDragOver(false)}
  onDrop={handleDrop}
  className={`border-2 border-dashed rounded-lg p-6 text-center transition-colors ${
    dragOver ? "border-primary bg-primary/5" : "border-muted-foreground/25"
  }`}
>
  <p className="text-sm text-muted-foreground">
    Drag & drop a <code>.db</code> backup file here, or{" "}
    <label className="text-primary cursor-pointer underline">
      browse
      <input
        type="file"
        accept=".db"
        className="hidden"
        onChange={handleFileInput}
      />
    </label>
  </p>
  {uploadMut.isPending && (
    <p className="text-sm text-muted-foreground mt-2">Uploading…</p>
  )}
</div>
```

- [ ] **Step 2: Verify the frontend builds**

Run: `cd flexloop-server/admin-ui && npm run build`
Expected: build succeeds

- [ ] **Step 3: Commit**

```bash
git add admin-ui/src/pages/BackupPage.tsx
git commit -m "feat(admin): add drag-and-drop backup upload zone"
```

---

### Task 10: BackupPage — restore (type-to-confirm) and delete dialogs

**Files:**
- Modify: `admin-ui/src/pages/BackupPage.tsx`

- [ ] **Step 1: Add restore and delete mutations + dialogs**

Add the following state, mutations, and dialog components to `BackupPage.tsx`.

State (add alongside existing state):

```tsx
const [restoreTarget, setRestoreTarget] = useState<Backup | null>(null);
const [restoreConfirmText, setRestoreConfirmText] = useState("");
const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
```

Mutations (add after uploadMut):

```tsx
const restoreMut = useMutation({
  mutationFn: (filename: string) =>
    api.post<{ status: string; restored_from: string; safety_backup: string }>(
      `/api/admin/backups/${filename}/restore`,
    ),
  onSuccess: (data) => {
    qc.invalidateQueries({ queryKey: ["admin", "backups"] });
    toast.success(
      `Restored from ${data.restored_from}. Safety backup: ${data.safety_backup}`,
    );
    setRestoreTarget(null);
    setRestoreConfirmText("");
  },
  onError: () => { toast.error("Restore failed"); setRestoreTarget(null); },
});

const deleteMut = useMutation({
  mutationFn: (filename: string) =>
    api.delete(`/api/admin/backups/${filename}`),
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: ["admin", "backups"] });
    toast.success("Backup deleted");
    setDeleteTarget(null);
  },
  onError: () => toast.error("Delete failed"),
});
```

Add Restore and Delete buttons to the per-row actions cell (alongside the existing Download button):

```tsx
<Button
  variant="ghost"
  size="icon"
  onClick={() => setRestoreTarget(b)}
>
  <RotateCcw className="h-4 w-4" />
</Button>
<Button
  variant="ghost"
  size="icon"
  onClick={() => setDeleteTarget(b.filename)}
>
  <Trash2 className="h-4 w-4" />
</Button>
```

Add the dialog imports at the top:

```tsx
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
```

Add the dialogs at the bottom of the component JSX (before the closing `</div>`):

```tsx
{/* Restore — type-to-confirm */}
<AlertDialog
  open={restoreTarget !== null}
  onOpenChange={(open) => {
    if (!open) { setRestoreTarget(null); setRestoreConfirmText(""); }
  }}
>
  <AlertDialogContent>
    <AlertDialogHeader>
      <AlertDialogTitle>Restore backup?</AlertDialogTitle>
      <AlertDialogDescription>
        This will replace the current database with{" "}
        <code className="font-mono">{restoreTarget?.filename}</code>{" "}
        ({restoreTarget ? formatBytes(restoreTarget.size_bytes) : ""},{" "}
        created {restoreTarget ? formatAge(restoreTarget.created_at) : ""}).
        A safety backup of the current state will be created first.
        Type the backup filename to confirm.
      </AlertDialogDescription>
    </AlertDialogHeader>
    <Input
      value={restoreConfirmText}
      onChange={(e) => setRestoreConfirmText(e.target.value)}
      placeholder={restoreTarget?.filename ?? ""}
      className="font-mono text-sm"
    />
    <AlertDialogFooter>
      <AlertDialogCancel>Cancel</AlertDialogCancel>
      <AlertDialogAction
        disabled={restoreConfirmText !== restoreTarget?.filename || restoreMut.isPending}
        onClick={() => restoreTarget && restoreMut.mutate(restoreTarget.filename)}
      >
        {restoreMut.isPending ? "Restoring…" : "Restore"}
      </AlertDialogAction>
    </AlertDialogFooter>
  </AlertDialogContent>
</AlertDialog>

{/* Delete — simple confirm */}
<AlertDialog
  open={deleteTarget !== null}
  onOpenChange={(open) => { if (!open) setDeleteTarget(null); }}
>
  <AlertDialogContent>
    <AlertDialogHeader>
      <AlertDialogTitle>Delete backup?</AlertDialogTitle>
      <AlertDialogDescription>
        This will permanently delete{" "}
        <code className="font-mono">{deleteTarget}</code>. This action
        cannot be undone.
      </AlertDialogDescription>
    </AlertDialogHeader>
    <AlertDialogFooter>
      <AlertDialogCancel>Cancel</AlertDialogCancel>
      <AlertDialogAction
        disabled={deleteMut.isPending}
        onClick={() => deleteTarget && deleteMut.mutate(deleteTarget)}
      >
        {deleteMut.isPending ? "Deleting…" : "Delete"}
      </AlertDialogAction>
    </AlertDialogFooter>
  </AlertDialogContent>
</AlertDialog>
```

- [ ] **Step 2: Verify the frontend builds**

Run: `cd flexloop-server/admin-ui && npm run build`
Expected: build succeeds

- [ ] **Step 3: Commit**

```bash
git add admin-ui/src/pages/BackupPage.tsx
git commit -m "feat(admin): add restore (type-to-confirm) and delete dialogs"
```

---

### Task 11: Final verification

- [ ] **Step 1: Run the full backend test suite**

Run: `cd flexloop-server && uv run pytest -x -q`
Expected: all tests pass (including the new test_admin_backup.py tests)

- [ ] **Step 2: Build the frontend**

Run: `cd flexloop-server/admin-ui && npm run build`
Expected: build succeeds, bundle under 1 MB gzipped

- [ ] **Step 3: Verify bundle size**

Run: `ls -lh flexloop-server/admin-ui/dist/assets/*.js | head -5`
Expected: JS bundles are reasonable size

- [ ] **Step 4: Quick manual smoke test** (optional — if dev server is available)

Start the backend: `cd flexloop-server && uv run uvicorn flexloop.main:app --port 8000`

Check:
- Navigate to `/admin/ops/backup`
- Sidebar shows "Backup & Restore" as active (not disabled)
- "Create backup" button works
- Backup appears in the table with filename, size, date, age
- Download button triggers a file download
- Upload via drag-and-drop works
- Restore shows type-to-confirm dialog
- Delete shows confirmation dialog

- [ ] **Step 5: Final commit if any adjustments were needed**

Stage only the specific files that were changed. Skip this step if no adjustments were needed.

```bash
git add src/flexloop/admin/routers/backup.py admin-ui/src/pages/BackupPage.tsx
git commit -m "chore(admin): phase 5a final adjustments"
```
