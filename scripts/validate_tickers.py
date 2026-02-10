#!/usr/bin/env python3
"""Validate ticker symbols with yfinance and attempt to fix missing suffixes."""
import sys
sys.path.insert(0, '.')

from app import create_app
from app.models import db, Company
from app.utils.yfinance_helper import fetch_prices
from datetime import date, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SUFFIXES = ['.HK', '.T', '.SA', '.AS', '.L', '.TO', '.PR', '.DE', '.PA', '.HE', '.OL', '.CO', '.MX', '.SI', '.KS', '.TWO', '.VI']

def validate_and_fix():
    app = create_app()
    with app.app_context():
        companies = db.session.query(Company).filter(Company.ticker_symbol.isnot(None)).all()
        logger.info(f"Validating {len(companies)} companies with tickers.")
        
        for company in companies:
            ticker = company.ticker_symbol
            logger.info(f"Checking {company.name}: {ticker}")
            # Try to fetch prices for a recent period (last 7 days)
            end = date.today()
            start = end - timedelta(days=7)
            data = fetch_prices(ticker, start, end)
            if not data.empty:
                logger.info(f"  OK: price data available")
                continue
            
            logger.warning(f"  No price data for {ticker}. Trying suffix variations...")
            # Try adding suffixes
            for suffix in SUFFIXES:
                if ticker.endswith(suffix):
                    continue
                new_ticker = ticker + suffix
                data = fetch_prices(new_ticker, start, end)
                if not data.empty:
                    logger.info(f"  Found valid ticker: {new_ticker}")
                    company.ticker_symbol = new_ticker
                    db.session.commit()
                    break
            else:
                logger.error(f"  No valid suffix found for {ticker}")
        
        logger.info("Validation complete.")

if __name__ == '__main__':
    validate_and_fix()