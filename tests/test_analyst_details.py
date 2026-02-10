#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')
from app import create_app
from app.extensions import db
from app.models import User
app = create_app()
with app.app_context():
    # Get first analyst id
    analyst = User.query.filter_by(is_admin=False).first()
    if analyst:
        print(f'Testing analyst_details for analyst_id={analyst.id}')
        from app.admin.routes import analyst_details
        try:
            # Simulate request with flask test client
            with app.test_client() as client:
                # login as admin? but we can just call the view function directly
                pass
        except Exception as e:
            print(f'Error importing: {e}')
    else:
        print('No analyst found')
    # Check if any analyst has performance data
    from app.utils.performance import PerformanceCalculator
    calculator = PerformanceCalculator()
    perf = calculator.get_all_analysts_performance()
    print(f'Total analysts with performance: {len(perf)}')
    for p in perf[:3]:
        print(p)