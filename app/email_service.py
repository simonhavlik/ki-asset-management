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
    # Provider order: MAIL_PROVIDER if forced, else Brevo / Resend / SendGrid
    # by whichever key is configured, with SMTP last (local dev - Render
    # blocks SMTP, so an HTTPS API is required in production).
    provider = (current_app.config.get('MAIL_PROVIDER') or '').lower()
    if provider:
        attempts = [provider]
    else:
        attempts = []
        if current_app.config.get('BREVO_API_KEY'):
            attempts.append('brevo')
        if current_app.config.get('RESEND_API_KEY'):
            attempts.append('resend')
        if current_app.config.get('SENDGRID_API_KEY'):
            attempts.append('sendgrid')
        attempts.append('smtp')

    for name in attempts:
        try:
            if name == 'brevo':
                return _send_brevo(to, subject, body, html)
            if name == 'resend':
                return _send_resend(to, subject, body, html)
            if name == 'sendgrid':
                return _send_sendgrid(to, subject, body, html)
            if name == 'smtp':
                return _send_smtp(to, subject, body, html)
        except Exception as e:
            current_app.logger.error(f'{name} failed: {e}')

    current_app.logger.error('No email provider succeeded')
    return False


def _sender():
    return (current_app.config.get('MAIL_DEFAULT_SENDER')
            or current_app.config.get('MAIL_USERNAME'))


def _send_brevo(to, subject, body, html=None):
    """Send via Brevo (Sendinblue) HTTPS API. Its free tier verifies a single
    sender *email* (no domain needed) - easiest drop-in for this app."""
    import requests
    key = current_app.config.get('BREVO_API_KEY')
    sender = _sender()
    if not (key and sender):
        raise ValueError('BREVO_API_KEY and MAIL_DEFAULT_SENDER must be set')
    payload = {
        'sender': {'email': sender},
        'to': [{'email': to}],
        'subject': subject,
        'textContent': body,
    }
    if html:
        payload['htmlContent'] = html
    r = requests.post('https://api.brevo.com/v3/smtp/email',
                      headers={'api-key': key, 'Content-Type': 'application/json',
                               'accept': 'application/json'},
                      json=payload, timeout=15)
    if r.status_code in (200, 201, 202):
        current_app.logger.info(f'Email sent to {to} via Brevo')
        return True
    raise Exception(f'Brevo {r.status_code}: {r.text[:200]}')


def _send_resend(to, subject, body, html=None):
    """Send via Resend HTTPS API (requires a verified sending domain)."""
    import requests
    key = current_app.config.get('RESEND_API_KEY')
    sender = _sender()
    if not (key and sender):
        raise ValueError('RESEND_API_KEY and MAIL_DEFAULT_SENDER must be set')
    r = requests.post('https://api.resend.com/emails',
                      headers={'Authorization': f'Bearer {key}',
                               'Content-Type': 'application/json'},
                      json={'from': sender, 'to': [to], 'subject': subject,
                            'text': body, 'html': html or body},
                      timeout=15)
    if r.status_code in (200, 201, 202):
        current_app.logger.info(f'Email sent to {to} via Resend')
        return True
    raise Exception(f'Resend {r.status_code}: {r.text[:200]}')


def _send_sendgrid(to, subject, body, html=None):
    """Send email using SendGrid API."""
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail
    
    sendgrid_api_key = current_app.config['SENDGRID_API_KEY']
    sender = _sender()
    
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


_MAIL_FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
_MAIL_MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace"


def _terminal_email(kicker, title, intro, url, cta, note):
    """Compact terminal-styled transactional email (dark ink + green accent).

    Table layout and inline styles only, so it renders in Gmail / Apple Mail /
    Outlook. Callers always pass a plain-text body too, so nothing depends on
    the HTML surviving.
    """
    return f'''<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f5f7f9;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f5f7f9;padding:28px 12px;">
    <tr><td align="center">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;background:#0f1419;border:1px solid #1a2028;border-radius:16px;overflow:hidden;">
        <tr><td style="padding:12px 16px;background:#141a21;border-bottom:1px solid #1a2028;">
          <span style="display:inline-block;width:9px;height:9px;border-radius:50%;background:#ff5f57;"></span>
          <span style="display:inline-block;width:9px;height:9px;border-radius:50%;background:#febc2e;margin-left:5px;"></span>
          <span style="display:inline-block;width:9px;height:9px;border-radius:50%;background:#28c840;margin-left:5px;"></span>
          <span style="font-family:{_MAIL_MONO};font-size:11px;letter-spacing:.14em;color:#c5cdd4;font-weight:700;margin-left:12px;vertical-align:middle;">KI ASSET MANAGEMENT</span>
        </td></tr>
        <tr><td style="height:3px;background:#2cce7e;"></td></tr>
        <tr><td style="padding:28px 26px 8px 26px;">
          <div style="font-family:{_MAIL_MONO};font-size:11px;letter-spacing:.16em;color:#6b7682;font-weight:700;text-transform:uppercase;">{kicker}</div>
          <h1 style="margin:10px 0 12px 0;font-family:{_MAIL_FONT};font-size:21px;line-height:1.3;color:#e6ebef;font-weight:700;">{title}</h1>
          <p style="margin:0 0 22px 0;font-family:{_MAIL_FONT};font-size:15px;line-height:1.65;color:#9aa5b1;">{intro}</p>
          <table role="presentation" cellspacing="0" cellpadding="0"><tr><td style="border-radius:10px;background:#2cce7e;">
            <a href="{url}" style="display:inline-block;padding:13px 26px;font-family:{_MAIL_MONO};font-size:13px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:#0f1419;text-decoration:none;">{cta}</a>
          </td></tr></table>
          <p style="margin:22px 0 6px 0;font-family:{_MAIL_MONO};font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:#6b7682;">or paste this link</p>
          <div style="font-family:{_MAIL_MONO};font-size:12px;line-height:1.5;color:#9aa5b1;background:#141a21;border:1px solid #1a2028;border-radius:8px;padding:10px 12px;word-break:break-all;">{url}</div>
          <p style="margin:18px 0 0 0;font-family:{_MAIL_MONO};font-size:11px;line-height:1.6;color:#6b7682;">{note}</p>
        </td></tr>
        <tr><td style="padding:18px 26px 24px 26px;border-top:1px solid #1a2028;">
          <p style="margin:0;font-family:{_MAIL_FONT};font-size:12px;color:#6b7682;">Analyst Performance Tracker &middot; Klub Investorů</p>
        </td></tr>
      </table>
      <div style="max-width:560px;margin:14px auto 0;font-family:{_MAIL_FONT};font-size:11px;color:#9aa5b1;text-align:center;">This is an automated message.</div>
    </td></tr>
  </table>
</body>
</html>'''


def send_password_setup_email(user, token):
    """Send the account-setup (activation) email."""
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

    html = _terminal_email(
        kicker='Account setup',
        title='Create your password',
        intro='You have been invited to set up your account at Analyst Performance '
              'Tracker. Choose a password to get started.',
        url=setup_url,
        cta='Set password',
        note='This link expires in 24 hours. If you did not expect this invitation, '
             'you can safely ignore this email.',
    )
    return send_email(user.email, subject, body, html)


def send_password_reset_email(user, token):
    """Send the password-reset email."""
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

    html = _terminal_email(
        kicker='Password reset',
        title='Reset your password',
        intro='You requested a password reset for Analyst Performance Tracker. '
              'Choose a new password below.',
        url=reset_url,
        cta='Reset password',
        note='This link expires in 24 hours. If you did not request this, you can '
             'safely ignore this email.',
    )
    return send_email(user.email, subject, body, html)
