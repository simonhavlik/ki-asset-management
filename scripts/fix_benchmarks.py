#!/usr/bin/env python3
"""
Script to fix benchmark data issues by:
1. Fetching 5 years of benchmark data
2. Clearing all caches
3. Triggering recalculation

Run this from the project root:
    python scripts/fix_benchmarks.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, timedelta
from app import create_app
from app.extensions import db
from app.models import BenchmarkPrice
from app.utils.overview_cache import invalidate_cache
from app.utils.neon_cache import invalidate_all_public_cache, invalidate_board_cache

app = create_app()

def update_benchmarks():
    """Fetch 5 years of benchmark data."""
    from app.utils.yahooquery_helper import fetch_prices
    
    tickers = ['SPY', 'VT', 'EEMS']
    end_date = date.today()
    start_date = end_date - timedelta(days=1825)  # 5 years
    
    print(f"Fetching benchmark data from {start_date} to {end_date}...")
    
    total_updated = 0
    
    for ticker in tickers:
        try:
            print(f"  Fetching {ticker}...", end=" ")
            df = fetch_prices(ticker, start_date, end_date)
            
            if df.empty:
                print(f"NO DATA")
                continue
            
            # Get existing dates
            existing_dates = {bp.date for bp in BenchmarkPrice.query.filter_by(ticker=ticker).all()}
            
            new_records = 0
            for _, row in df.iterrows():
                price_date = row['Date'].date() if hasattr(row['Date'], 'date') else row['Date']
                
                if price_date in existing_dates:
                    continue
                
                bp = BenchmarkPrice(
                    ticker=ticker,
                    date=price_date,
                    close_price=row['close_price']
                )
                db.session.add(bp)
                new_records += 1
            
            db.session.commit()
            total_updated += new_records
            print(f"+{new_records} records")
            
        except Exception as e:
            db.session.rollback()
            print(f"ERROR: {e}")
    
    print(f"\nTotal new benchmark records: {total_updated}")
    return total_updated

def clear_caches():
    """Clear all caches."""
    print("\nClearing caches...")
    
    try:
        invalidate_all_public_cache()
        print("  - Public caches cleared")
    except Exception as e:
        print(f"  - Public caches error: {e}")
    
    try:
        invalidate_board_cache()
        print("  - Board cache cleared")
    except Exception as e:
        print(f"  - Board cache error: {e}")
    
    try:
        invalidate_cache()  # Clear all overview caches
        print("  - Overview caches cleared")
    except Exception as e:
        print(f"  - Overview cache error: {e}")
    
    print("All caches cleared!")

def main():
    with app.app_context():
        print("=" * 60)
        print("BENCHMARK FIX SCRIPT")
        print("=" * 60)
        
        # Step 1: Update benchmarks
        update_benchmarks()
        
        # Step 2: Clear caches
        clear_caches()
        
        print("\n" + "=" * 60)
        print("DONE!")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Go to the Overview page")
        print("2. For each filter (All Stocks, Approved + Neutral, etc.):")
        print("   - Select the filter")
        print("   - Click 'Recalculate All Now'")
        print("   - Wait for it to complete")
        print("\nThe benchmark charts should now display correctly!")

if __name__ == '__main__':
    main()
