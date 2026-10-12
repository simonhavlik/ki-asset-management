"""In-process ring buffer of recent log records, exposed by the key-secured API.

Render's logs API does not return runtime logs on the free plan, so the app keeps
its own tail: the last N records (INFO and above) from every logger. Read it at
GET /api/logs to inspect a forced run without a Render dashboard round-trip.

Two things matter for this to be *useful* rather than noise:

  * Secrets never enter the buffer. Startup lines print the configured
    ``DATABASE_URL``; a password in a log line is a leak the moment the endpoint
    (or the file log) is read, so every record is redacted on the way in.
  * Request chatter is separable. Public deployments are scanned constantly
    (/info.php, /actuator/env, /.vscode/sftp.json, …) and those lines would
    otherwise fill the whole ring in minutes and push out the job logs you came
    for. ``tail(..., include_requests=False)`` (the default) drops them; pass
    ``include_requests=true`` on the endpoint when you want request lines.
"""
import collections
import logging
import re
import threading
from datetime import datetime, timedelta, timezone

_CAPACITY = 800

_LEVELS = {'DEBUG': 10, 'INFO': 20, 'WARNING': 30, 'ERROR': 40, 'CRITICAL': 50}

# Anything matching these is replaced before a record is stored.
_REDACTIONS = (
    # postgres://user:password@host/db  (and postgresql+, mysql, redis, mongodb…)
    (re.compile(r'(?i)\b(?:postgres(?:ql)?|mysql|redis|mongodb)(?:\+\w+)?://([^:/@\s]+):([^@\s]+)@'),
     r'\1:***@'),
    # key=value / key: value for anything that looks like a credential
    (re.compile(r'(?i)\b([A-Z0-9_]*(?:API_?KEY|TOKEN|SECRET|PASSWORD|REFRESH_API_KEY)[A-Z0-9_]*)\s*[=:]\s*([^\s,;"\']+)'),
     r'\1=***'),
    # Authorization: Bearer xxx
    (re.compile(r'(?i)\b(bearer\s+)[A-Za-z0-9._\-]{8,}'), r'\1***'),
    # provider-specific key shapes (Notion, Render, SendGrid, OpenAI-style, Cloudflare)
    (re.compile(r'\b(ntn_|secret_|rnd_|SG\.|sk-[A-Za-z0-9]|cfut_)[A-Za-z0-9._\-]{6,}'),
     r'\1***'),
)


def redact(text):
    """Return ``text`` with credentials masked. Never raises."""
    try:
        out = text
        for pattern, replacement in _REDACTIONS:
            out = pattern.sub(replacement, out)
        return out
    except Exception:  # a broken regex must not break logging
        return text


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
                'msg': redact(record.getMessage()),
            }
        except Exception:  # a broken log call must never break the app
            return
        with self._lock:
            self._buf.append(entry)

    def tail(self, lines=200, level='INFO', since=None, logger=None, q=None,
             include_requests=False):
        """Filtered tail of the buffer.

        lines            how many records to return (most recent last)
        level            minimum level name (DEBUG/INFO/WARNING/ERROR/CRITICAL)
        since            ISO timestamp or a relative window ('-30m', '-2h', '-1d')
        logger           logger-name prefix ('app.scheduler' matches 'app.scheduler.x')
        q                case-insensitive substring match on the message
        include_requests keep 'app.request' lines (default: drop them, they are
                         mostly internet scanner noise)
        """
        threshold = _LEVELS.get((level or 'INFO').upper(), 20)
        try:
            n = max(1, int(lines))
        except (TypeError, ValueError):
            n = 200
        cutoff = _parse_since(since)
        with self._lock:
            rows = list(self._buf)
        needle = (q or '').strip().lower()
        out = []
        for row in rows:
            if _LEVELS.get(row['level'], 0) < threshold:
                continue
            if not include_requests and row['logger'].startswith('app.request'):
                continue
            if logger and not row['logger'].startswith(logger):
                continue
            if cutoff is not None:
                try:
                    if datetime.fromisoformat(row['ts']) < cutoff:
                        continue
                except ValueError:
                    pass
            if needle and needle not in row['msg'].lower():
                continue
            out.append(row)
        return out[-n:]

    def stats(self):
        """Cheap summary so /api/logs can report what it is filtering."""
        with self._lock:
            rows = list(self._buf)
        return {
            'buffered': len(rows),
            'capacity': self._buf.maxlen,
            'levels': collections.Counter(r['level'] for r in rows),
        }


def _parse_since(value):
    """ISO timestamp or '-30m'/'2h'/'1d' → aware datetime, else None."""
    if not value:
        return None
    text = str(value).strip().lower()
    match = re.fullmatch(r'-?(\d+)\s*([smhd])', text)
    if match:
        amount, unit = int(match.group(1)), match.group(2)
        delta = {
            's': timedelta(seconds=amount),
            'm': timedelta(minutes=amount),
            'h': timedelta(hours=amount),
            'd': timedelta(days=amount),
        }[unit]
        return datetime.now(tz=timezone.utc) - delta
    try:
        parsed = datetime.fromisoformat(text.replace('z', '+00:00'))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


LOG_BUFFER = RingBufferHandler()


def install_log_buffer():
    """Attach LOG_BUFFER to the root logger once (idempotent across reloads)."""
    root = logging.getLogger()
    if LOG_BUFFER not in root.handlers:
        root.addHandler(LOG_BUFFER)
    return LOG_BUFFER
