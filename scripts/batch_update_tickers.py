#!/usr/bin/env python3
"""Batch update missing ticker symbols using Brave Search integration."""
import sys
sys.path.insert(0, '.')

from app import create_app
from app.models import db, Company
from app.utils.yfinance_helper import get_validated_ticker_for_company
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def update_missing_tickers():
    app = create_app()
    with app.app_context():
        missing = db.session.query(Company).filter(Company.ticker_symbol.is_(None)).all()
        total = len(missing)
        logger.info(f"Found {total} companies missing ticker symbols.")
        
        updated = 0
        for i, company in enumerate(missing, start=1):
            logger.info(f"[{i}/{total}] Processing '{company.name}' (sector: {company.sector})...")
            ticker = get_validated_ticker_for_company(company.name, hint=company.sector)
            if ticker:
                logger.info(f"    Found ticker: {ticker}")
                company.ticker_symbol = ticker
                updated += 1
            else:
                logger.warning(f"    No ticker found.")
        
        if updated:
            db.session.commit()
            logger.info(f"Successfully updated {updated} companies.")
        else:
            logger.info("No updates made.")
        
        # Print summary
        still_missing = db.session.query(Company).filter(Company.ticker_symbol.is_(None)).count()
        logger.info(f"Remaining missing tickers: {still_missing}")
        return updated

if __name__ == '__main__':
    update_missing_tickers()