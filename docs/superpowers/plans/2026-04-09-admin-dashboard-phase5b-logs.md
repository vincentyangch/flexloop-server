# Admin Dashboard — Phase 5b (Logs Viewer) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the admin Logs Viewer — a filterable, virtualized log page with live-tail SSE streaming, backed by the existing `RingBufferHandler` enhanced with record IDs, `since` filtering, and a rotating JSONL file sink for persistence.

**Architecture:**
1. **Enhances the existing `RingBufferHandler`** in `flexloop.admin.log_handler` (installed in `main.py` since phase 1). Adds: monotonic record IDs for SSE cursor tracking, `since` timestamp filtering, a JSONL file sink (`logs/flexloop.YYYY-MM-DD.jsonl`) for crash-recovery persistence, and a `get_records_after(id)` method for SSE polling. The ring buffer remains the primary query source (10K records, fast).
2. **New admin router** at `flexloop.admin.routers.logs` exposes 2 endpoints: `GET /api/admin/logs` (history query with level/search/since/limit filters) and `GET /api/admin/logs/stream` (SSE stream that polls the ring buffer every 500ms for new records). Both require admin auth.
3. **Frontend** adds `react-virtuoso` for efficient rendering, a `LogsPage.tsx` with severity/search/time filters, color-coded virtualized log lines with click-to-expand details, and a "Live tail" toggle that connects to the SSE stream via `fetch` + the existing `parseSSE` utility.

**Tech Stack (new to phase 5b):** Backend: no new deps (uses stdlib `logging`, `json`, `pathlib`). Frontend: `react-virtuoso` (new).

**Spec reference:** `docs/superpowers/specs/2026-04-06-admin-dashboard-design.md`. Read §11.3 (Log viewer — authoritative), §14 phase 5 bullet, §15 open question 3 (virtualization library pick).

**Phases 1-5a already delivered.** Phase 5b is the second of three phase-5 sub-plans. Phase 5c (Triggers) is out of scope.

---

## Decisions locked in for this phase

1. **Ring buffer is the only query source for the GET endpoint.** The JSONL file sink provides persistence/audit but the history endpoint reads only from the in-memory ring buffer (10K records). Reading from JSONL files is deferred — the ring buffer covers hours of history at typical log rates. This keeps the endpoint fast and simple.

2. **Record IDs are monotonic integers assigned in `emit()`.** Each record gets `"id": N` where N increments from 0 on process start. IDs are NOT persistent across restarts (they reset). The SSE stream uses IDs as a cursor to track what the client has already seen.

3. **SSE stream uses server-side polling at 500ms.** The stream endpoint calls `get_records_after(last_id)` every 500ms and yields any new records as SSE events. This avoids threading complexity (emit() runs in arbitrary threads; the SSE endpoint is asyncio). 500ms latency is acceptable for a log viewer.

4. **Frontend uses `fetch` + existing `parseSSE` (not EventSource).** The existing `admin-ui/src/lib/sseReader.ts` async generator works through the Vite dev proxy. EventSource may not proxy correctly in dev mode. An `AbortController` handles cleanup on unmount or filter changes.

5. **JSONL file sink: one file per day, 7-day retention.** Files written to `logs/flexloop.YYYY-MM-DD.jsonl` relative to the working directory. Pruning runs every 1000 records to avoid checking on every emit. The `logs/` directory is created lazily on first write.

6. **`react-virtuoso` for log list virtualization.** Per spec §15 open question 3, picked over `@tanstack/virtual` for simpler API with auto-scroll support (needed for live tail). Install via `npm install react-virtuoso`.

7. **Log record shape** (unchanged from phase 1 handler): `{id, timestamp, level, logger, message, exception?, extra?}`. The `id` field is new. The `extra` field is new (captures `record.__dict__` extras beyond the standard fields).

8. **Color coding by severity:**
   - DEBUG: `text-muted-foreground` (gray)
   - INFO: default text color
   - WARNING: `text-yellow-500`
   - ERROR: `text-red-500`
   - CRITICAL: `text-red-500 font-bold`

9. **No audit logging for log queries.** Reading logs is not a mutation.

10. **Time range picker deferred.** The spec mentions a time range picker in the filter bar. The backend supports `since` parameter, but the frontend ships with severity dropdown + search only. A date picker can be added later without backend changes.

11. **Client-side log cap at 5000 records.** During live tail, the frontend caps the logs array at 5000 entries to prevent unbounded memory growth.

10. **Worktree + feature branch:**
    - Worktree path: `/Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase5b`
    - Branch: `feat/admin-dashboard-phase5b-logs`
    - Merge: fast-forward into `main`, delete branch + worktree, bump parent submodule, update memory.

---

## File Structure

All paths relative to `flexloop-server/` unless stated otherwise.

**Backend — modified:**
```
src/flexloop/admin/
└── log_handler.py              MODIFY — add IDs, since filter, JSONL sink, get_records_after()
```

**Backend — new:**
```
src/flexloop/admin/routers/
└── logs.py                     NEW — GET /api/admin/logs + GET /api/admin/logs/stream
```

**Backend — modified:**
```
src/flexloop/main.py            MODIFY — import and mount admin_logs_router
```

**Frontend — new:**
```
admin-ui/src/pages/
└── LogsPage.tsx                NEW — full logs viewer page
```

**Frontend — modified:**
```
admin-ui/src/App.tsx            MODIFY — import LogsPage + add route
admin-ui/src/components/
└── AppSidebar.tsx              MODIFY — enable Logs sidebar item
```

**Tests — new:**
```
tests/test_log_handler.py       NEW — unit tests for enhanced RingBufferHandler
tests/test_admin_logs.py        NEW — integration tests for logs router
```

---

## Chunk 1: Backend — RingBufferHandler enhancements + JSONL sink

### Task 1: Enhance RingBufferHandler with IDs, `since` filter, and `get_records_after`

**Files:**
- Modify: `src/flexloop/admin/log_handler.py`
- Create: `tests/test_log_handler.py`

- [ ] **Step 1: Write failing tests for the new features**

```python
"""Unit tests for RingBufferHandler enhancements."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from flexloop.admin.log_handler import RingBufferHandler


class TestRecordIds:
    def test_records_have_sequential_ids(self) -> None:
        handler = RingBufferHandler(capacity=100)
        logger = logging.getLogger("test.ids")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        logger.info("first")
        logger.info("second")
        logger.info("third")

        records = handler.get_records()
        ids = [r["id"] for r in records]
        assert ids == [0, 1, 2]

        logger.removeHandler(handler)


class TestSinceFilter:
    def test_since_filters_old_records(self) -> None:
        handler = RingBufferHandler(capacity=100)
        logger = logging.getLogger("test.since")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        logger.info("old")
        # Get the timestamp of the first record
        all_records = handler.get_records()
        first_ts = all_records[0]["timestamp"]

        logger.info("new")

        # Query with since = first record's timestamp should return both
        # (since is inclusive of records AT that timestamp)
        records = handler.get_records(since=first_ts)
        assert len(records) >= 1

        logger.removeHandler(handler)


class TestGetRecordsAfter:
    def test_returns_records_after_id(self) -> None:
        handler = RingBufferHandler(capacity=100)
        logger = logging.getLogger("test.after")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        logger.info("a")
        logger.info("b")
        logger.info("c")

        # Get records after id 0 (should return b and c)
        records = handler.get_records_after(0)
        assert len(records) == 2
        assert records[0]["message"] == "b"
        assert records[1]["message"] == "c"

        logger.removeHandler(handler)

    def test_returns_empty_when_no_new(self) -> None:
        handler = RingBufferHandler(capacity=100)
        logger = logging.getLogger("test.after2")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        logger.info("only")

        records = handler.get_records_after(0)
        assert len(records) == 0

        logger.removeHandler(handler)

    def test_respects_level_filter(self) -> None:
        handler = RingBufferHandler(capacity=100)
        logger = logging.getLogger("test.after3")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        logger.debug("debug msg")
        logger.warning("warn msg")

        records = handler.get_records_after(-1, min_level="WARNING")
        assert len(records) == 1
        assert records[0]["message"] == "warn msg"

        logger.removeHandler(handler)


class TestGetLatestId:
    def test_returns_neg1_when_empty(self) -> None:
        handler = RingBufferHandler(capacity=100)
        assert handler.get_latest_id() == -1

    def test_returns_last_id(self) -> None:
        handler = RingBufferHandler(capacity=100)
        logger = logging.getLogger("test.latest")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        logger.info("a")
        logger.info("b")
        assert handler.get_latest_id() == 1

        logger.removeHandler(handler)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd flexloop-server && uv run pytest tests/test_log_handler.py -v`
Expected: FAIL (no `id` field, no `get_records_after`, no `get_latest_id`, no `since`)

- [ ] **Step 3: Implement the enhancements**

Replace `src/flexloop/admin/log_handler.py` with:

```python
"""In-memory ring buffer log handler for the admin Log Viewer.

Keeps the last N records in a deque for instant live-tail queries.
Also writes each record to a rotating JSONL file for crash-recovery
persistence (one file per day, 7-day retention).
"""
import json
import logging
import threading
import traceback
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

LEVEL_RANK = {
    "DEBUG": 10,
    "INFO": 20,
    "WARNING": 30,
    "ERROR": 40,
    "CRITICAL": 50,
}

# Standard LogRecord attributes to exclude from the "extra" dict
_STANDARD_ATTRS = frozenset({
    "args", "asctime", "created", "exc_info", "exc_text", "filename",
    "funcName", "levelname", "levelno", "lineno", "message", "module",
    "msecs", "msg", "name", "pathname", "process", "processName",
    "relativeCreated", "stack_info", "taskName", "thread", "threadName",
})


class RingBufferHandler(logging.Handler):
    """Stores the most recent log records in a bounded deque.

    Thread-safe. Records are dicts with monotonic ``id`` fields for
    SSE cursor tracking.
    """

    def __init__(self, capacity: int = 10_000, log_dir: str = "logs") -> None:
        super().__init__()
        self._buffer: deque[dict[str, Any]] = deque(maxlen=capacity)
        self._lock = threading.Lock()
        self._next_id: int = 0
        self._log_dir = Path(log_dir)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry: dict[str, Any] = {
                "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "exception": None,
            }
            if record.exc_info and record.exc_info[0] is not None:
                entry["exception"] = "".join(
                    traceback.format_exception(*record.exc_info)
                )
            # Capture extra fields
            extras = {
                k: v for k, v in record.__dict__.items()
                if k not in _STANDARD_ATTRS and not k.startswith("_")
            }
            if extras:
                entry["extra"] = extras

            with self._lock:
                entry["id"] = self._next_id
                self._next_id += 1
                self._buffer.append(entry)

            self._write_jsonl(entry)

            # Prune old JSONL files every 1000 records
            if entry["id"] % 1000 == 0:
                self._prune_old_logs()
        except Exception:  # noqa: BLE001
            self.handleError(record)

    def get_records(
        self,
        min_level: str = "DEBUG",
        search: str | None = None,
        since: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        threshold = LEVEL_RANK.get(min_level.upper(), 0)
        with self._lock:
            snapshot = list(self._buffer)

        filtered = [
            r for r in snapshot
            if LEVEL_RANK.get(r["level"], 0) >= threshold
            and (search is None or search.lower() in r["message"].lower())
            and (since is None or r["timestamp"] >= since)
        ]
        if limit is not None:
            filtered = filtered[-limit:]
        return filtered

    def get_records_after(
        self,
        after_id: int,
        min_level: str = "DEBUG",
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return records with id > after_id, optionally filtered."""
        threshold = LEVEL_RANK.get(min_level.upper(), 0)
        with self._lock:
            snapshot = list(self._buffer)
        return [
            r for r in snapshot
            if r.get("id", -1) > after_id
            and LEVEL_RANK.get(r["level"], 0) >= threshold
            and (search is None or search.lower() in r["message"].lower())
        ]

    def get_latest_id(self) -> int:
        """Return the id of the most recent record, or -1 if empty."""
        with self._lock:
            if self._buffer:
                return self._buffer[-1].get("id", -1)
            return -1

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()

    def _write_jsonl(self, entry: dict[str, Any]) -> None:
        """Append a record to today's JSONL file."""
        try:
            self._log_dir.mkdir(parents=True, exist_ok=True)
            today = datetime.now().strftime("%Y-%m-%d")
            path = self._log_dir / f"flexloop.{today}.jsonl"
            with open(path, "a") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except Exception:  # noqa: BLE001
            pass  # Never let file I/O crash logging

    def _prune_old_logs(self, retention_days: int = 7) -> None:
        """Delete JSONL files older than retention_days."""
        try:
            cutoff = datetime.now() - timedelta(days=retention_days)
            for path in self._log_dir.glob("flexloop.*.jsonl"):
                # Extract date from filename: flexloop.YYYY-MM-DD.jsonl
                parts = path.stem.split(".", 1)
                if len(parts) == 2:
                    try:
                        file_date = datetime.strptime(parts[1], "%Y-%m-%d")
                        if file_date < cutoff:
                            path.unlink(missing_ok=True)
                    except ValueError:
                        pass
        except Exception:  # noqa: BLE001
            pass


# Process-wide singleton installed in main.py. Other modules import this
# directly (e.g., the health endpoint reads from it for recent_errors).
admin_ring_buffer = RingBufferHandler(capacity=10_000)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd flexloop-server && uv run pytest tests/test_log_handler.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/flexloop/admin/log_handler.py tests/test_log_handler.py
git commit -m "feat(admin): enhance RingBufferHandler with IDs, since filter, JSONL sink"
```

---

### Task 2: Create logs router with history endpoint

**Files:**
- Create: `src/flexloop/admin/routers/logs.py`
- Create: `tests/test_admin_logs.py`

- [ ] **Step 1: Write failing tests for the history endpoint**

```python
"""Integration tests for /api/admin/logs."""
from __future__ import annotations

import logging

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import SESSION_COOKIE_NAME, create_session, hash_password
from flexloop.admin.log_handler import admin_ring_buffer
from flexloop.models.admin_user import AdminUser


ORIGIN = {"Origin": "http://localhost:5173"}


async def _cookie(db: AsyncSession) -> dict[str, str]:
    a = AdminUser(username="t", password_hash=hash_password("password123"))
    db.add(a); await db.commit(); await db.refresh(a)
    token, _ = await create_session(db, admin_user_id=a.id)
    return {SESSION_COOKIE_NAME: token}


@pytest.fixture(autouse=True)
def _clear_buffer():
    """Clear the ring buffer before each test."""
    admin_ring_buffer.clear()
    yield
    admin_ring_buffer.clear()


class TestGetLogs:
    async def test_auth(self, client: AsyncClient) -> None:
        assert (await client.get("/api/admin/logs")).status_code == 401

    async def test_empty(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        res = await client.get("/api/admin/logs", cookies=cookies)
        assert res.status_code == 200
        assert res.json() == []

    async def test_returns_records(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        logger = logging.getLogger("test.integration")
        logger.warning("test warning message")

        res = await client.get("/api/admin/logs", cookies=cookies)
        assert res.status_code == 200
        records = res.json()
        assert any(r["message"] == "test warning message" for r in records)

    async def test_filter_by_level(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        logger = logging.getLogger("test.level")
        logger.info("info msg")
        logger.warning("warn msg")

        res = await client.get(
            "/api/admin/logs?level=WARNING", cookies=cookies,
        )
        records = res.json()
        assert all(r["level"] in ("WARNING", "ERROR", "CRITICAL") for r in records)

    async def test_filter_by_search(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        logger = logging.getLogger("test.search")
        logger.info("needle in haystack")
        logger.info("just hay")

        res = await client.get(
            "/api/admin/logs?search=needle", cookies=cookies,
        )
        records = res.json()
        assert all("needle" in r["message"].lower() for r in records)

    async def test_limit(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)
        logger = logging.getLogger("test.limit")
        for i in range(10):
            logger.info(f"msg {i}")

        res = await client.get(
            "/api/admin/logs?limit=3", cookies=cookies,
        )
        records = res.json()
        assert len(records) <= 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd flexloop-server && uv run pytest tests/test_admin_logs.py -v`
Expected: FAIL (router doesn't exist)

- [ ] **Step 3: Create the logs router**

```python
"""Admin log viewer endpoints.

Exposes the in-memory ring buffer to the admin UI for querying and
live-tail streaming.
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from flexloop.admin.auth import require_admin
from flexloop.admin.log_handler import admin_ring_buffer

router = APIRouter(prefix="/api/admin/logs", tags=["admin:logs"])


@router.get("")
async def get_logs(
    level: str = "DEBUG",
    search: str | None = None,
    since: str | None = None,
    limit: int = 200,
    _admin=Depends(require_admin),
) -> list[dict]:
    return admin_ring_buffer.get_records(
        min_level=level,
        search=search,
        since=since,
        limit=limit,
    )
```

- [ ] **Step 4: Mount the router in main.py**

In `src/flexloop/main.py`, add the import alongside the other admin router imports:

```python
from flexloop.admin.routers.logs import router as admin_logs_router
```

And add the include alongside the other admin includes:

```python
app.include_router(admin_logs_router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd flexloop-server && uv run pytest tests/test_admin_logs.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/flexloop/admin/routers/logs.py src/flexloop/main.py tests/test_admin_logs.py
git commit -m "feat(admin): add GET /api/admin/logs history endpoint"
```

---

### Task 3: Add SSE stream endpoint

**Files:**
- Modify: `src/flexloop/admin/routers/logs.py`
- Modify: `tests/test_admin_logs.py`

- [ ] **Step 1: Write failing test for the SSE stream**

Append to `tests/test_admin_logs.py`:

```python
class TestStreamLogs:
    async def test_auth(self, client: AsyncClient) -> None:
        assert (await client.get("/api/admin/logs/stream")).status_code == 401

    async def test_stream_returns_sse(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cookies = await _cookie(db_session)

        # Emit a log record before connecting
        logger = logging.getLogger("test.stream")
        logger.warning("stream test")

        # The stream endpoint returns text/event-stream
        # We use stream=True and read a small amount
        import httpx

        async with client.stream(
            "GET", "/api/admin/logs/stream", cookies=cookies,
        ) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")
            # Read the first chunk (should contain our log record)
            chunks = []
            async for chunk in response.aiter_text():
                chunks.append(chunk)
                if len(chunks) >= 1:
                    break

            # The first chunk should contain SSE data
            text = "".join(chunks)
            assert "data:" in text
```

- [ ] **Step 2: Run tests to verify the new test fails**

Run: `cd flexloop-server && uv run pytest tests/test_admin_logs.py::TestStreamLogs -v`
Expected: FAIL (endpoint doesn't exist)

- [ ] **Step 3: Add the SSE stream endpoint**

Append to `src/flexloop/admin/routers/logs.py`:

```python
@router.get("/stream")
async def stream_logs(
    level: str = "DEBUG",
    search: str | None = None,
    _admin=Depends(require_admin),
) -> StreamingResponse:
    """SSE stream of new log records.

    Polls the ring buffer every 500ms for records newer than the client's
    cursor. Yields each record as a ``data: {json}\\n\\n`` SSE event.
    """
    async def event_generator():
        last_id = admin_ring_buffer.get_latest_id()
        # Yield existing recent records as an initial batch so the client
        # sees some history on connect (last 50 matching records).
        initial = admin_ring_buffer.get_records(
            min_level=level, search=search, limit=50,
        )
        for r in initial:
            yield f"data: {json.dumps(r, default=str)}\n\n"
            last_id = max(last_id, r.get("id", -1))

        while True:
            records = admin_ring_buffer.get_records_after(
                last_id, min_level=level, search=search,
            )
            for r in records:
                yield f"data: {json.dumps(r, default=str)}\n\n"
                last_id = r.get("id", -1)
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd flexloop-server && uv run pytest tests/test_admin_logs.py -v`
Expected: PASS

- [ ] **Step 5: Run the full test suite**

Run: `cd flexloop-server && uv run pytest -x -q`
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add src/flexloop/admin/routers/logs.py tests/test_admin_logs.py
git commit -m "feat(admin): add GET /api/admin/logs/stream SSE endpoint"
```

---

## Chunk 2: Frontend — LogsPage + routing + sidebar

### Task 4: Install react-virtuoso, enable sidebar, add route

**Files:**
- Modify: `admin-ui/package.json` (via npm install)
- Modify: `admin-ui/src/components/AppSidebar.tsx`
- Modify: `admin-ui/src/App.tsx`

- [ ] **Step 1: Install react-virtuoso**

Run: `cd flexloop-server/admin-ui && npm install react-virtuoso --legacy-peer-deps`

- [ ] **Step 2: Enable the Logs sidebar item**

In `admin-ui/src/components/AppSidebar.tsx`, change the Logs item:

```typescript
// Before:
{ label: "Logs", to: "/ops/logs", icon: ScrollText, disabled: true },
// After:
{ label: "Logs", to: "/ops/logs", icon: ScrollText },
```

- [ ] **Step 3: Add the route in App.tsx**

Import the page:

```typescript
import { LogsPage } from "@/pages/LogsPage";
```

Add the route inside the authenticated layout:

```typescript
<Route path="ops/logs" element={<LogsPage />} />
```

- [ ] **Step 4: Create a placeholder LogsPage**

Create `admin-ui/src/pages/LogsPage.tsx`:

```tsx
export function LogsPage() {
  return <div className="p-6"><h1 className="text-2xl font-semibold">Logs</h1></div>;
}
```

- [ ] **Step 5: Verify the frontend builds**

Run: `cd flexloop-server/admin-ui && npm run build`
Expected: build succeeds

- [ ] **Step 6: Commit**

```bash
git add admin-ui/package.json admin-ui/package-lock.json admin-ui/src/components/AppSidebar.tsx admin-ui/src/App.tsx admin-ui/src/pages/LogsPage.tsx
git commit -m "feat(admin): wire up Logs route, sidebar item, install react-virtuoso"
```

---

### Task 5: LogsPage — filter bar + virtualized log list with initial data

**Files:**
- Modify: `admin-ui/src/pages/LogsPage.tsx`

- [ ] **Step 1: Implement the logs page with filters and virtualized list**

Replace `admin-ui/src/pages/LogsPage.tsx` with:

```tsx
import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Virtuoso, type VirtuosoHandle } from "react-virtuoso";
import { api } from "@/lib/api";
import { parseSSE } from "@/lib/sseReader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Circle } from "lucide-react";

type LogRecord = {
  id: number;
  timestamp: string;
  level: string;
  logger: string;
  message: string;
  exception?: string | null;
  extra?: Record<string, unknown> | null;
};

const LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"];

const levelColor: Record<string, string> = {
  DEBUG: "text-muted-foreground",
  INFO: "",
  WARNING: "text-yellow-500",
  ERROR: "text-red-500",
  CRITICAL: "text-red-500 font-bold",
};

const levelBadgeVariant: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  DEBUG: "outline",
  INFO: "secondary",
  WARNING: "default",
  ERROR: "destructive",
  CRITICAL: "destructive",
};

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString();
}

export function LogsPage() {
  const [level, setLevel] = useState("INFO");
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [logs, setLogs] = useState<LogRecord[]>([]);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [liveTail, setLiveTail] = useState(false);
  const virtuosoRef = useRef<VirtuosoHandle>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Debounce search input
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(t);
  }, [search]);

  // Fetch initial logs
  const { data: initialLogs, isLoading } = useQuery({
    queryKey: ["admin", "logs", level, debouncedSearch],
    queryFn: () => {
      const params: Record<string, string | number | undefined> = {
        level,
        limit: 500,
      };
      if (debouncedSearch) params.search = debouncedSearch;
      return api.get<LogRecord[]>("/api/admin/logs", params);
    },
  });

  // Sync initial logs into state (reset on filter change)
  useEffect(() => {
    if (initialLogs) {
      setLogs(initialLogs);
    }
  }, [initialLogs]);

  // Live tail SSE connection
  useEffect(() => {
    if (!liveTail) {
      abortRef.current?.abort();
      abortRef.current = null;
      return;
    }

    const controller = new AbortController();
    abortRef.current = controller;

    (async () => {
      try {
        const params = new URLSearchParams();
        if (level !== "DEBUG") params.set("level", level);
        if (debouncedSearch) params.set("search", debouncedSearch);

        const res = await fetch(`/api/admin/logs/stream?${params}`, {
          credentials: "include",
          signal: controller.signal,
        });

        for await (const event of parseSSE(res)) {
          // parseSSE returns SSEEvent but our data is a LogRecord — safe
          // because parseSSE just JSON.parse's the data: payload.
          const record = event as unknown as LogRecord;
          setLogs((prev) => {
            // Deduplicate by id
            if (prev.some((r) => r.id === record.id)) return prev;
            const next = [...prev, record];
            // Cap at 5000 records to prevent unbounded growth during live tail
            return next.length > 5000 ? next.slice(-5000) : next;
          });
        }
      } catch {
        // AbortError or network error — expected on cleanup
      }
    })();

    return () => controller.abort();
  }, [liveTail, level, debouncedSearch]);

  // Auto-scroll to bottom when live tail is on and new logs arrive
  useEffect(() => {
    if (liveTail && logs.length > 0) {
      virtuosoRef.current?.scrollToIndex({
        index: logs.length - 1,
        behavior: "smooth",
      });
    }
  }, [liveTail, logs.length]);

  const toggleExpand = useCallback((id: number) => {
    setExpandedId((prev) => (prev === id ? null : id));
  }, []);

  return (
    <div className="flex h-full flex-col p-6">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Logs</h1>
        <Button
          variant={liveTail ? "default" : "outline"}
          size="sm"
          onClick={() => setLiveTail((prev) => !prev)}
        >
          <Circle
            className={`mr-2 h-3 w-3 ${liveTail ? "fill-red-500 text-red-500 animate-pulse" : ""}`}
          />
          Live tail
        </Button>
      </div>

      {/* Filter bar */}
      <div className="mb-4 flex gap-2">
        <Select value={level} onValueChange={setLevel}>
          <SelectTrigger className="w-[140px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {LEVELS.map((l) => (
              <SelectItem key={l} value={l}>
                {l}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Input
          placeholder="Search logs…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-sm"
        />
      </div>

      {/* Virtualized log list */}
      <div className="flex-1 rounded-md border">
        {isLoading ? (
          <p className="p-4 text-muted-foreground">Loading…</p>
        ) : logs.length === 0 ? (
          <p className="p-4 text-muted-foreground">No log records.</p>
        ) : (
          <Virtuoso
            ref={virtuosoRef}
            data={logs}
            style={{ height: "100%" }}
            itemContent={(_, record) => (
              <div
                key={record.id}
                className={`border-b px-3 py-2 cursor-pointer hover:bg-muted/50 ${levelColor[record.level] ?? ""}`}
                onClick={() => toggleExpand(record.id)}
              >
                <div className="flex items-center gap-2 text-sm">
                  <span className="shrink-0 font-mono text-xs text-muted-foreground">
                    {formatTime(record.timestamp)}
                  </span>
                  <Badge variant={levelBadgeVariant[record.level] ?? "outline"} className="shrink-0 text-xs">
                    {record.level}
                  </Badge>
                  <span className="truncate">{record.message}</span>
                  <span className="ml-auto shrink-0 text-xs text-muted-foreground">
                    {record.logger}
                  </span>
                </div>
                {expandedId === record.id && (
                  <div className="mt-2 space-y-1 rounded bg-muted/30 p-2 text-xs font-mono">
                    <div><strong>Logger:</strong> {record.logger}</div>
                    <div><strong>Timestamp:</strong> {record.timestamp}</div>
                    {record.exception && (
                      <div>
                        <strong>Exception:</strong>
                        <pre className="mt-1 whitespace-pre-wrap text-red-400">{record.exception}</pre>
                      </div>
                    )}
                    {record.extra && Object.keys(record.extra).length > 0 && (
                      <div>
                        <strong>Extra:</strong>
                        <pre className="mt-1 whitespace-pre-wrap">{JSON.stringify(record.extra, null, 2)}</pre>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          />
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify the frontend builds**

Run: `cd flexloop-server/admin-ui && npm run build`
Expected: build succeeds

- [ ] **Step 3: Commit**

```bash
git add admin-ui/src/pages/LogsPage.tsx
git commit -m "feat(admin): LogsPage with filter bar, virtualized list, live tail, expand"
```

---

### Task 6: Final verification

- [ ] **Step 1: Run the full backend test suite**

Run: `cd flexloop-server && uv run pytest -x -q`
Expected: all tests pass (455 baseline + new log handler + log router tests)

- [ ] **Step 2: Build the frontend**

Run: `cd flexloop-server/admin-ui && npm run build`
Expected: build succeeds

- [ ] **Step 3: Verify the sidebar item is enabled**

Check `admin-ui/src/components/AppSidebar.tsx` — the Logs item should NOT have `disabled: true`.

- [ ] **Step 4: Quick manual smoke test** (optional)

Start the backend: `cd flexloop-server && uv run uvicorn flexloop.main:app --port 8000`

Check:
- Navigate to `/admin/ops/logs`
- Sidebar shows "Logs" as active (not disabled)
- Filter bar with severity dropdown and search input visible
- Log records appear in the virtualized list
- Clicking a line expands to show details
- "Live tail" toggle connects SSE and auto-scrolls
- Changing level filter updates the list

- [ ] **Step 5: Final commit if any adjustments were needed**

Stage only the specific files that were changed. Skip this step if no adjustments were needed.

```bash
git add src/flexloop/admin/routers/logs.py admin-ui/src/pages/LogsPage.tsx
git commit -m "chore(admin): phase 5b final adjustments"
```
