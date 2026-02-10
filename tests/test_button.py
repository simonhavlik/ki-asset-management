#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')
from app import create_app
from app.extensions import db
from app.models import User
app = create_app()
app.config['TESTING'] = True
app.config['WTF_CSRF_ENABLED'] = False
with app.app_context():
    # Get an analyst id
    analyst = User.query.filter_by(is_admin=False).first()
    if not analyst:
        print('No analyst found')
        sys.exit(1)
    analyst_id = analyst.id
    print(f'Testing analyst_details for analyst_id={analyst_id}')
    # Use test client
    with app.test_client() as client:
        # Simulate admin login (need admin user)
        admin = User.query.filter_by(is_admin=True).first()
        if not admin:
            print('No admin user found')
            sys.exit(1)
        # login via session (since we can't use password)
        from flask_login import login_user
        with client.session_transaction() as sess:
            sess['_user_id'] = str(admin.id)
            sess['_fresh'] = True
        # Make GET request
        resp = client.get(f'/admin/analyst/{analyst_id}/details')
        print(f'Status code: {resp.status_code}')
        if resp.status_code != 200:
            print(f'Response data: {resp.data[:500]}')
        else:
            print('Page loaded successfully')
            # Check if chart canvas present
            if b'returnsChart' in resp.data:
                print('Chart canvas found')
            else:
                print('Chart canvas missing')
        # Also test with filter parameter
        resp2 = client.get(f'/admin/analyst/{analyst_id}/details?filter=approved_only')
        print(f'With filter status: {resp2.status_code}')