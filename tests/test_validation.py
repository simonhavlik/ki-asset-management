#!/usr/bin/env python3
"""Test the validated ticker lookup."""
import sys
sys.path.insert(0, '.')

from app import create_app
from app.utils.yfinance_helper import get_validated_ticker_for_company

app = create_app()
with app.app_context():
    test_cases = [
        ("Apple", "Technology"),
        ("Fractal Gaming Group", "Gaming"),
        ("Banco Inter", "Financial"),
        ("Bocconi collab", ""),
        ("Japonský SaaS", "Software"),
        ("Sport retail sector", "Retail"),
    ]
    for name, hint in test_cases:
        print(f"\n--- {name} (hint: {hint}) ---")
        ticker = get_validated_ticker_for_company(name, hint=hint, max_attempts=2)
        print(f"Result: {ticker}")
        if ticker:
            # Check price data
            from app.utils.yfinance_helper import _ticker_has_price_data
            has = _ticker_has_price_data(ticker)
            print(f"Has price data: {has}")