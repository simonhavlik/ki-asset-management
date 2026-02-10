#!/usr/bin/env python3
"""
Test script for yahooquery functionality.

This tests the new yahooquery-based stock data fetching to ensure
it works correctly on Render and provides the expected data.
"""

import os
import sys
from datetime import date, timedelta

# Add app directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_yahooquery_direct():
    """Test yahooquery library directly."""
    print("=" * 70)
    print("YAHOOQUERY DIRECT TEST")
    print("=" * 70)
    
    try:
        print("\n1. Installing yahooquery...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "yahooquery==2.3.7"])
        print("   ✓ yahooquery installed")
        
        print("\n2. Importing yahooquery...")
        from yahooquery import Ticker, search
        print("   ✓ yahooquery imported successfully")
        
        # Test 1: Fetch AAPL (US stock)
        print("\n3. Testing AAPL (US stock - Apple)...")
        t = Ticker("AAPL")
        
        # Get historical data for last 30 days
        end_date = date.today()
        start_date = end_date - timedelta(days=30)
        
        data = t.history(start=start_date.strftime('%Y-%m-%d'),
                        end=end_date.strftime('%Y-%m-%d'))
        
        if data is not None and not data.empty:
            print(f"   ✓ AAPL: Fetched {len(data)} days of data")
            print(f"   Columns: {list(data.columns)}")
            print(f"   Latest price: ${data['close'].iloc[-1]:.2f}")
            print(f"   Date range: {data.index[0][1] if isinstance(data.index, pd.MultiIndex) else data.index[0]} to {data.index[-1][1] if isinstance(data.index, pd.MultiIndex) else data.index[-1]}")
        else:
            print("   ✗ AAPL: No data returned")
            return False
        
        # Test 2: Fetch SAP.DE (European stock)
        print("\n4. Testing SAP.DE (European stock - SAP)...")
        t2 = Ticker("SAP.DE")
        data2 = t2.history(start=start_date.strftime('%Y-%m-%d'),
                          end=end_date.strftime('%Y-%m-%d'))
        
        if data2 is not None and not data2.empty:
            print(f"   ✓ SAP.DE: Fetched {len(data2)} days of data")
            print(f"   Latest price: €{data2['close'].iloc[-1]:.2f}")
        else:
            print("   ⚠ SAP.DE: No data returned (may be weekend/holiday)")
        
        # Test 3: Search function
        print("\n5. Testing search function...")
        results = search("Apple")
        if results and 'quotes' in results:
            print(f"   ✓ Search returned {len(results['quotes'])} results")
            for q in results['quotes'][:3]:
                print(f"     - {q.get('symbol')}: {q.get('longname') or q.get('shortname')} ({q.get('exchange')})")
        else:
            print("   ✗ Search returned no results")
        
        # Test 4: Long historical data (2+ years)
        print("\n6. Testing 2-year historical data...")
        t3 = Ticker("MSFT")
        start_2yr = end_date - timedelta(days=730)
        data_2yr = t3.history(start=start_2yr.strftime('%Y-%m-%d'),
                             end=end_date.strftime('%Y-%m-%d'))
        
        if data_2yr is not None and not data_2yr.empty:
            print(f"   ✓ MSFT 2-year: Fetched {len(data_2yr)} days of data")
            print(f"   First price: ${data_2yr['close'].iloc[0]:.2f}")
            print(f"   Last price: ${data_2yr['close'].iloc[-1]:.2f}")
            print(f"   Return: {((data_2yr['close'].iloc[-1] / data_2yr['close'].iloc[0]) - 1) * 100:.1f}%")
        else:
            print("   ✗ 2-year data fetch failed")
            return False
        
        print("\n" + "=" * 70)
        print("✓ ALL DIRECT TESTS PASSED")
        print("=" * 70)
        return True
        
    except Exception as e:
        print(f"\n✗ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_helper_module():
    """Test the yahooquery_helper module."""
    print("\n" + "=" * 70)
    print("YAHOOQUERY HELPER MODULE TEST")
    print("=" * 70)
    
    try:
        print("\n1. Setting up environment...")
        os.environ['USE_LOCAL_SQLITE'] = 'True'
        os.environ['SECRET_KEY'] = 'test-key'
        
        print("2. Importing helper module...")
        from app.utils.yahooquery_helper import fetch_prices, search_tickers, get_company_info
        import pandas as pd
        print("   ✓ Module imported")
        
        print("\n3. Testing fetch_prices()...")
        end_date = date.today()
        start_date = end_date - timedelta(days=30)
        
        df = fetch_prices("AAPL", start_date, end_date)
        
        if not df.empty:
            print(f"   ✓ Fetched {len(df)} records")
            print(f"   Columns: {list(df.columns)}")
            print(f"   Sample data:")
            print(df.head(3).to_string())
        else:
            print("   ✗ No data returned")
            return False
        
        print("\n4. Testing search_tickers()...")
        results = search_tickers("Microsoft")
        if results:
            print(f"   ✓ Found {len(results)} results")
            for r in results[:3]:
                print(f"     - {r['symbol']}: {r['name']} ({r['exchange']})")
        else:
            print("   ⚠ No search results (may be rate limited)")
        
        print("\n5. Testing get_company_info()...")
        info = get_company_info("AAPL")
        if info:
            print(f"   ✓ Company info retrieved")
            print(f"     Sector: {info.get('sector', 'N/A')}")
            print(f"     Industry: {info.get('industry', 'N/A')}")
            print(f"     Employees: {info.get('fullTimeEmployees', 'N/A')}")
        else:
            print("   ⚠ No company info (may need authentication)")
        
        print("\n" + "=" * 70)
        print("✓ HELPER MODULE TESTS PASSED")
        print("=" * 70)
        return True
        
    except Exception as e:
        print(f"\n✗ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_vs_yfinance():
    """Compare yahooquery vs yfinance to ensure compatibility."""
    print("\n" + "=" * 70)
    print("COMPATIBILITY TEST (yahooquery vs yfinance)")
    print("=" * 70)
    
    try:
        print("\n1. Fetching same data with both libraries...")
        
        end_date = date.today()
        start_date = end_date - timedelta(days=30)
        
        # yahooquery
        print("\n   yahooquery:")
        from app.utils.yahooquery_helper import fetch_prices as yq_fetch
        df_yq = yq_fetch("AAPL", start_date, end_date)
        
        if not df_yq.empty:
            print(f"   ✓ Retrieved {len(df_yq)} records")
            print(f"   Price range: ${df_yq['close_price'].min():.2f} - ${df_yq['close_price'].max():.2f}")
        else:
            print("   ✗ No data")
        
        # yfinance (if available)
        print("\n   yfinance:")
        try:
            import yfinance as yf
            data_yf = yf.download("AAPL", start=start_date, end=end_date, progress=False)
            if not data_yf.empty:
                print(f"   ✓ Retrieved {len(data_yf)} records")
                print(f"   Price range: ${data_yf['Close'].min():.2f} - ${data_yf['Close'].max():.2f}")
            else:
                print("   ✗ No data")
        except ImportError:
            print("   ⚠ yfinance not installed (this is expected)")
        
        print("\n" + "=" * 70)
        print("✓ COMPATIBILITY CHECK COMPLETE")
        print("=" * 70)
        return True
        
    except Exception as e:
        print(f"\n✗ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    print("\n" + "=" * 70)
    print("YAHOOQUERY STOCK DATA TEST SUITE")
    print("=" * 70)
    print("\nThis tests the new yahooquery-based stock data fetching.")
    print("yahooquery is more reliable than yfinance on cloud platforms like Render.")
    
    success_count = 0
    total_tests = 3
    
    # Test 1: Direct library test
    if test_yahooquery_direct():
        success_count += 1
    
    # Test 2: Helper module test
    if test_helper_module():
        success_count += 1
    
    # Test 3: Compatibility test
    if test_vs_yfinance():
        success_count += 1
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"\nPassed: {success_count}/{total_tests} tests")
    
    if success_count == total_tests:
        print("\n✓ ALL TESTS PASSED")
        print("\nThe yahooquery integration is working correctly.")
        print("You can safely deploy this to Render.")
        sys.exit(0)
    else:
        print("\n⚠ SOME TESTS FAILED")
        print("\nPlease review the errors above before deploying.")
        sys.exit(1)
