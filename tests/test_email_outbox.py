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


def test_relay_script_is_importable_without_psycopg2_at_import_time():
    """The relay runs on the DB host; importing it must not require psycopg2."""
    import importlib.util
    import pathlib
    path = pathlib.Path(__file__).resolve().parents[1] / 'scripts' / 'send_outbox.py'
    spec = importlib.util.spec_from_file_location('send_outbox', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.MAX_ATTEMPTS == 5
    assert callable(module.smtp_send)
