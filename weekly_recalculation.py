#!/usr/bin/env python3
"""
Weekly Recalculation Job for KI Asset Management

This script should be run weekly (e.g., via cron) to recalculate all performance data
and refresh all caches. It can also be run manually for testing.

Usage:
    python weekly_recalculation.py
    
Cron setup (runs every Sunday at 3 AM):
    0 3 * * 0 cd /path/to/app && python weekly_recalculation.py >> logs/weekly_recalculation.log 2>&1
"""

import os
import sys
import argparse
from datetime import datetime

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    parser = argparse.ArgumentParser(description='Weekly recalculation job for KI Asset Management')
    parser.add_argument('--force', action='store_true', help='Force recalculation even if not due')
    parser.add_argument('--check-only', action='store_true', help='Only check if recalculation is due')
    args = parser.parse_args()
    
    # Import after setting up path
    from app import create_app
    from app.utils.neon_cache import (
        run_weekly_recalculation,
        should_run_weekly_recalculation,
        get_last_recalculation_time
    )
    
    app = create_app()
    
    with app.app_context():
        # Check if we should run
        last_run = get_last_recalculation_time()
        should_run = should_run_weekly_recalculation() or args.force
        
        if args.check_only:
            if last_run:
                days_since = (datetime.now() - last_run).days
                print(f"Last recalculation: {last_run.strftime('%Y-%m-%d %H:%M:%S')} ({days_since} days ago)")
            else:
                print("No previous recalculation found")
            print(f"Should run: {should_run}")
            return 0 if should_run else 1
        
        if not should_run and not args.force:
            print("Weekly recalculation not due yet. Use --force to run anyway.")
            if last_run:
                days_since = (datetime.now() - last_run).days
                print(f"Last run: {days_since} days ago")
            return 0
        
        # Run recalculation
        print("=" * 70)
        print(f"Starting {'forced ' if args.force else ''}weekly recalculation...")
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70)
        
        try:
            results = run_weekly_recalculation()
            
            print("\n" + "=" * 70)
            print("RECALCULATION COMPLETE")
            print("=" * 70)
            print(f"Performance calculations: {results['performance_calculated']} analyses")
            print(f"Caches cleared: {', '.join(results['caches_cleared'])}")
            print(f"Caches warmed: {', '.join(results['caches_warmed'])}")
            print(f"Time elapsed: {results['elapsed_seconds']:.1f} seconds")
            
            if results['errors']:
                print(f"\nWARNINGS/ERRORS ({len(results['errors'])}):")
                for error in results['errors']:
                    print(f"  - {error}")
            
            print("=" * 70)
            
            return 0 if not results['errors'] else 1
            
        except Exception as e:
            print(f"\nERROR: Recalculation failed: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            return 1

if __name__ == '__main__':
    sys.exit(main())
