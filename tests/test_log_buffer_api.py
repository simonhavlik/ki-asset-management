#!/usr/bin/env python3
"""Standalone checks for the upgraded log buffer (no Flask/deps needed)."""
import importlib.util
import logging
import pathlib
import sys

path = pathlib.Path(__file__).resolve().parent.parent / "app" / "api" / "log_buffer.py"
spec = importlib.util.spec_from_file_location("log_buffer", path)
mod = importlib.util.module_from_spec(spec)
sys.modules["log_buffer"] = mod
spec.loader.exec_module(mod)

# 1. redaction
sample = ("creating app: db=postgresql://kiam:REDACTED@212.227.211.88:5432/kiam "
          "NOTION_API_KEY=ntn_abc123XYZ key=cfut_deadbeef Header: Bearer abc.def.ghi")
red = mod.redact(sample)
print("redacted:", red)
assert "PASSWORD" not in red, "db password leaked"
assert "ntn_abc123XYZ" not in red, "notion key leaked"
assert "cfut_deadbeef" not in red, "cloudflare token leaked"
assert "abc.def.ghi" not in red, "bearer token leaked"
assert "kiam:" in red and "@212.227.211.88" in red, "host should survive"

# 2. filters (real logger names, like production)
buf = mod.RingBufferHandler(capacity=50)
logging.getLogger().handlers = [buf]
logging.getLogger("app.scheduler").setLevel(logging.DEBUG)
logging.getLogger("app.request").setLevel(logging.DEBUG)
logging.getLogger("app.utils.notion_import").setLevel(logging.DEBUG)
logging.getLogger("app.scheduler").info("Daily Notion import scheduled")
logging.getLogger("app.request").warning("GET /info.php -> 404 0.2ms")
logging.getLogger("app.utils.notion_import").error("Notion import failed: boom")
logging.getLogger("app.scheduler").info("plain info line")

rows = buf.tail(10, "INFO")
print("default tail:", [(r["logger"], r["msg"][:30]) for r in rows])
assert len(rows) == 3, rows                                   # request line excluded by default
assert len(buf.tail(10, "INFO", include_requests=True)) == 4  # …but available on request
assert len(buf.tail(10, "INFO", q="info.php")) == 0
assert len(buf.tail(10, "INFO", q="info.php", include_requests=True)) == 1
assert len(buf.tail(10, "ERROR")) == 1
assert [r["level"] for r in buf.tail(10, "WARNING", include_requests=True)] == ["WARNING", "ERROR"]
assert len(buf.tail(10, "INFO", logger="app.scheduler")) == 2
assert len(buf.tail(10, "INFO", since="-5m")) == 3
assert len(buf.tail(10, "INFO", since="2000-01-01T00:00:00")) == 3
assert len(buf.tail(10, "INFO", since="2999-01-01T00:00:00")) == 0, "future cutoff must filter everything out"
assert len(buf.tail(10, "INFO", since="-1m")) == 3
assert len(buf.tail(10, "INFO", q="NOTION")) == 2, "search must be case-insensitive"
assert buf.stats()["buffered"] == 4

# 3. since parser
parsed = mod._parse_since("-30m")
assert parsed is not None and abs((mod.datetime.now(mod.timezone.utc) - parsed).total_seconds() - 1800) < 5
assert mod._parse_since("2026-10-12T21:00:00Z") is not None
assert mod._parse_since("nonsense") is None
assert mod._parse_since(None) is None

print("LOG BUFFER CHECKS OK")
