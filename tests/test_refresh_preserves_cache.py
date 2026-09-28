"""A refresh that dies must never leave the overview with no data.

Regression (twice over): the refresh invalidated the caches before recomputing,
and the scheduler job recomputed and then discarded the result before deleting
the cache. The recompute takes minutes and runs in a thread on a free instance
that sleeps when idle and restarts on every deploy, so both were routinely
killed mid-flight - leaving the overview blank and stuck on "refreshing" with
nothing to fall back on.
"""

import pytest

from app import create_app
from app.extensions import db
from app.utils import overview_cache as oc


@pytest.fixture()
def app():
    application = create_app()
    with application.app_context():
        db.create_all()
        yield application


def _seed(filter_type='all_incremental', marker='previous'):
    oc.save_overview_cache(filter_type, {
        'portfolio_performance': {'num_positions': 7, 'total_return': 1.23},
        'series_all': [{'date': '2026-01-01', 'value': 1}],
        'sector_stats': [{'sector': marker}],
        'analyst_rankings': [],
    })


def _cache_is_intact(filter_type='all_incremental'):
    data, _ = oc.get_overview_cache_any(filter_type)
    return bool(data) and (data.get('sector_stats') or [{}])[0].get('sector') == 'previous'


def test_failed_recalculation_keeps_the_previous_data(app, monkeypatch):
    from app.utils import full_recalc

    with app.app_context():
        oc.invalidate_cache()
        _seed()

        def boom(*args, **kwargs):
            raise RuntimeError('killed mid-run (deploy / instance sleep)')

        monkeypatch.setattr('app.utils.unified_calculator.recalculate_all_unified', boom)
        monkeypatch.setattr('app.utils.yahooquery_helper.fetch_benchmark_prices',
                            lambda *a, **k: None)
        monkeypatch.setattr('app.utils.neon_cache.warm_public_caches', lambda *a, **k: [])
        monkeypatch.setattr(full_recalc, '_warm_dashboards', lambda *a, **k: None)

        full_recalc._run_full_recalculation('manual')

        assert _cache_is_intact(), 'a failed refresh destroyed the cached overview data'


def test_successful_recalculation_replaces_the_data(app, monkeypatch):
    from app.utils import full_recalc

    with app.app_context():
        oc.invalidate_cache()
        _seed()

        monkeypatch.setattr(
            'app.utils.unified_calculator.recalculate_all_unified',
            lambda force=False: {'all_incremental': {
                'portfolio_performance': {'num_positions': 9, 'total_return': 2.0},
                'series_all': [{'date': '2026-02-02', 'value': 2}],
                'sector_stats': [{'sector': 'fresh'}],
                'analyst_rankings': [],
            }},
        )
        monkeypatch.setattr('app.utils.yahooquery_helper.fetch_benchmark_prices',
                            lambda *a, **k: None)
        monkeypatch.setattr('app.utils.neon_cache.warm_public_caches', lambda *a, **k: [])
        monkeypatch.setattr(full_recalc, '_warm_dashboards', lambda *a, **k: None)

        full_recalc._run_full_recalculation('manual')

        data, _ = oc.get_overview_cache_any('all_incremental')
        assert (data.get('sector_stats') or [{}])[0].get('sector') == 'fresh'


def test_manual_cache_clear_does_not_touch_overview_data(app):
    """The admin "Refresh All Caches" button must not blank the overview."""
    with app.app_context():
        oc.invalidate_cache()
        _seed()
        # what admin.refresh_all_caches now does
        from app.utils.neon_cache import invalidate_all_public_cache
        invalidate_all_public_cache()
        assert _cache_is_intact()
