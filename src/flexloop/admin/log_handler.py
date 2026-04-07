"""In-memory ring buffer log handler for the admin Log Viewer.

Keeps the last N records in a deque for instant live-tail queries. A future
phase (5) will add a rotating JSONL file sink for longer history.
"""
import logging
import threading
import traceback
from collections import deque
from datetime import datetime
from typing import Any

LEVEL_RANK = {
    "DEBUG": 10,
    "INFO": 20,
    "WARNING": 30,
    "ERROR": 40,
    "CRITICAL": 50,
}


class RingBufferHandler(logging.Handler):
    """Stores the most recent log records in a bounded deque.

    Thread-safe. Records are dicts, not LogRecord objects, so they're safe to
    serialize to JSON directly.
    """

    def __init__(self, capacity: int = 10_000) -> None:
        super().__init__()
        self._buffer: deque[dict[str, Any]] = deque(maxlen=capacity)
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry: dict[str, Any] = {
                "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "exception": None,
            }
            if record.exc_info:
                entry["exception"] = "".join(traceback.format_exception(*record.exc_info))
            with self._lock:
                self._buffer.append(entry)
        except Exception:  # noqa: BLE001
            # Don't let a logging failure crash the app
            self.handleError(record)

    def get_records(
        self,
        min_level: str = "DEBUG",
        search: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        threshold = LEVEL_RANK.get(min_level.upper(), 0)
        with self._lock:
            snapshot = list(self._buffer)

        filtered = [
            r for r in snapshot
            if LEVEL_RANK.get(r["level"], 0) >= threshold
            and (search is None or search.lower() in r["message"].lower())
        ]
        if limit is not None:
            filtered = filtered[-limit:]
        return filtered

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()


# Process-wide singleton installed in main.py. Other modules import this
# directly (e.g., the health endpoint reads from it for recent_errors).
admin_ring_buffer = RingBufferHandler(capacity=10_000)
