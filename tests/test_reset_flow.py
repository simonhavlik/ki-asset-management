#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')

from app import create_app
from app.models import User, PasswordResetToken
from app.auth.utils import create_password_reset_token
from datetime import datetime, timedelta

app = create_app()
app.config['WTF_CSRF_ENABLED'] = False  # Disable CSRF for testing
app.config['TESTING'] = True

with app.app_context():
    # Ensure a user exists
    user = User.query.first()
    if not user:
        print("No user found, creating test user")
        user = User(
            email='test@example.com',
            is_admin=False,
            is_active=True,
            email_verified=True
        )
        user.set_password('oldpassword')
        from app.extensions import db
        db.session.add(user)
        db.session.commit()
    
    # Create a token
    token = create_password_reset_token(user, token_type='reset', expires_hours=1)
    print(f"Token: {token}")
    
    # Simulate GET request to reset password page
    with app.test_client() as client:
        # GET reset page
        resp = client.get(f'/auth/reset-password/{token}')
        assert resp.status_code == 200, f"GET failed with {resp.status_code}"
        print("✓ GET reset page successful")
        
        # Ensure token still valid (not consumed)
        from app.auth.utils import validate_token
        user_check = validate_token(token, token_type='reset', consume=False)
        assert user_check is not None, "Token consumed prematurely"
        print("✓ Token not consumed after GET")
        
        # POST new password
        resp = client.post(f'/auth/reset-password/{token}', data={
            'password': 'NewSecurePassword123',
            'confirm_password': 'NewSecurePassword123',
        }, follow_redirects=False)
        # Expect redirect (302) to login or dashboard
        assert resp.status_code == 302, f"POST failed with {resp.status_code}"
        print("✓ POST reset successful")
        
        # Verify token is now consumed
        user_check = validate_token(token, token_type='reset', consume=False)
        assert user_check is None, "Token not consumed after POST"
        print("✓ Token consumed after POST")
        
        # Verify password changed
        user.refresh()
        assert user.check_password('NewSecurePassword123'), "Password not updated"
        print("✓ Password updated")
        
        # Verify user is active
        assert user.is_active == True
        print("✓ User active")
        
        # Verify user can log in with new password
        login_resp = client.post('/auth/login', data={
            'email': user.email,
            'password': 'NewSecurePassword123',
        }, follow_redirects=False)
        assert login_resp.status_code == 302, "Login failed"
        print("✓ Login with new password works")
    
    print("\nAll integration tests passed.")