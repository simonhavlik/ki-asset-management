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
    setup_url = url_for('auth.set_password', token=token, _external=True)
    body = f'''Hello,

You have been invited to set up your account at Analyst Performance Tracker.

Please click the following link to create your password (valid for 24 hours):

{setup_url}

If you didn't expect this invitation, please ignore this email.

Best regards,
The Analyst Performance Tracker Team
'''
    html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{subject}</title>
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f6f9f6; color: #333;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <tr>
            <td style="text-align: center; padding: 30px 0;">
                <div style="display: inline-block; background: linear-gradient(135deg, #10b981 0%, #059669 100%); padding: 20px 30px; border-radius: 16px; margin-bottom: 20px;">
                    <span style="font-size: 32px;">📊</span>
                </div>
                <h1 style="margin: 0; color: #065f46; font-size: 28px; font-weight: 700;">Analyst Performance Tracker</h1>
            </td>
        </tr>
        <tr>
            <td style="background: #ffffff; border-radius: 16px; padding: 40px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);">
                <h2 style="margin: 0 0 20px 0; color: #1f2937; font-size: 24px;">Welcome! 👋</h2>
                <p style="margin: 0 0 24px 0; color: #4b5563; font-size: 16px; line-height: 1.6;">
                    You have been invited to set up your account. Click the button below to create your password and get started.
                </p>
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                    <tr>
                        <td style="text-align: center; padding: 20px 0;">
                            <a href="{setup_url}" style="display: inline-block; background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: #ffffff; text-decoration: none; padding: 16px 40px; border-radius: 12px; font-size: 16px; font-weight: 600; box-shadow: 0 4px 14px rgba(16, 185, 129, 0.4);">
                                Set Password →
                            </a>
                        </td>
                    </tr>
                </table>
                <p style="margin: 24px 0 0 0; color: #9ca3af; font-size: 14px; text-align: center;">
                    This link will expire in 24 hours.
                </p>
            </td>
        </tr>
        <tr>
            <td style="text-align: center; padding: 30px 0; color: #9ca3af; font-size: 14px;">
                <p style="margin: 0;">Analyst Performance Tracker</p>
                <p style="margin: 8px 0 0 0; color: #d1d5db;">If you didn't expect this email, you can safely ignore it.</p>
            </td>
        </tr>
    </table>
</body>
</html>'''
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
    html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{subject}</title>
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f6f9f6; color: #333;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <tr>
            <td style="text-align: center; padding: 30px 0;">
                <div style="display: inline-block; background: linear-gradient(135deg, #10b981 0%, #059669 100%); padding: 20px 30px; border-radius: 16px; margin-bottom: 20px;">
                    <span style="font-size: 32px;">📊</span>
                </div>
                <h1 style="margin: 0; color: #065f46; font-size: 28px; font-weight: 700;">Analyst Performance Tracker</h1>
            </td>
        </tr>
        <tr>
            <td style="background: #ffffff; border-radius: 16px; padding: 40px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);">
                <h2 style="margin: 0 0 20px 0; color: #1f2937; font-size: 24px;">Reset Password 🔐</h2>
                <p style="margin: 0 0 24px 0; color: #4b5563; font-size: 16px; line-height: 1.6;">
                    You requested to reset your password. Click the button below to choose a new password.
                </p>
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                    <tr>
                        <td style="text-align: center; padding: 20px 0;">
                            <a href="{reset_url}" style="display: inline-block; background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: #ffffff; text-decoration: none; padding: 16px 40px; border-radius: 12px; font-size: 16px; font-weight: 600; box-shadow: 0 4px 14px rgba(16, 185, 129, 0.4);">
                                Reset Password →
                            </a>
                        </td>
                    </tr>
                </table>
                <p style="margin: 24px 0 0 0; color: #9ca3af; font-size: 14px; text-align: center;">
                    This link will expire in 24 hours.
                </p>
                <p style="margin: 16px 0 0 0; color: #9ca3af; font-size: 14px; text-align: center;">
                    If you didn't request this, you can safely ignore this email.
                </p>
            </td>
        </tr>
        <tr>
            <td style="text-align: center; padding: 30px 0; color: #9ca3af; font-size: 14px;">
                <p style="margin: 0;">Analyst Performance Tracker</p>
            </td>
        </tr>
    </table>
</body>
</html>'''
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