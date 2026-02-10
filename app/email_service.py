"""
Email service that supports both SendGrid API (for Render) and SMTP (for local dev).

SendGrid is preferred on Render because:
- Render free tier blocks outbound SMTP (ports 587, 465, 25)
- SendGrid uses HTTPS API which is not blocked
- SendGrid has a generous free tier (100 emails/day)

To use SendGrid:
1. Sign up at https://sendgrid.com (free tier: 100 emails/day)
2. Create an API key
3. Set SENDGRID_API_KEY in environment variables
4. Set MAIL_DEFAULT_SENDER to your verified sender email
"""

import logging
from flask import current_app

def send_email(to, subject, body, html=None):
    """
    Send an email using SendGrid API (preferred) or SMTP fallback.
    
    Args:
        to: Recipient email address
        subject: Email subject
        body: Plain text body
        html: HTML body (optional)
    
    Returns:
        bool: True if email was sent successfully, False otherwise
    """
    # Try SendGrid first (works on Render)
    sendgrid_api_key = current_app.config.get('SENDGRID_API_KEY')
    if sendgrid_api_key:
        try:
            return _send_sendgrid(to, subject, body, html)
        except Exception as e:
            current_app.logger.error(f'SendGrid failed: {e}')
            # Fall through to SMTP as backup
    
    # Fallback to SMTP (for local development)
    try:
        return _send_smtp(to, subject, body, html)
    except Exception as e:
        current_app.logger.error(f'SMTP failed: {e}')
        return False


def _send_sendgrid(to, subject, body, html=None):
    """Send email using SendGrid API."""
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail
    
    sendgrid_api_key = current_app.config['SENDGRID_API_KEY']
    sender = current_app.config.get('MAIL_DEFAULT_SENDER') or current_app.config.get('MAIL_USERNAME')
    
    if not sender:
        raise ValueError("MAIL_DEFAULT_SENDER or MAIL_USERNAME must be set")
    
    message = Mail(
        from_email=sender,
        to_emails=to,
        subject=subject,
        plain_text_content=body,
        html_content=html
    )
    
    sg = SendGridAPIClient(sendgrid_api_key)
    response = sg.send(message)
    
    if response.status_code in (200, 201, 202):
        current_app.logger.info(f'Email sent to {to} via SendGrid')
        return True
    else:
        raise Exception(f'SendGrid returned status {response.status_code}')


def _send_smtp(to, subject, body, html=None):
    """Send email using SMTP (Flask-Mail)."""
    from flask_mail import Message
    from .extensions import mail
    
    msg = Message(
        subject=subject,
        recipients=[to],
        body=body,
        html=html
    )
    mail.send(msg)
    current_app.logger.info(f'Email sent to {to} via SMTP')
    return True


def send_password_setup_email(user, token):
    """Send email with activation code and clickable link."""
    from flask import url_for
    
    subject = 'Set up your password for Analyst Performance Tracker'
    setup_url = url_for('auth.set_password', token=token, _external=True)
    
    body = f'''Hello,

You have been invited to set up your account at Analyst Performance Tracker.

Please click the following link to create your password (valid for 24 hours):

{setup_url}

If you did not expect this invitation, please ignore this email.

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
    """Send password‑reset email."""
    from flask import url_for
    
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
