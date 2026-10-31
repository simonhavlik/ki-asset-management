"""Page loads read shared results, never compute them or start refresh jobs."""
from datetime import date, datetime

import pytest
from app import create_app
from app.extensions import db
from app.utils.calculation_snapshots import snapshot


@pytest.fixture()
def application():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        from app.models import CalculationSnapshot, AnalystDashboardCache
        CalculationSnapshot.query.delete()
        AnalystDashboardCache.query.delete()
        db.session.commit()
        yield app


def test_snapshot_misses_and_restarts_never_compute(application):
    calls = []

    @snapshot(default=lambda: {'pending': True})
    def fetch(series='all', force_refresh=False):
        calls.append(series)
        return {'as_of': date(2026, 10, 26), 'return': 3.5}

    assert fetch() == {'pending': True}
    assert calls == []
    expected = fetch(force_refresh=True)
    db.session.remove()  # another worker has no local cache
    assert fetch() == expected
    assert fetch(series='other') == {'pending': True}
    assert calls == ['all']


def test_failed_refresh_keeps_last_success_and_old_results_are_served(application):
    from app.models import CalculationSnapshot
    fail = False

    @snapshot()
    def fetch(force_refresh=False):
        if fail:
            raise RuntimeError('source unavailable')
        return {'series': [0, 2, 3]}

    expected = fetch(force_refresh=True)
    row = CalculationSnapshot.query.first()
    row.cached_at = datetime(2000, 1, 1)
    db.session.commit()
    fail = True
    with pytest.raises(RuntimeError):
        fetch(force_refresh=True)
    assert fetch() == expected


def test_cold_pages_do_not_call_calculators(application, monkeypatch):
    from app.analyst import routes as ar
    from app.admin import routes as admin
    from app.main import routes as main
    from app.utils import neon_cache as nc, overview_cache as oc
    from app.models import User

    def forbidden(*args, **kwargs):
        raise AssertionError('A page load started a calculation')

    monkeypatch.setattr(main, 'get_dashboard_stats', forbidden)
    monkeypatch.setattr(main, 'get_portfolio_chart_data', forbidden)
    monkeypatch.setattr(admin, 'get_portfolio_performance', forbidden)
    monkeypatch.setattr(admin, 'get_portfolio_series', forbidden)
    monkeypatch.setattr(ar, '_compute_dashboard_data', forbidden)
    monkeypatch.setattr(oc, 'refresh_overview_async', forbidden)
    monkeypatch.setattr(oc, 'get_overview_cache_any', lambda *a: (None, None))
    monkeypatch.setattr(ar, '_try_broader_view_cache', lambda *a: None)
    user = User(email='snapshot-admin@klubinvestoru.com', is_admin=True, is_active=True)
    db.session.add(user)
    db.session.commit()
    client = application.test_client()
    assert client.get('/').status_code == 200
    assert nc.get_cached_board_portfolio_series() is None
    with client.session_transaction() as session:
        session['_user_id'] = str(user.id)
        session['_fresh'] = True
    from flask import g
    g.pop('_login_user', None)
    for path in ['/analyst/', '/admin/board', '/analyst/overview?refresh=true']:
        assert client.get(path).status_code == 200, path


def test_scheduled_job_uses_complete_central_publisher(application, monkeypatch):
    from app import scheduler
    from app.utils import full_recalc
    calls = []
    monkeypatch.setattr(scheduler, '_refresh_presentation_exports', lambda: None)
    monkeypatch.setattr(full_recalc, '_run_full_recalculation',
                        lambda kind: calls.append(kind) or {'ok': True})
    assert scheduler.refresh_all_cached_data('scheduled') == {'ok': True}
    assert calls == ['scheduled']


def test_publisher_warms_every_board_variant(application, monkeypatch):
    from app.utils import neon_cache as nc
    for name in ['main_stats', 'purchased_main_stats', 'portfolio_chart', 'growth_timeline', 'top_sectors',
                 'latest_blog_posts', 'featured_research', 'rss_posts', 'sitemap_posts']:
        monkeypatch.setattr(nc, 'get_cached_' + name, lambda **kw: None)
    purchased_public = []
    monkeypatch.setattr(nc, 'get_cached_purchased_main_stats', lambda **kw: purchased_public.append(kw))
    performance, series = [], []
    monkeypatch.setattr(nc, 'get_cached_board_portfolio_performance',
                        lambda **kw: performance.append(kw))
    monkeypatch.setattr(nc, 'get_cached_board_portfolio_series',
                        lambda **kw: series.append(kw))
    nc.warm_public_caches(strict=True)
    assert purchased_public == [{'force_refresh': True}]
    assert performance == [{'purchased_only': p, 'force_refresh': True} for p in (False, True)]
    assert series == [{'purchased_only': p, 'years': y, 'force_refresh': True}
                      for p in (False, True) for y in (None, 1)]


def test_overnight_catchup_respects_weekly_slot(application, monkeypatch):
    from app import scheduler
    from app.models import RecalculationLog

    class Clock(datetime):
        hour = 3

        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 26, cls.hour, 15, tzinfo=tz)

    monkeypatch.setattr(scheduler, 'datetime', Clock)
    monkeypatch.setattr(scheduler, 'get_scheduler_settings',
        lambda: {'enabled': True, 'day_of_week': 'mon', 'hour': 4, 'minute': 0})
    calls = []
    monkeypatch.setattr(scheduler, 'weekly_data_refresh', lambda: calls.append('run'))
    RecalculationLog.query.delete()
    row = RecalculationLog(run_type='scheduled', status='completed',
                           started_at=datetime(2026, 10, 19, 2))
    db.session.add(row)
    db.session.commit()
    scheduler.scheduled_recalc_if_due()
    assert calls == []  # before this week's scheduled slot
    Clock.hour = 5
    scheduler.scheduled_recalc_if_due()
    assert calls == ['run']
    row.started_at = datetime(2026, 10, 26, 3, 0)  # 04:00 Prague after DST change
    db.session.commit()
    scheduler.scheduled_recalc_if_due()
    assert calls == ['run']
