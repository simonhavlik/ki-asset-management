"""A send that no provider can deliver must be queued, never silently lost.

Regression: SendGrid ran out of credits (401) and Render blocks SMTP outright
([Errno 101]), so every password reset was logged and dropped - users never
received a link and nothing surfaced the failure.
"""

import pytest

from app import create_app
from app.extensions import db


@pytest.fixture()
def app():
    application = create_app()
    with application.app_context():
        db.create_all()
        yield application


def _fail_all_providers(monkeypatch):
    import app.email_service as es
    def boom(*args, **kwargs):
        raise RuntimeError('Network is unreachable')
    for name in ('_send_smtp', '_send_sendgrid', '_send_brevo', '_send_resend'):
        monkeypatch.setattr(es, name, boom)


def test_failed_send_is_queued_instead_of_lost(app, monkeypatch):
    import app.email_service as es
    from app.models import EmailOutbox

    _fail_all_providers(monkeypatch)
    app.config['MAIL_PROVIDER'] = 'smtp'

    with app.app_context():
        EmailOutbox.query.delete()
        db.session.commit()

        assert es.send_email('analyst@example.com', 'Reset your password',
                             'plain body', '<p>html body</p>') is False

        rows = EmailOutbox.query.all()
        assert len(rows) == 1, 'the message must be parked in the outbox'
        row = rows[0]
        assert row.recipient == 'analyst@example.com'
        assert row.subject == 'Reset your password'
        assert row.text_body == 'plain body'
        assert row.html_body == '<p>html body</p>'
        assert row.status == 'pending'
        assert row.attempts == 0
        assert 'Network is unreachable' in (row.last_error or '')
        assert es.outbox_pending_count() == 1


def test_successful_send_is_not_queued(app, monkeypatch):
    import app.email_service as es
    from app.models import EmailOutbox

    monkeypatch.setattr(es, '_send_smtp', lambda *a, **k: True)
    app.config['MAIL_PROVIDER'] = 'smtp'

    with app.app_context():
        EmailOutbox.query.delete()
        db.session.commit()

        assert es.send_email('analyst@example.com', 'Hello', 'body') is True
        assert EmailOutbox.query.count() == 0


class _FakeResponse:
    def __init__(self, status=200, payload=None, text=''):
        self.status_code = status
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


def _fake_google(monkeypatch, fail_send=False, calls=None):
    """Stand in for the token endpoint and the Gmail send endpoint."""
    import app.email_service as es
    calls = calls if calls is not None else []
    es._gmail_token.update({'value': None, 'expires_at': 0.0})

    def fake_post(url, **kwargs):
        calls.append({'url': url, **kwargs})
        if url.endswith('/token'):
            return _FakeResponse(200, {'access_token': 'ya29.fake', 'expires_in': 3600})
        if 'messages/send' in url:
            if fail_send:
                return _FakeResponse(403, text='{"error": {"message": "insufficient permission"}}')
            return _FakeResponse(200, {'id': 'msg-1'})
        raise AssertionError(f'unexpected URL {url}')

    monkeypatch.setattr(es.requests, 'post', fake_post)
    return calls


def _configure_gmail(app):
    app.config.update(
        MAIL_PROVIDER='gmail_api',
        GMAIL_CLIENT_ID='client-id.apps.googleusercontent.com',
        GMAIL_CLIENT_SECRET='client-secret',
        GMAIL_REFRESH_TOKEN='1//refresh-token',
        GMAIL_SENDER='simon.havlik@klubinvestoru.com',
    )


def test_gmail_api_sends_over_https(app, monkeypatch):
    import base64
    import email
    import app.email_service as es

    calls = _fake_google(monkeypatch)
    _configure_gmail(app)

    with app.app_context():
        assert es.send_email('analyst@example.com', 'Reset your password',
                             'plain', '<p>html</p>') is True

    urls = [c['url'] for c in calls]
    assert urls[0] == 'https://oauth2.googleapis.com/token'
    assert urls[1] == 'https://gmail.googleapis.com/gmail/v1/users/me/messages/send'

    send_call = calls[1]
    assert send_call['headers']['Authorization'] == 'Bearer ya29.fake'
    parsed = email.message_from_bytes(base64.urlsafe_b64decode(send_call['json']['raw']))
    assert parsed['To'] == 'analyst@example.com'
    assert parsed['From'] == 'simon.havlik@klubinvestoru.com'
    assert parsed['Subject'] == 'Reset your password'


def test_gmail_access_token_is_cached(app, monkeypatch):
    import app.email_service as es

    calls = _fake_google(monkeypatch)
    _configure_gmail(app)

    with app.app_context():
        es.send_email('a@example.com', 'one', 'body')
        es.send_email('b@example.com', 'two', 'body')

    token_calls = [c for c in calls if c['url'].endswith('/token')]
    assert len(token_calls) == 1, 'the access token must be reused, not re-minted per email'


def test_failed_gmail_send_is_queued(app, monkeypatch):
    import app.email_service as es
    from app.models import EmailOutbox

    _fake_google(monkeypatch, fail_send=True)
    _configure_gmail(app)

    with app.app_context():
        EmailOutbox.query.delete()
        db.session.commit()
        assert es.send_email('analyst@example.com', 'Reset', 'body') is False
        assert EmailOutbox.query.count() == 1


def test_provider_chain_prefers_gmail_api(app):
    import app.email_service as es
    with app.app_context():
        app.config.update(GMAIL_REFRESH_TOKEN='1//x', SENDGRID_API_KEY='SG.x',
                          BREVO_API_KEY='', RESEND_API_KEY='', MAIL_PROVIDER='')
        assert es._provider_chain()[0] == 'gmail_api'


def test_drain_outbox_delivers_and_marks_sent(app, monkeypatch):
    import app.email_service as es
    from app.models import EmailOutbox

    monkeypatch.setattr(es, '_dispatch', lambda *a, **k: True)
    with app.app_context():
        EmailOutbox.query.delete()
        db.session.commit()
        db.session.add(EmailOutbox(recipient='a@example.com', subject='s',
                                   text_body='b', status='pending'))
        db.session.commit()

        assert es.drain_outbox() == (1, 0)
        row = EmailOutbox.query.first()
        assert row.status == 'sent'
        assert row.sent_at is not None
        assert row.attempts == 1


def test_drain_outbox_gives_up_after_max_attempts(app, monkeypatch):
    import app.email_service as es
    from app.models import EmailOutbox

    def boom(*args, **kwargs):
        raise RuntimeError('still broken')
    monkeypatch.setattr(es, '_dispatch', boom)

    with app.app_context():
        EmailOutbox.query.delete()
        db.session.commit()
        row = EmailOutbox(recipient='a@example.com', subject='s', text_body='b',
                          status='pending', attempts=EmailOutbox.MAX_ATTEMPTS - 1)
        db.session.add(row)
        db.session.commit()

        sent, failed = es.drain_outbox()
        assert (sent, failed) == (0, 1)
        row = EmailOutbox.query.first()
        assert row.status == 'failed', 'must stop retrying a permanently broken send'
        assert row.attempts == EmailOutbox.MAX_ATTEMPTS


def test_check_gmail_api_reports_bad_refresh_token(app, monkeypatch):
    """A revoked/expired refresh token must be diagnosable, not a mystery."""
    import app.email_service as es

    es._gmail_token.update({'value': None, 'expires_at': 0.0})
    monkeypatch.setattr(es.requests, 'post', lambda url, **kw: _FakeResponse(
        400, text='{"error": "invalid_grant", "error_description": "Token has been expired or revoked."}'))
    _configure_gmail(app)

    with app.app_context():
        ok, detail = es.check_gmail_api()
    assert ok is False
    assert 'invalid_grant' in detail
    assert '7 days' in detail, 'the message must explain the Testing-mode trap'


def test_check_gmail_api_reports_success(app, monkeypatch):
    import app.email_service as es

    _fake_google(monkeypatch)
    _configure_gmail(app)
    with app.app_context():
        ok, detail = es.check_gmail_api()
    assert ok is True
    assert 'access token obtained' in detail
