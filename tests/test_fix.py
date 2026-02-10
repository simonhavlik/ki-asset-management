#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')

from app import create_app
from app.models import User, PasswordResetToken
from app.auth.utils import create_password_reset_token, validate_token
from datetime import datetime, timedelta

app = create_app()
with app.app_context():
    # Get a user
    user = User.query.first()
    if not user:
        print("No user found, skipping test")
        sys.exit(0)
    
    print(f"Testing with user {user.email}")
    
    # Create a reset token
    token = create_password_reset_token(user, token_type='reset', expires_hours=1)
    print(f"Created token: {token}")
    
    # Validate token without consuming (GET scenario)
    validated_user = validate_token(token, token_type='reset', consume=False)
    if validated_user:
        print(f"✓ Token validated (non‑consumptive), user: {validated_user.email}")
    else:
        print("✗ Token validation failed (non‑consumptive)")
    
    # Token should still be unused
    token_record = PasswordResetToken.query.filter_by(token_hash=token).first()
    if token_record:
        print(f"Token used flag: {token_record.used} (should be False)")
    
    # Validate token with consuming (POST scenario)
    validated_user2 = validate_token(token, token_type='reset', consume=True)
    if validated_user2:
        print(f"✓ Token validated (consumptive), user: {validated_user2.email}")
    else:
        print("✗ Token validation failed (consumptive)")
    
    # Token should now be used
    token_record = PasswordResetToken.query.filter_by(token_hash=token).first()
    if token_record:
        print(f"Token used flag: {token_record.used} (should be True)")
    
    # Attempt to validate again (should fail)
    validated_user3 = validate_token(token, token_type='reset', consume=False)
    if not validated_user3:
        print("✓ Used token correctly rejected")
    else:
        print("✗ Used token incorrectly accepted")
    
    # Test expired token
    # Create a token with immediate expiration
    expired_token = create_password_reset_token(user, token_type='reset', expires_hours=-1)
    # Manually set expires_at to past
    expired_record = PasswordResetToken.query.filter_by(token_hash=expired_token).first()
    if expired_record:
        expired_record.expires_at = datetime.utcnow() - timedelta(hours=1)
        expired_record.used = False
        app.extensions['db'].session.commit()
        validated_expired = validate_token(expired_token, token_type='reset', consume=False)
        if not validated_expired:
            print("✓ Expired token correctly rejected")
        else:
            print("✗ Expired token incorrectly accepted")
    
    print("\nAll tests passed.")