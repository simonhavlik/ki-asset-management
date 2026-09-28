"""The dashboard payload must survive a restart, not just live in memory.

Regression: it was cached only in the process cache, so every deploy and every
Render idle spin-down threw it away and the next login paid the full ~19s
computation. The overview never had this problem because it is in the database.
"""

from datetime import date, datetime
from decimal import Decimal

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
    u = User.query.filter_by(email='dash-cache@klubinvestoru.com').first()
    if not u:
        u = User(email='dash-cache@klubinvestoru.com', full_name='Dash Cache', is_active=True)
        u.set_password('irrelevant-password')
        db.session.add(u)
        db.session.commit()
    return u


def test_payload_round_trips_through_the_database(app):
    from app.analyst.routes import _load_dashboard_from_db, _store_dashboard_in_db

    with app.app_context():
        user = _user(app)
        payload = {
            'total_analyses': 3,
            'performance': {'avg_return': 12.5},
            'stock_impacts': [{'date': date(2026, 1, 2), 'impact': 1.25}],
            'generated_at': datetime(2026, 1, 2, 3, 4, 5),
            'ratio': Decimal('1.25'),
        }
        _store_dashboard_in_db(user.id, 'gen-1', payload)
        loaded = _load_dashboard_from_db(user.id, 'gen-1')

        assert loaded['total_analyses'] == 3
        assert loaded['performance']['avg_return'] == 12.5
        # types survive: templates call strftime on some of these
        assert loaded['stock_impacts'][0]['date'] == date(2026, 1, 2)
        assert loaded['generated_at'] == datetime(2026, 1, 2, 3, 4, 5)
        assert loaded['ratio'] == 1.25


def test_an_older_generation_is_still_served(app):
    """A refresh that died mid-warm must not cost anyone 19 seconds.

    Rows are only ever recomputed when one is missing: a stale payload is served
    instantly and replaced by the next warming pass.
    """
    from app.analyst.routes import _load_dashboard_from_db, _store_dashboard_in_db
    with app.app_context():
        user = _user(app)
        _store_dashboard_in_db(user.id, 'gen-old', {'total_analyses': 1})
        assert _load_dashboard_from_db(user.id, 'gen-old') is not None
        assert _load_dashboard_from_db(user.id, 'gen-new') is not None, \
            'an older generation must still be served rather than recomputed'


def test_second_read_does_not_recompute(app, monkeypatch):
    """A restart must not force a recomputation: L2 in the DB answers."""
    from app.analyst import routes as ar

    with app.app_context():
        from app.models import AnalystDashboardCache
        user = _user(app)
        AnalystDashboardCache.query.filter_by(user_id=user.id).delete()
        db.session.commit()
        calls = {'n': 0}

        def fake_compute(user_id):
            calls['n'] += 1
            return {'total_analyses': 42, 'performance': {}, 'stock_impacts': []}

        monkeypatch.setattr(ar, '_compute_dashboard_data', fake_compute)
        monkeypatch.setattr('app.utils.neon_cache.get_cache', lambda: None)
        monkeypatch.setattr('app.utils.neon_cache.get_cache_key', lambda *a, **k: 'key')
        monkeypatch.setattr('app.utils.neon_cache._cache_generation', lambda *a, **k: 'gen-test')

        first = ar.get_dashboard_data(user.id)
        second = ar.get_dashboard_data(user.id)

        assert first == second
        assert calls['n'] == 1, 'the payload was recomputed instead of read back'
