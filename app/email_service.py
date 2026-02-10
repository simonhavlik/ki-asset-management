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
    
    html = f'''<p>Hello,</p>
<p>You have requested to reset your password for Analyst Performance Tracker.</p>
<p>Please <a href="{reset_url}">click here</a> to choose a new password (valid for 24 hours).</p>
<p>If you did not request this, please ignore this email.</p>
<p>Best regards,<br>The Analyst Performance Tracker Team</p>'''
    
    return send_email(user.email, subject, body, html)
