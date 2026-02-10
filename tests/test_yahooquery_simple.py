#!/usr/bin/env python3
"""
Simple test for yahooquery functionality.
"""

import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 60)
print("YAHOOQUERY QUICK TEST")
print("=" * 60)

# Test 1: Direct yahooquery
print("\n1. Testing direct yahooquery import...")
try:
    from yahooquery import Ticker
    print("   ✓ yahooquery imported")
    
    print("\n2. Fetching AAPL data...")
    t = Ticker("AAPL")
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    data = t.history(start=start_date.strftime('%Y-%m-%d'), 
                     end=end_date.strftime('%Y-%m-%d'))
    print(f"   ✓ Fetched {len(data)} days of data")
    print(f"   Latest close: ${data['close'].iloc[-1]:.2f}")
except Exception as e:
    print(f"   ✗ Error: {e}")
    sys.exit(1)

# Test 2: Via helper module
print("\n3. Testing via helper module...")
try:
    os.environ['USE_LOCAL_SQLITE'] = 'True'
    os.environ['SECRET_KEY'] = 'test'
    
    from app.utils.yahooquery_helper import fetch_prices, search_tickers
    
    df = fetch_prices("MSFT", start_date, end_date)
    print(f"   ✓ Fetched {len(df)} records via helper")
    print(f"   Columns: {list(df.columns)}")
    
    results = search_tickers("Apple")
    print(f"   ✓ Search returned {len(results)} results")
    
except Exception as e:
    print(f"   ✗ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("✓ ALL TESTS PASSED")
print("=" * 60)
print("\nyahooquery is working correctly!")
print("You can safely deploy to Render.")
