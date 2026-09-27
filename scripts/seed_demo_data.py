#!/usr/bin/env python
"""
Seed a small, realistic demo dataset for local testing.

Motivation
----------
The Board page chart ("/admin/board") and the per-analyst chart
("/admin/analyst/<id>") draw their series from *different* code paths, so
reproducing a chart bug needs real rows in every table involved: companies,
analyses, votes, stock prices and performance calculations.

This script creates such a dataset locally (SQLite) so both pages can be
exercised. Everything it creates is prefixed ``DEMO`` so ``--reset`` can remove
exactly what it added.

The ``--days-ago`` flag is the interesting knob. The Board page marks an
analysis as "Board approved" when yes-votes > no-votes, and builds two series:
an inception series and a 1-year series. When every analysis is older than one
year, the 1-year series comes back ``None``.

Usage
-----
    # Exercise the "all positions older than 1 year" case (reproduces the bug)
    venv/bin/python scripts/seed_demo_data.py --days-ago 700

    # Exercise the "recent positions" case (charts have both series)
    venv/bin/python scripts/seed_demo_data.py --reset --days-ago 100

    # Remove demo rows
    venv/bin/python scripts/seed_demo_data.py --reset
"""

import argparse
import os
import random
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import (  # noqa: E402
    Analysis,
    Company,
    CompanySectorCache,
    CompanyTickerMapping,
    PerformanceCalculation,
    StockPrice,
    User,
    Vote,
    analysis_analysts,
)

DEMO_PREFIX = "DEMO "
DEMO_ANALYST_EMAIL = "analyst.demo@klubinvestoru.com"
DEMO_ANALYST_PASSWORD = "TestPass123!"

# (ticker, sector, annual growth %) - deliberately varied so charts have shape.
UNIVERSE = [
    ("AAPL", "Technology", 0.28),
    ("MSFT", "Technology", 0.22),
    ("JNJ", "Healthcare", 0.06),
    ("XOM", "Energy", -0.09),
    ("KO", "Consumer Staples", 0.11),
]


def reset_demo_data() -> None:
    """Delete everything this script previously created."""
    companies = Company.query.filter(Company.name.like(f"{DEMO_PREFIX}%")).all()
    company_ids = [c.id for c in companies]
    deleted = {"companies": len(companies)}

    if company_ids:
        analyses = Analysis.query.filter(Analysis.company_id.in_(company_ids)).all()
        analysis_ids = [a.id for a in analyses]
        deleted["analyses"] = len(analyses)

        if analysis_ids:
            deleted["performance_calculations"] = PerformanceCalculation.query.filter(
                PerformanceCalculation.analysis_id.in_(analysis_ids)
            ).delete(synchronize_session=False)
            deleted["votes"] = Vote.query.filter(
                Vote.analysis_id.in_(analysis_ids)
            ).delete(synchronize_session=False)
            db.session.execute(
                analysis_analysts.delete().where(
                    analysis_analysts.c.analysis_id.in_(analysis_ids)
                )
            )
        deleted["stock_prices"] = StockPrice.query.filter(
            StockPrice.company_id.in_(company_ids)
        ).delete(synchronize_session=False)
        deleted["sector_cache"] = CompanySectorCache.query.filter(
            CompanySectorCache.company_id.in_(company_ids)
        ).delete(synchronize_session=False)
        Analysis.query.filter(Analysis.company_id.in_(company_ids)).delete(
            synchronize_session=False
        )

    deleted["ticker_mappings"] = CompanyTickerMapping.query.filter(
        CompanyTickerMapping.company_name.like(f"{DEMO_PREFIX}%")
    ).delete(synchronize_session=False)

    analyst = User.query.filter_by(email=DEMO_ANALYST_EMAIL).first()
    if analyst:
        db.session.delete(analyst)
        deleted["demo_analyst"] = 1

    for company in companies:
        db.session.delete(company)

    db.session.commit()
    print("reset:", ", ".join(f"{k}={v}" for k, v in deleted.items()))


def get_or_create_demo_analyst() -> User:
    user = User.query.filter_by(email=DEMO_ANALYST_EMAIL).first()
    if user is None:
        user = User(
            email=DEMO_ANALYST_EMAIL,
            full_name="Demo Analyst",
            is_admin=False,
            is_active=True,
            email_verified=True,
        )
        user.set_password(DEMO_ANALYST_PASSWORD)
        db.session.add(user)
        db.session.flush()
        print(f"created demo analyst {DEMO_ANALYST_EMAIL} / {DEMO_ANALYST_PASSWORD}")
    return user


def get_admin() -> User:
    admin = User.query.filter_by(is_admin=True).order_by(User.id).first()
    if admin is None:
        raise SystemExit(
            "No admin user found. Run: venv/bin/python -m flask create-admin"
        )
    return admin


def monthly_dates(start: date, end: date):
    """Yield the first of each month between start and end, inclusive."""
    current = start.replace(day=1)
    while current <= end:
        yield current
        current = (
            current.replace(year=current.year + 1, month=1)
            if current.month == 12
            else current.replace(month=current.month + 1)
        )


def seed(days_ago: int, count: int) -> None:
    admin = get_admin()
    analyst = get_or_create_demo_analyst()
    today = date.today()
    rng = random.Random(20260927)  # deterministic output

    for ticker, sector, annual_growth in UNIVERSE[:count]:
        name = f"{DEMO_PREFIX}{ticker} Inc"
        company = Company(name=name, ticker_symbol=ticker, sector=sector)
        db.session.add(company)
        db.session.flush()

        db.session.add(CompanyTickerMapping(
            company_name=name, ticker_symbol=ticker,
            source="demo", is_other_event=False,
        ))
        db.session.add(CompanySectorCache(
            company_id=company.id, sector=sector, industry=sector,
        ))

        analysis_date = today - timedelta(days=days_ago)
        analysis = Analysis(
            company_id=company.id,
            analysis_date=analysis_date,
            status="On Watchlist",
            comment=f"{DEMO_PREFIX}seeded analysis for {ticker}",
            purchase_date=analysis_date,
            is_in_portfolio=True,
        )
        db.session.add(analysis)
        db.session.flush()

        # Link the analyst so /admin/analyst/<id> has data for them.
        db.session.execute(analysis_analysts.insert().values(
            analysis_id=analysis.id, user_id=analyst.id, role="analyst",
        ))

        # Board approval == yes votes strictly greater than no votes.
        db.session.add(Vote(analysis_id=analysis.id, user_id=admin.id, vote=True))

        # Price history: one point just before the analysis date (so an entry
        # price exists) then monthly points up to today.
        entry_price = 100.0
        db.session.add(StockPrice(
            company_id=company.id, date=analysis_date - timedelta(days=3),
            close_price=round(entry_price, 2),
        ))
        for when in monthly_dates(analysis_date, today):
            elapsed_years = (when - analysis_date).days / 365.0
            grown = entry_price * (1 + annual_growth * elapsed_years)
            wobble = rng.uniform(-0.02, 0.02)
            db.session.add(StockPrice(
                company_id=company.id, date=when,
                close_price=round(grown * (1 + wobble), 2),
            ))

        prev = StockPrice.query.filter(
            StockPrice.company_id == company.id,
            StockPrice.date <= today,
        ).order_by(StockPrice.date.desc()).first()
        price_now = float(prev.close_price) if prev else entry_price
        return_pct = (price_now - entry_price) / entry_price * 100

        # Board stat tiles read PerformanceCalculation; charts read StockPrice.
        db.session.add(PerformanceCalculation(
            analysis_id=analysis.id,
            calculation_date=today,
            price_at_analysis=round(entry_price, 2),
            price_current=round(price_now, 2),
            return_pct=round(return_pct, 2),
        ))
        print(
            f"  {ticker:5s} analysis={analysis_date} entry={entry_price:.2f} "
            f"now={price_now:.2f} return={return_pct:+.2f}%"
        )

    db.session.commit()

    print(
        f"\nseeded {count} demo companies, all with analysis_date "
        f"{today - timedelta(days=days_ago)} ({days_ago} days ago)"
    )
    if days_ago > 365:
        print(
            "NOTE: every analysis is older than 1 year, so the Board page's "
            "1-year series will be None. If the Board chart disappears while the "
            "per-analyst chart still renders, that is the bug being reproduced."
        )


def assert_local_database(app, force: bool) -> None:
    """Refuse to seed anything that is not a local SQLite database.

    .env mirrors the deployment configuration, which means DATABASE_URL can point
    at the live Neon/Postgres database. Seeding demo rows into production would be
    destructive, so require an explicit opt-in for anything non-local.
    """
    uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    looks_local = uri.startswith('sqlite:') and (
        '//' in uri and not any(
            host in uri for host in ('@', 'neon.tech', 'amazonaws', 'render.com')
        )
    )
    if looks_local or force:
        if not looks_local:
            print(f"WARNING: --force given, writing to NON-LOCAL database: {uri.split('@')[-1][:60]}")
        return
    raise SystemExit(
        "REFUSING to seed demo data.\n"
        f"  Database is not local SQLite: {uri.split('@')[-1][:60]}\n"
        "  This looks like the production database. Demo rows would pollute it.\n"
        "  To seed a local database, either:\n"
        "    * set USE_LOCAL_SQLITE=True (and remove/blank DATABASE_URL) in .env, or\n"
        "    * re-run with --force-i-know-this-is-not-local\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--days-ago", type=int, default=700,
        help="how long ago the seeded analyses were made (default: 700)",
    )
    parser.add_argument(
        "--companies", type=int, default=3,
        help="how many companies to seed from the demo universe (default: 3)",
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="delete existing demo data before seeding",
    )
    parser.add_argument(
        "--reset-only", action="store_true",
        help="delete existing demo data and exit",
    )
    parser.add_argument(
        "--force-i-know-this-is-not-local", dest="force", action="store_true",
        help="allow running against a non-local (e.g. production) database",
    )
    args = parser.parse_args()

    app = create_app()
    assert_local_database(app, args.force)
    with app.app_context():
        if args.reset or args.reset_only:
            reset_demo_data()
        if args.reset_only:
            return
        seed(args.days_ago, args.companies)


if __name__ == "__main__":
    main()
