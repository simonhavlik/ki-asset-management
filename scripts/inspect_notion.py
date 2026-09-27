#!/usr/bin/env python
"""
READ-ONLY Notion schedule inspector.

    ####################################################################
    #  THIS SCRIPT CANNOT WRITE TO NOTION.                              #
    #                                                                   #
    #  Every outgoing HTTP call goes through _request(), which only     #
    #  permits two operations and hard-fails on anything else:          #
    #                                                                   #
    #      GET   /v1/databases/{id}          database metadata          #
    #      POST  /v1/databases/{id}/query    read rows                  #
    #                                                                   #
    #  The query call is a POST only because the Notion API has no GET  #
    #  endpoint for reading rows; it is a query and modifies nothing.   #
    #  There is no create/update/archive code path in this file, any    #
    #  URL containing /pages or /blocks is rejected before the request  #
    #  is sent, and run_selftest() proves that.                         #
    ####################################################################

It prints the schedule (Name / Date / Sector / Analyst / Opponent / Status) and
summarises the dates, plus a "schema drift" section comparing the property names
this database actually uses against the names hardcoded in the app's
`flask notion-import` command. It deliberately does NOT import the app package
or touch any database.

Usage
-----
    venv/bin/python scripts/inspect_notion.py
    venv/bin/python scripts/inspect_notion.py --limit 200
    venv/bin/python scripts/inspect_notion.py --selftest   # prove read-only
    venv/bin/python scripts/inspect_notion.py --raw
"""

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import date, datetime, timedelta

import requests

API_ROOT = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
DEFAULT_ENV_FILE = ".env"

# --- The allowlist. Nothing outside this is ever sent. ----------------------
_DB_ID = r"[0-9a-fA-F]{32}|[0-9a-fA-F-]{36}"
ALLOWED = (
    ("GET", re.compile(rf"^/databases/(?:{_DB_ID})$")),
    ("POST", re.compile(rf"^/databases/(?:{_DB_ID})/query$")),
)
# Explicitly forbidden even if a pattern above were ever loosened.
FORBIDDEN_SUBSTRINGS = ("/pages", "/blocks", "/comments", "/users/me")

# What app/__init__.py:register_cli()['notion-import'] passes as column_mapping.
APP_HARDCODED_MAPPING = {
    "Company": "Company",
    "Date": "Date",
    "Sector": "Sector",
    "Analyst": "Analyst",
    "Opponent": "Opponent",
    "Comment": "Comment",
    "Status": "Status",
    "Files & media": "Files & media",
}

# Columns worth showing in the schedule table.
DISPLAY_COLUMNS = ["Company", "Date", "Sector", "Analysis", "Analyst", "Opponent", "Status"]


def _request(method: str, path: str, token: str, json_body=None, timeout: int = 30):
    """The ONLY place this script performs network I/O.

    Refuses (before sending) any request that is not on the read-only allowlist.
    """
    method = method.upper()
    if any(bad in path for bad in FORBIDDEN_SUBSTRINGS):
        raise SystemExit(f"REFUSED: path {path!r} touches a write-capable endpoint")

    if not any(m == method and rx.match(path) for m, rx in ALLOWED):
        raise SystemExit(f"REFUSED: ({method} {path}) is not on the read-only allowlist")

    print(f"  [{method} {path}]")
    response = requests.request(
        method,
        f"{API_ROOT}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
        json=json_body,
        timeout=timeout,
    )
    if response.status_code == 401:
        raise SystemExit("Notion: invalid or expired token (401)")
    if response.status_code == 404:
        raise SystemExit(
            "Notion: database not found, or the integration is not shared with it (404)"
        )
    if response.status_code != 200:
        raise SystemExit(f"Notion API error {response.status_code}: {response.text[:400]}")
    return response.json()


def run_selftest() -> int:
    """Prove that no write-capable request can get past _request()."""
    db = "11f8c7709a728027ac0deb4211d87f1c"
    attempts = [
        ("PATCH", "/pages/abc123", "modify a page"),
        ("POST", "/pages", "create a page"),
        ("POST", f"/databases/{db}", "create a database"),
        ("PATCH", f"/databases/{db}", "alter schema"),
        ("DELETE", "/blocks/abc", "delete a block"),
        ("PATCH", "/blocks/abc/children", "append blocks"),
        ("POST", f"/databases/{db}/query/../pages", "path traversal to pages"),
        ("GET", "/users/me", "unrelated endpoint"),
    ]
    print("refusal self-test (all of these must be refused before any network call)\n")
    danger = 0
    for method, path, why in attempts:
        try:
            _request(method, path, "fake-token")
            print(f"  !! ALLOWED  {method:6s} {path}  <-- DANGER: {why}")
            danger += 1
        except SystemExit:
            print(f"  refused  {method:6s} {path:40s} ({why})")

    print("\npermitted operations:")
    for method, rx in ALLOWED:
        print(f"  {method:5s} {rx.pattern}")
    print(f"\n{'FAIL: a write path was reachable' if danger else 'SAFE: every write path refused'}")
    return 1 if danger else 0


def read_env(env_file: str, keys) -> dict:
    """Read specific KEY=VALUE pairs without importing the app or exporting vars."""
    if not os.path.exists(env_file):
        raise SystemExit(f"{env_file} not found")
    wanted = {}
    with open(env_file, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            if key in keys:
                wanted[key] = value
    missing = [k for k in keys if not wanted.get(k)]
    if missing:
        raise SystemExit(f"missing in {env_file}: {', '.join(missing)}")
    return wanted


def extract_property_value(prop) -> str:
    """Mirror of app.utils.notion_helper.extract_property_value, kept local so this
    script imports nothing from the application."""
    if prop is None:
        return ""
    t = prop.get("type", "")
    if t == "title":
        return "".join(x.get("plain_text", "") for x in prop.get("title", []))
    if t == "rich_text":
        return "".join(x.get("plain_text", "") for x in prop.get("rich_text", []))
    if t == "number":
        return str(prop.get("number", "") or "")
    if t == "select":
        v = prop.get("select")
        return v.get("name", "") if v else ""
    if t == "multi_select":
        return ", ".join(s.get("name", "") for s in prop.get("multi_select", []))
    if t == "date":
        v = prop.get("date")
        return v.get("start", "") if v else ""
    if t == "status":
        v = prop.get("status")
        return v.get("name", "") if v else ""
    if t == "checkbox":
        return "Yes" if prop.get("checkbox") else "No"
    if t == "url":
        return prop.get("url", "") or ""
    if t == "email":
        return prop.get("email", "") or ""
    if t == "people":
        return ", ".join(p.get("name", "") for p in prop.get("people", []) if p.get("name"))
    if t == "files":
        return ", ".join(f.get("name", "") for f in prop.get("files", []) if f.get("name"))
    return ""


def fetch_all_rows(database_id: str, token: str, limit=None):
    """Page through the database. Read-only."""
    rows, cursor = [], None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        payload = _request("POST", f"/databases/{database_id}/query", token, json_body=body)
        rows.extend(payload.get("results", []))
        if limit and len(rows) >= limit:
            return rows[:limit]
        if not payload.get("has_more"):
            return rows
        cursor = payload.get("next_cursor")


def parse_date(value: str):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def resolve_mapping(properties: dict):
    """Map app column names onto the real Notion property names.

    Tolerates surrounding whitespace in property names, which matters here: this
    database names the date column 'Date ' (trailing space), so an exact
    'Date' lookup silently yields nothing.
    """
    by_norm = {}
    for name in properties:
        by_norm.setdefault(name.strip().lower(), name)

    resolved = {}
    title_prop = next(
        (n for n, spec in properties.items() if spec.get("type") == "title"), None
    )
    if title_prop:
        resolved["Company"] = title_prop
    for key, candidates in (
        ("Date", ["date", "analysis date", "report date"]),
        ("Sector", ["sector", "industry"]),
        ("Analyst", ["analyst"]),
        ("Opponent", ["opponent"]),
        ("Status", ["status"]),
        # The app calls this "Comment"; this database calls it "Voting".
        ("Comment", ["comment", "voting", "note", "notes"]),
        ("Files & media", ["files & media", "files", "media"]),
    ):
        for cand in candidates:
            if cand in by_norm:
                resolved[key] = by_norm[cand]
                break
    return resolved, by_norm


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--selftest", action="store_true", help="prove read-only and exit")
    parser.add_argument("--raw", action="store_true", help="also dump raw page JSON")
    args = parser.parse_args()

    if args.selftest:
        sys.exit(run_selftest())

    env = read_env(args.env_file, ("NOTION_API_KEY", "NOTION_DATABASE_ID"))
    token = env["NOTION_API_KEY"]
    database_id = env["NOTION_DATABASE_ID"]

    print("READ-ONLY Notion inspection")
    print(f"token: {token[:7]}...{token[-4:]} (from {args.env_file})")
    print(f"database: {database_id}\n")

    print("1) database metadata")
    info = _request("GET", f"/databases/{database_id}", token)
    title = "".join(t.get("plain_text", "") for t in info.get("title", [])) or "(untitled)"
    props = info.get("properties", {})
    print(f"  title: {title}")
    for name, spec in props.items():
        flag = ""
        if name != name.strip():
            flag = "  <-- NAME HAS SURROUNDING WHITESPACE"
        print(f"    - {name!r:24s} {spec.get('type', '?'):14s}{flag}")

    resolved, by_norm = resolve_mapping(props)

    print("\n2) schema drift: app's hardcoded notion-import mapping vs reality")
    drift = False
    for app_col, notion_name in APP_HARDCODED_MAPPING.items():
        exists = notion_name in props
        actual = resolved.get(app_col)
        if exists:
            print(f"  OK      '{notion_name}' -> {app_col}")
        else:
            drift = True
            found = f"maps to {actual!r}" if actual else "NO MATCH FOUND"
            print(f"  MISSING '{notion_name}' -> {app_col:14s} ({found})")
    if drift:
        print(
            "\n  WARNING: app/__init__.py 'flask notion-import' uses the hardcoded names\n"
            "  above. Property names are matched with `notion_prop in properties`, i.e.\n"
            "  exactly, with no whitespace normalisation, so every MISSING row above\n"
            "  imports as an empty value. auto_detect_column_mapping() would help but is\n"
            "  never called anywhere in the codebase."
        )

    print("\n3) reading rows")
    rows = fetch_all_rows(database_id, token, limit=args.limit)
    print(f"  rows fetched: {len(rows)}")

    print("\n4) populate rate per property")
    for name in props:
        filled = sum(
            1 for p in rows if extract_property_value(p["properties"].get(name)).strip()
        )
        print(f"  {name!r:24s} {props[name].get('type', '?'):14s} {filled:>4}/{len(rows)}")

    print("\n5) schedule")
    header = DISPLAY_COLUMNS
    table, dates, statuses = [], [], Counter()

    for page in rows:
        page_props = page.get("properties", {})
        row = {}
        for col in header:
            notion_name = resolved.get(col)
            row[col] = extract_property_value(page_props.get(notion_name)) if notion_name else ""
        table.append(row)
        statuses[row.get("Status") or "(blank)"] += 1
        d = parse_date(row.get("Date", ""))
        if d:
            dates.append(d)

    widths = {h: max([len(h)] + [len(r.get(h, "")) for r in table]) for h in header}
    print("  " + "  ".join(h.ljust(widths[h]) for h in header))
    print("  " + "  ".join("-" * widths[h] for h in header))
    for row in sorted(table, key=lambda r: (r.get("Date") or "", r.get("Company") or "")):
        print("  " + "  ".join((row.get(h, "") or "").ljust(widths[h]) for h in header))

    print("\n6) status distribution")
    for status, count in statuses.most_common():
        print(f"  {status:22s} {count:>4}")

    print("\n7) date analysis (this is what feeds the Board chart's 1-year window)")
    if dates:
        today = date.today()
        cutoff = today - timedelta(days=365)
        recent = [d for d in dates if d >= cutoff]
        print(f"  dated rows            {len(dates)}/{len(rows)}")
        print(f"  earliest              {min(dates)}")
        print(f"  latest                {max(dates)}")
        print(f"  today                 {today}")
        print(f"  within last 365 days  {len(recent)}   (cutoff {cutoff})")
        print("\n  per calendar year:")
        for year, count in sorted(Counter(d.year for d in dates).items()):
            print(f"    {year}  {count:>4}")
    else:
        print("  no dated rows found")

    if args.raw:
        print("\n8) raw JSON (first 2 rows)")
        print(json.dumps(rows[:2], indent=2, ensure_ascii=False)[:4000])

    print("\nDone. No write operations were performed.")


if __name__ == "__main__":
    main()
