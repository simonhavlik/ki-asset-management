#!/usr/bin/env python
"""
Read-only diagnostic queries against a remote (production) database.

Why this exists
---------------
Running the app against production from a laptop is risky: ``create_app()``
calls ``db.create_all()`` and ``_ensure_benchmark_table()``, which can WRITE
(including inserting seed rows) into the live database. So this script never
builds a Flask app and never uses the ORM session. It opens a plain SQLAlchemy
connection, forces the transaction to READ ONLY, and issues SELECTs only.

Its main job is to answer one question about the Board page chart:

    "In production, is the 1-year series empty while the inception series has
     data?"

The Board page builds two series from the same set of Board-approved analyses
(status 'On Watchlist', yes-votes > no-votes). The 1-year series only includes
analyses whose entry date falls inside the last 365 days, so if every approved
analysis is older than that, the 1-year series comes back None.

Usage
-----
    venv/bin/python scripts/inspect_prod.py
    venv/bin/python scripts/inspect_prod.py --env-file .env
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

DEFAULT_ENV_FILE = ".env"

# Board "approved" == status 'On Watchlist' AND yes votes > no votes.
APPROVED_CTE = """
    approved AS (
        SELECT a.id,
               a.analysis_date,
               COALESCE(a.purchase_date, a.analysis_date) AS entry_date
        FROM analyses a
        LEFT JOIN (
            SELECT analysis_id,
                   SUM(CASE WHEN vote THEN 1 ELSE 0 END) AS yes_votes,
                   SUM(CASE WHEN NOT vote THEN 1 ELSE 0 END) AS no_votes
            FROM votes
            GROUP BY analysis_id
        ) v ON v.analysis_id = a.id
        WHERE a.status = 'On Watchlist'
          AND COALESCE(v.yes_votes, 0) > COALESCE(v.no_votes, 0)
    )
"""


def _normalize_url(url: str) -> str:
    """Force the psycopg2 driver.

    SQLAlchemy 2.1 changed the default DBAPI for bare ``postgresql://`` URLs to
    psycopg3 (``psycopg``). The project installs ``psycopg2-binary`` only, so a
    bare URL raises "ModuleNotFoundError: No module named 'psycopg'". Selecting
    the driver explicitly keeps this script (and the app) working on both
    SQLAlchemy 2.0 and 2.1.
    """
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg2://" + url[len(prefix):]
    return url


def read_database_url(env_file: str) -> str:
    if not os.path.exists(env_file):
        raise SystemExit(f"{env_file} not found")
    with open(env_file, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if line.startswith("DATABASE_URL"):
                value = line.split("=", 1)[1].strip()
                # Tolerate surrounding quotes, as written in .env files.
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                return value
    raise SystemExit(f"DATABASE_URL not found in {env_file}")


def scalar(conn, sql, **params):
    return conn.execute(text(sql), params).scalar()


def section(title: str) -> None:
    print(f"\n{title}")
    print("-" * len(title))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    args = parser.parse_args()

    url = _normalize_url(read_database_url(args.env_file))
    # Never print the URL: it embeds the database password.
    host = url.split("@")[-1].split("/")[0] if "@" in url else "?"
    print(f"connecting (read-only) to host={host} from {args.env_file}")

    engine = create_engine(
        url,
        poolclass=NullPool,
        connect_args={"connect_timeout": 15},
    )

    with engine.connect() as conn:
        # MUST be the first statement: psycopg2 opens a transaction lazily, so
        # SET TRANSACTION applies to the transaction the SELECTs will run in.
        # (SET SESSION CHARACTERISTICS only affects *later* transactions, which
        # is why it left transaction_read_only reporting 'off'.)
        conn.execute(text("SET TRANSACTION READ ONLY"))
        conn.execute(text("SET LOCAL statement_timeout = 30000"))

        read_only = scalar(conn, "SELECT current_setting('transaction_read_only')")
        timeout = scalar(conn, "SELECT current_setting('statement_timeout')")
        print(f"transaction_read_only = {read_only} (statement_timeout={timeout})")
        if read_only != "on":
            raise SystemExit(
                "refusing to continue: could not establish a read-only transaction"
            )

        section("row counts")
        for table in (
            "users", "companies", "analyses", "votes", "portfolio_purchases",
            "stock_prices", "performance_calculations", "benchmark_prices",
            "company_sector_cache", "company_ticker_maps",
        ):
            try:
                count = scalar(conn, f"SELECT count(*) FROM {table}")
                print(f"  {table:26s} {count:>8,}")
            except Exception as exc:  # noqa: BLE001
                print(f"  {table:26s} ERROR {exc}")

        section("analyses by status")
        for status, count in conn.execute(text(
            "SELECT status, count(*) FROM analyses GROUP BY status ORDER BY 2 DESC"
        )):
            print(f"  {str(status):26s} {count:>8,}")

        section("analyses by calendar year of analysis_date")
        rows_by_year = list(conn.execute(text("""
            SELECT EXTRACT(YEAR FROM analysis_date)::int AS yr,
                   count(*) AS total,
                   count(*) FILTER (WHERE status = 'On Watchlist') AS on_watchlist
            FROM analyses
            WHERE analysis_date IS NOT NULL
            GROUP BY 1 ORDER BY 1
        """)))
        print(f"  {'year':6s} {'total':>8s} {'on_watchlist':>14s}")
        for yr, total, watch in rows_by_year:
            print(f"  {yr:<6d} {total:>8,} {watch:>14,}")

        null_dates = scalar(conn, "SELECT count(*) FROM analyses WHERE analysis_date IS NULL")
        if null_dates:
            print(f"\n  WARNING: {null_dates:,} analyses have a NULL analysis_date")

        section("the Board-approved analyses actually in the portfolio")
        approved_rows = list(conn.execute(text(f"""
            WITH {APPROVED_CTE}
            SELECT c.name, a.analysis_date, a.entry_date
            FROM approved a
            JOIN analyses an ON an.id = a.id
            JOIN companies c ON c.id = an.company_id
            ORDER BY a.entry_date
        """)))
        if not approved_rows:
            print("  (none)")
        for name, analysis_date, entry_date in approved_rows:
            print(f"  {str(name)[:38]:40s} analysis_date={analysis_date} entry={entry_date}")

        section("Board-approved analyses (status='On Watchlist' AND yes>no)")
        total_approved = scalar(conn, f"WITH {APPROVED_CTE} SELECT count(*) FROM approved")
        print(f"  approved total            {total_approved:>8,}")

        row = conn.execute(text(f"""
            WITH {APPROVED_CTE}
            SELECT min(entry_date), max(entry_date),
                   count(*) FILTER (WHERE entry_date >= CURRENT_DATE - INTERVAL '365 days'),
                   count(*) FILTER (WHERE analysis_date >= CURRENT_DATE - INTERVAL '365 days')
            FROM approved
        """)).one()
        min_entry, max_entry, approved_recent_entry, approved_recent_analysis = row
        print(f"  earliest entry date       {min_entry}")
        print(f"  latest entry date         {max_entry}")
        print(f"  entries within 1 year     {approved_recent_entry:,}")
        print(f"  analyses within 1 year    {approved_recent_analysis:,}")

        section("stock price coverage")
        row = conn.execute(text("""
            SELECT count(*), count(DISTINCT company_id), min(date), max(date)
            FROM stock_prices
        """)).one()
        print(f"  rows={row[0]:,} companies={row[1]:,} range={row[2]}..{row[3]}")

        section("benchmark coverage (drives the SPY/VT/EEMS lines)")
        for ticker, count, min_d, max_d in conn.execute(text("""
            SELECT ticker, count(*), min(date), max(date)
            FROM benchmark_prices GROUP BY ticker ORDER BY ticker
        """)):
            print(f"  {ticker:6s} rows={count:>6,} range={min_d}..{max_d}")

        section("VERDICT - what the Board page will render")
        series_all = total_approved > 0 and scalar(conn, f"""
            WITH {APPROVED_CTE}
            SELECT count(*) FROM approved a
            JOIN companies c ON c.id = (SELECT company_id FROM analyses WHERE id = a.id)
            WHERE c.ticker_symbol IS NOT NULL
        """) > 0

        series_1y = approved_recent_entry > 0
        purchased = scalar(conn, "SELECT count(*) FROM portfolio_purchases")

        print(f"  approved seriesAll : {'PRESENT' if series_all else 'None'}")
        print(f"  approved series1y  : {'PRESENT' if series_1y else 'None'}")
        print(f"  PortfolioPurchase rows: {purchased:,}")

        if series_all and not series_1y:
            print(
                "\n  >>> REPRODUCED: seriesAll is present but series1y is None.\n"
                "      Before the fix, admin/board.html aborted on `if (!data.seriesAll\n"
                "      || !data.series1y) return;` so BOTH Board charts stayed blank,\n"
                "      while /admin/analyst/<id> (which guards each chart separately)\n"
                "      still rendered the inception chart."
            )
        elif series_all and series_1y:
            print(
                "\n  Both series exist in production, so the Board chart should draw.\n"
                "  If it is still blank, the cause is different - check the app log\n"
                "  for the 'board.page:' line and the browser console."
            )


if __name__ == "__main__":
    main()
