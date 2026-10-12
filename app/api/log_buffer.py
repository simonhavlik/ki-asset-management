"""In-process ring buffer of recent log records, exposed by the key-secured API.

Render's logs API does not return runtime logs on the free plan, so the app keeps
its own tail: the last N records (INFO and above) from every logger. Read it at
GET /api/logs to inspect a forced run without a Render dashboards round-trip.
"""
import collections
import logging
import threading
from datetime import datetime, timezone

_CAPACITY = 800

_LEVELS = {'DEBUG': 10, 'INFO': 20, 'WARNING': 30, 'ERROR': 40, 'CRITICAL': 50}


class RingBufferHandler(logging.Handler):
    """Keep the most recent records in memory for the /api/logs endpoint."""

    def __init__(self, capacity=_CAPACITY):
        super().__init__()
        self._buf = collections.deque(maxlen=capacity)
        self._lock = threading.Lock()

    def emit(self, record):
        try:
            entry = {
                'ts': datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec='seconds'),
                'level': record.levelname,
                'logger': record.name,
                'msg': record.getMessage(),
            }
        except Exception:  # a broken log call must never break the app
            return
        with self._lock:
            self._buf.append(entry)

    def tail(self, lines=200, level='INFO'):
        threshold = _LEVELS.get((level or 'INFO').upper(), 20)
        try:
            n = max(1, int(lines))
        except (TypeError, ValueError):
            n = 200
        with self._lock:
            rows = list(self._buf)
        return [r for r in rows if _LEVELS.get(r['level'], 0) >= threshold][-n:]


LOG_BUFFER = RingBufferHandler()


def install_log_buffer():
    """Attach LOG_BUFFER to the root logger once (idempotent across reloads)."""
    root = logging.getLogger()
    if LOG_BUFFER not in root.handlers:
        root.addHandler(LOG_BUFFER)
    return LOG_BUFFER
