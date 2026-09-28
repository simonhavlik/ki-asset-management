"""The refresh widget must report the real state, on any page, after any restart.

Requirements: an explicit start press; then, wherever the user navigates and
however long it takes, pressing it again must show the progress or the result -
including after a redeploy / idle spin-down killed the job.
"""

from datetime import datetime, timedelta

import pytest

from app import create_app
from app.extensions import db


@pytest.fixture()
def app():
    application = create_app()
    application.config['WTF_CSRF_ENABLED'] = False
    with application.app_context():
        db.create_all()
        yield application


@pytest.fixture()
def client(app):
    return app.test_client()


def _log(app, status, minutes_ago=0, **kw):
    from app.models import RecalculationLog
    with app.app_context():
        row = RecalculationLog(run_type='manual', status=status,
                               started_at=datetime.utcnow() - timedelta(minutes=minutes_ago), **kw)
        if status != 'running':
            row.completed_at = datetime.utcnow()
            row.duration_seconds = 61.0
        db.session.add(row)
        db.session.commit()
        return row.id


def _state(app):
    from app.analyst.routes import build_refresh_state
    with app.app_context():
        return build_refresh_state()


def test_idle_state_has_a_stable_shape(app):
    from app.models import RecalculationLog
    with app.app_context():
        RecalculationLog.query.delete()
        db.session.commit()
        state = _state(app)
    assert state['running'] is False
    assert state['status'] == 'idle'
    assert state['last'] is None
    for key in ('progress_pct', 'message', 'logs'):
        assert key in state


def test_finished_run_is_reported_with_its_summary(app):
    from app.models import RecalculationLog
    with app.app_context():
        RecalculationLog.query.delete()
        db.session.commit()
    _log(app, 'completed', minutes_ago=5, calculations_updated=10, errors_count=0)
    state = _state(app)
    assert state['running'] is False
    assert state['status'] == 'completed'
    assert state['last']['calculations_updated'] == 10
    assert state['last']['duration_seconds'] == 61.0
    assert state['last']['finished_at']


def test_run_still_in_progress_counts_as_running(app):
    from app.models import RecalculationLog
    with app.app_context():
        RecalculationLog.query.delete()
        db.session.commit()
    _log(app, 'running', minutes_ago=1)
    state = _state(app)
    assert state['running'] is True
    assert state['status'] == 'running'


def test_interrupted_run_is_not_reported_as_progress_forever(app):
    """A job killed by a redeploy leaves status='running'; say so, don't lie."""
    from app.models import RecalculationLog
    with app.app_context():
        RecalculationLog.query.delete()
        db.session.commit()
    row_id = _log(app, 'running', minutes_ago=120)

    state = _state(app)
    assert state['running'] is False, 'a dead job must not look like ongoing work'
    assert state['last']['status'] == 'failed'
    assert 'Interrupted' in (state['last']['error_message'] or '')

    with app.app_context():
        assert db.session.get(RecalculationLog, row_id).status == 'failed'


def test_widget_is_available_on_every_page_when_logged_in(app, client):
    """The control lives in the navbar, so it exists on every page - but only
    for signed-in users."""
    from app.models import User

    password = 'Widget-Test-2026!'
    with app.app_context():
        user = User.query.filter_by(email='widget@klubinvestoru.com').first()
        if not user:
            user = User(email='widget@klubinvestoru.com', full_name='Widget',
                        is_active=True, email_verified=True)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
        else:
            user.set_password(password)
            db.session.commit()

    anon = client.get('/')
    assert b'refreshModal' not in anon.data, 'anonymous visitors must not see the control'

    # log in through the real route (the app hardens sessions in init_security,
    # so hand-written session cookies are not honoured)
    r = client.post('/auth/login', data={'email': 'widget@klubinvestoru.com', 'password': password})
    assert r.status_code in (302, 303), 'login failed, cannot test the widget'

    for path in ('/', '/blog/', '/analyst/'):
        page = client.get(path)
        assert page.status_code == 200, f'{path} -> {page.status_code}'
        assert b'refreshDataBtn' in page.data, f'no refresh control on {path}'
        assert b'refreshModal' in page.data


def test_progress_endpoint_requires_login(client):
    r = client.get('/analyst/refresh-progress')
    assert r.status_code in (302, 401)
