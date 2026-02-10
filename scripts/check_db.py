#!/usr/bin/env python3
"""Check database counts."""
import sys
sys.path.insert(0, '.')

from app import create_app
from app.models import db, Company, Analysis, StockPrice
from sqlalchemy import func

app = create_app()
with app.app_context():
    total_companies = db.session.query(func.count(Company.id)).scalar()
    missing_ticker = db.session.query(func.count(Company.id)).filter(Company.ticker_symbol.is_(None)).scalar()
    total_analyses = db.session.query(func.count(Analysis.id)).scalar()
    analyses_with_ticker = db.session.query(func.count(Analysis.id)).join(Company).filter(Company.ticker_symbol.isnot(None)).scalar()
    analyses_without_ticker = total_analyses - analyses_with_ticker
    
    # Count missing price data
    # For each analysis we need price_at_analysis and price_current; but we can count analyses with missing price entries.
    # Let's just get a rough number: analyses where company has ticker but no stock price for that date.
    # Complex, so skip for now.
    
    print(f"Total companies: {total_companies}")
    print(f"Companies missing ticker: {missing_ticker}")
    print(f"Total analyses: {total_analyses}")
    print(f"Analyses with ticker: {analyses_with_ticker}")
    print(f"Analyses without ticker: {analyses_without_ticker}")
    
    # List some missing ticker companies
    missing = db.session.query(Company).filter(Company.ticker_symbol.is_(None)).limit(10).all()
    print("\nSample missing ticker companies:")
    for c in missing:
        print(f"  - {c.name} (sector: {c.sector})")