"""Token validation must be one indexed lookup, not a hash scan.

Regression: validate_token() loaded every unused token and ran a pbkdf2-SHA256
check (600k iterations) against each, twice per page load. With 20 outstanding
tokens that was ~40 slow hashes: GET /auth/reset-password/<token> measured
24-29s on Render's free instance and got slower with every reset request.
"""

import time

import pytest

from app import create_app
from app.extensions import db


@pytest.fixture()
def app():
    application = create_app()
    with application.app_context():
        db.create_all()
        yield application


def _user(app):
    from app.models import User
    user = User.query.filter_by(email='token-test@klubinvestoru.com').first()
    if not user:
        user = User(email='token-test@klubinvestoru.com', full_name='Token Test',
                    is_active=True)
        user.set_password('irrelevant')
        db.session.add(user)
        db.session.commit()
    return user


def test_token_round_trip(app):
    from app.auth.utils import create_password_reset_token, validate_token
    with app.app_context():
        user = _user(app)
        token = create_password_reset_token(user, token_type='reset')
        assert validate_token(token, token_type='reset', consume=False).id == user.id
        # consuming marks it used, and it cannot be reused
        assert validate_token(token, token_type='reset', consume=True).id == user.id
        assert validate_token(token, token_type='reset', consume=False) is None


def test_stored_hash_is_not_a_password_hash(app):
    from app.auth.utils import create_password_reset_token
    from app.models import PasswordResetToken
    with app.app_context():
        user = _user(app)
        token = create_password_reset_token(user, token_type='reset')
        row = PasswordResetToken.query.order_by(PasswordResetToken.id.desc()).first()
        assert '$' not in row.token_hash, 'must be a plain sha256 digest for lookup'
        assert len(row.token_hash) == 64
        assert token not in row.token_hash, 'the raw token must never be stored'


def test_wrong_token_is_rejected(app):
    from app.auth.utils import validate_token
    with app.app_context():
        assert validate_token('not-a-real-token', token_type='reset') is None


def test_validation_cost_does_not_grow_with_many_outstanding_tokens(app):
    """The whole point: cost is constant, not O(outstanding tokens)."""
    from app.auth.utils import create_password_reset_token, validate_token
    from app.models import PasswordResetToken, User

    with app.app_context():
        user = _user(app)
        PasswordResetToken.query.delete()
        db.session.commit()

        for _ in range(30):                     # 30 live tokens, like production
            create_password_reset_token(user, token_type='reset')

        newest = PasswordResetToken.query.order_by(PasswordResetToken.id.desc()).first()
        probe = create_password_reset_token(user, token_type='reset')

        start = time.time()
        for _ in range(20):
            assert validate_token(probe, token_type='reset', consume=False) is not None
        elapsed = (time.time() - start) / 20

        # With the old scan this was ~30 password hashes per call (~2s each here).
        assert elapsed < 0.05, f'{elapsed*1000:.1f}ms per validation is too slow'


def test_expired_token_is_rejected(app):
    from datetime import datetime, timedelta
    from app.auth.utils import create_password_reset_token, validate_token
    from app.models import PasswordResetToken
    with app.app_context():
        user = _user(app)
        token = create_password_reset_token(user, token_type='reset')
        row = PasswordResetToken.query.order_by(PasswordResetToken.id.desc()).first()
        row.expires_at = datetime.utcnow() - timedelta(minutes=1)
        db.session.commit()
        assert validate_token(token, token_type='reset', consume=False) is None


def test_relay_mode_retry_leaves_queued_mail_alone(app, monkeypatch):
    """In relay mode the app must not 'retry' rows and mark them failed."""
    import app.email_service as es
    from app.models import EmailOutbox

    app.config['MAIL_PROVIDER'] = 'outbox'
    with app.app_context():
        EmailOutbox.query.delete()
        db.session.commit()
        db.session.add(EmailOutbox(recipient='a@example.com', subject='s',
                                   text_body='b', status='pending'))
        db.session.commit()

        assert es.drain_outbox() == (0, 0)
        row = EmailOutbox.query.first()
        assert row.status == 'pending'
        assert row.attempts == 0, 'the relay would have lost this message'
