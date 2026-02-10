import secrets
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer
from flask import current_app, url_for
from flask_mail import Message
from ..extensions import mail, db
from ..models import User, PasswordResetToken

def generate_token():
    """Generate a secure random token (URL‑safe)."""
    return secrets.token_urlsafe(32)

def create_password_reset_token(user, token_type='reset', expires_hours=24):
    """Create a token record in the database."""
    token = generate_token()
    expires_at = datetime.utcnow() + timedelta(hours=expires_hours)
    token_hash = generate_password_hash(token)
    token_record = PasswordResetToken(
        user_id=user.id,
        token_hash=token_hash,
        token_type=token_type,
        expires_at=expires_at
    )
    db.session.add(token_record)
    db.session.commit()
    return token

def validate_token(token, token_type='reset', consume=True):
    """Validate a token and return the user if valid.
    
    If consume is True (default), the token will be marked as used.
    """
    # Find all token records of the given type that are unused and not expired
    token_records = PasswordResetToken.query.filter(
        PasswordResetToken.token_type == token_type,
        PasswordResetToken.used == False,
        PasswordResetToken.expires_at > datetime.utcnow()
    ).all()
    for token_record in token_records:
        # Verify token hash
        if check_password_hash(token_record.token_hash, token):
            if consume:
                token_record.used = True
                db.session.commit()
            return token_record.user
    return None

def send_password_setup_email(user, token):
    """Send email with activation code and clickable link.
    
    Returns True if email was sent successfully, False otherwise.
    """
    subject = 'Set up your password for Analyst Performance Tracker'
    activation_url = url_for('auth.activate', token=token, _external=True)
    body = f'''Hello,

You have requested to set up a password for your account at Analyst Performance Tracker.

Your activation code is:

{token}

You can also click the following link to activate your account directly (valid for 24 hours):

{activation_url}

If you did not request this, please ignore this email.

Best regards,
The Analyst Performance Tracker Team
'''
    html = f'''<p>Hello,</p>
<p>You have requested to set up a password for your account at Analyst Performance Tracker.</p>
<p><strong>Your activation code:</strong></p>
<p style="font-size: 1.2rem; font-family: monospace; padding: 10px; background: #f8f9fa; border: 1px solid #ddd;">{token}</p>
<p>You can also <a href="{activation_url}">click here</a> to activate your account directly (valid for 24 hours).</p>
<p>If you did not request this, please ignore this email.</p>
<p>Best regards,<br>The Analyst Performance Tracker Team</p>'''
    return send_email(user.email, subject, body, html)

def send_password_reset_email(user, token):
    """Send password‑reset email.
    
    Returns True if email was sent successfully, False otherwise.
    """
    subject = 'Reset your password for Analyst Performance Tracker'
    reset_url = url_for('auth.reset_password', token=token, _external=True)
    body = f'''Hello,

You have requested to reset your password for Analyst Performance Tracker.

Please click the following link to choose a new password (valid for 24 hours):

{reset_url}

If you did not request this, please ignore this email.

Best regards,
The Analyst Performance Tracker Team
'''
    html = f'''<p>Hello,</p>
<p>You have requested to reset your password for Analyst Performance Tracker.</p>
<p>Please <a href="{reset_url}">click here</a> to choose a new password (valid for 24 hours).</p>
<p>If you did not request this, please ignore this email.</p>
<p>Best regards,<br>The Analyst Performance Tracker Team</p>'''
    return send_email(user.email, subject, body, html)

def send_email(to, subject, body, html=None):
    """Send an email via Flask‑Mail.
    
    On Render free tier, SMTP may be blocked. Errors are logged but not raised
    to prevent breaking user registration flow.
    """
    msg = Message(
        subject=subject,
        recipients=[to],
        body=body,
        html=html
    )
    try:
        mail.send(msg)
        current_app.logger.info(f'Email sent to {to}')
        return True
    except Exception as e:
        current_app.logger.error(f'Failed to send email to {to}: {e}')
        # Don't raise - allow registration to continue even if email fails
        # On Render free tier, SMTP is often blocked
        return False