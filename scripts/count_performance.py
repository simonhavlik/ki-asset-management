#!/usr/bin/env python3
"""Count performance calculations."""
import sys
sys.path.insert(0, '.')

from app import create_app
from app.models import db, PerformanceCalculation, Analysis

app = create_app()
with app.app_context():
    total_pc = db.session.query(db.func.count(PerformanceCalculation.id)).scalar()
    total_analyses = db.session.query(db.func.count(Analysis.id)).scalar()
    analyses_with_pc = db.session.query(db.func.count(db.distinct(PerformanceCalculation.analysis_id))).scalar()
    print(f"Total PerformanceCalculation records: {total_pc}")
    print(f"Total analyses: {total_analyses}")
    print(f"Analyses with at least one performance record: {analyses_with_pc}")
    
    # Count analyses with ticker
    from app.models import Company
    analyses_with_ticker = db.session.query(Analysis).join(Company).filter(Company.ticker_symbol.isnot(None)).count()
    print(f"Analyses with ticker: {analyses_with_ticker}")
    
    # Count analyses with missing price data
    # (harder, but we can approximate)
    pass