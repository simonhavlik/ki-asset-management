#!/usr/bin/env python3
"""Test Brave Search integration with app context."""
import sys
sys.path.insert(0, '.')

from app import create_app
from app.utils.yfinance_helper import get_ticker_for_company
from app.models import db, Company

def test_missing_companies():
    app = create_app()
    with app.app_context():
        missing = db.session.query(Company).filter(Company.ticker_symbol.is_(None)).limit(5).all()
        print(f"Testing {len(missing)} missing companies...")
        for company in missing:
            print(f"\nCompany: {company.name} (sector: {company.sector})")
            ticker = get_ticker_for_company(company.name, hint=company.sector)
            if ticker:
                print(f"  -> Found ticker: {ticker}")
                # Optionally update the database (uncomment to apply)
                # company.ticker_symbol = ticker
                # db.session.commit()
            else:
                print(f"  -> No ticker found")
        
        # Test a few known companies to verify API works
        print("\n--- Testing known companies ---")
        test_cases = [
            ("Apple", "Technology"),
            ("Microsoft", "Technology"),
            ("Tesla", "Automotive"),
            ("BYD Company", "Automotive"),
            ("NVIDIA", "Technology"),
        ]
        for name, sector in test_cases:
            ticker = get_ticker_for_company(name, hint=sector)
            print(f"{name} ({sector}) -> {ticker}")

if __name__ == '__main__':
    test_missing_companies()