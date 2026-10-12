#!/usr/bin/env python3
"""Fetch this service's logs from the Render API.

Live-debugging aid for the autonomous jobs (the daily Notion import and the
Monday recalculation). Their output goes to stdout/stderr, which Render captures
and serves back through the public API - so a run can be inspected without
dashboard access:

    export RENDER_API_KEY=rnd_...        # or: set -a; . private_docs/live-debug.env; set +a
    python scripts/render_logs.py                        # newest 100 app-log lines
    python scripts/render_logs.py --text "Notion import"
    python scripts/render_logs.py --text "refresh completed" --limit 50
    python scripts/render_logs.py --type request --text "/health"

The key is never read from the repo: it comes from the environment or the
gitignored private_docs/live-debug.env.
"""

import argparse
import os
import sys

import requests

API = "https://api.render.com/v1"
ENV_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "private_docs", "live-debug.env")


def load_api_key(explicit=None):
    key = explicit or os.environ.get("RENDER_API_KEY", "").strip()
    if key:
        return key
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("RENDER_API_KEY="):
                    value = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if value:
                        return value
    sys.exit(
        "No Render API key. Set RENDER_API_KEY, or put it in "
        f"{ENV_FILE}.\nCreate one at Render dashboard -> Account Settings -> API Keys."
    )


def resolve_service(session, key, name):
    resp = session.get(f"{API}/services", headers=_headers(key),
                       params={"limit": 100}, timeout=30)
    resp.raise_for_status()
    for item in resp.json():
        svc = item.get("service", item)
        if svc.get("name") == name:
            return svc
    sys.exit(f"No service named {name!r} found. Pass --service with an exact name.")


def _headers(key):
    return {"Authorization": f"Bearer {key}", "Accept": "application/json"}


def main():
    parser = argparse.ArgumentParser(description="Fetch Render logs for the KI service.")
    parser.add_argument("--service", default="ki-asset-management",
                        help="Render service name (default: ki-asset-management)")
    parser.add_argument("--service-id", default=os.environ.get("KI_SERVICE_ID", ""),
                        help="Skip name lookup and use this service id")
    parser.add_argument("--api-key", default=None, help="Render API key (else env/file)")
    parser.add_argument("--text", default="", help="Only logs matching this text/regex")
    parser.add_argument("--type", default="app", help="Log type: app|request|build ('*' for all)")
    parser.add_argument("--level", default="", help="Severity filter, e.g. error")
    parser.add_argument("--limit", type=int, default=100, help="Max lines (1-100)")
    parser.add_argument("--raw", action="store_true", help="Print raw JSON entries")
    args = parser.parse_args()

    key = load_api_key(args.api_key)
    session = requests.Session()

    if args.service_id:
        service_id, owner_id = args.service_id, os.environ.get("KI_OWNER_ID", "")
        if not owner_id:
            svc = session.get(f"{API}/services/{service_id}", headers=_headers(key),
                              timeout=30).json()
            owner_id = (svc.get("ownerId") or svc.get("service", {}).get("ownerId", ""))
    else:
        svc = resolve_service(session, key, args.service)
        service_id = svc["id"]
        owner_id = svc.get("ownerId", "")

    params = {
        "ownerId": owner_id,
        "resource": service_id,
        "limit": max(1, min(args.limit, 100)),
        "direction": "backward",
    }
    if args.type and args.type != "*":
        params["type"] = args.type
    if args.text:
        params["text"] = args.text
    if args.level:
        params["level"] = args.level

    resp = session.get(f"{API}/logs", headers=_headers(key), params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    entries = data.get("logs", [])

    if args.raw:
        for entry in reversed(entries):
            print(entry)
        return

    for entry in reversed(entries):  # API returns newest-first; print oldest-first
        if isinstance(entry, dict):
            ts = entry.get("timestamp", "")
            msg = entry.get("message", entry.get("text", str(entry)))
            print(f"{ts} {msg}".strip())
        else:
            print(entry)

    if data.get("hasMore"):
        print(f"\n[more available - narrow with --text or raise --limit]")


if __name__ == "__main__":
    main()
