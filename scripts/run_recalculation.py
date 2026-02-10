#!/usr/bin/env python3
"""Run performance recalculation and show results."""
import sys
sys.path.insert(0, '.')

from app import create_app
from app.utils.performance import PerformanceCalculator

app = create_app()
with app.app_context():
    calculator = PerformanceCalculator()
    result = calculator.recalculate_all()
    print("Recalculation result:")
    print(f"  Analyses processed: {result.get('analyses_processed', 0)}")
    print(f"  Missing ticker: {result.get('missing_ticker', 0)}")
    print(f"  Missing price: {result.get('missing_price', 0)}")
    print(f"  Errors: {result.get('errors', 0)}")
    
    # Also get analyst performance to see how many analysts have data
    analyst_perf = calculator.get_all_analysts_performance()
    print(f"\nAnalyst performance count: {len(analyst_perf)}")
    for a in analyst_perf:
        if a['num_analyses'] > 0:
            print(f"  {a['analyst_name']}: {a['num_analyses']} analyses, avg return {a['avg_return']}%")