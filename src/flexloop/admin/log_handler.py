"""In-memory ring buffer log handler for the admin Log Viewer.

Keeps the last N records in a deque for instant live-tail queries.
Also writes each record to a rotating JSONL file for crash-recovery
persistence (one file per day, 7-day retention).
"""
from __future__ import annotations

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

_STANDARD_ATTRS = frozenset({
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "message",
    "module",
    "msecs",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "taskName",
    "thread",
    "threadName",
})


def _coerce_json_value(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _coerce_json_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set | frozenset | deque):
        return [_coerce_json_value(item) for item in value]
    return str(value)


class RingBufferHandler(logging.Handler):
    """Stores the most recent log records in a bounded deque.

    Thread-safe. Records are dicts with monotonic ``id`` fields for
    SSE cursor tracking.
    """

    def __init__(self, capacity: int = 10_000, log_dir: str | Path = "logs") -> None:
        super().__init__()
        self._buffer: deque[dict[str, Any]] = deque(maxlen=capacity)
        self._lock = threading.Lock()
        self._next_id = 0
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
                entry["exception"] = "".join(traceback.format_exception(*record.exc_info))

            extras = {
                key: _coerce_json_value(value)
                for key, value in record.__dict__.items()
                if key not in _STANDARD_ATTRS and not key.startswith("_")
            }
            if extras:
                entry["extra"] = extras

            with self._lock:
                entry["id"] = self._next_id
                self._next_id += 1
                self._buffer.append(entry)

            self._write_jsonl(entry)

            if (entry["id"] + 1) % 1000 == 0:
                self._prune_old_logs()
        except Exception:  # noqa: BLE001
            # Don't let a logging failure crash the app.
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
            record
            for record in snapshot
            if LEVEL_RANK.get(record["level"], 0) >= threshold
            and (search is None or search.lower() in record["message"].lower())
            and (since is None or record["timestamp"] >= since)
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
        threshold = LEVEL_RANK.get(min_level.upper(), 0)
        with self._lock:
            snapshot = list(self._buffer)

        return [
            record
            for record in snapshot
            if record.get("id", -1) > after_id
            and LEVEL_RANK.get(record["level"], 0) >= threshold
            and (search is None or search.lower() in record["message"].lower())
        ]

    def get_latest_id(self) -> int:
        with self._lock:
            if not self._buffer:
                return -1
            return self._buffer[-1].get("id", -1)

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()

    def _write_jsonl(self, entry: dict[str, Any]) -> None:
        try:
            self._log_dir.mkdir(parents=True, exist_ok=True)
            filename = f"flexloop.{datetime.now().strftime('%Y-%m-%d')}.jsonl"
            path = self._log_dir / filename
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, default=str) + "\n")
        except Exception:  # noqa: BLE001
            pass

    def _prune_old_logs(self, retention_days: int = 7) -> None:
        try:
            cutoff = datetime.now() - timedelta(days=retention_days)
            for path in self._log_dir.glob("flexloop.*.jsonl"):
                parts = path.stem.split(".", 1)
                if len(parts) != 2:
                    continue
                try:
                    file_date = datetime.strptime(parts[1], "%Y-%m-%d")
                except ValueError:
                    continue
                if file_date < cutoff:
                    path.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass


# Process-wide singleton installed in main.py. Other modules import this
# directly (e.g., the health endpoint reads from it for recent_errors).
admin_ring_buffer = RingBufferHandler(capacity=10_000)
