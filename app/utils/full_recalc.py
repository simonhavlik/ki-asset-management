"""Full data recalculation, run in a background thread with live progress.

Shared by the admin Update panel and the analyst pages' "Refresh data" button,
so both drive the same progress object (UnifiedDataCalculator.CalculationProgress)
and both refresh the public caches *and* the per-analyst dashboard caches.

The work is heavy (prices + performance + every view + dashboard warm), which is
why it never runs inside a request: callers start it and poll the progress.
"""

import logging
import threading
from datetime import date, timedelta

logger = logging.getLogger(__name__)

# Benchmark tickers kept fresh. MCHI (MSCI China) and ASHR (CSI 300) back the
# coverage-based "closest index" used on the analyst pages.
BENCHMARK_TICKERS = ['SPY', 'VT', 'EEMS', 'MCHI', 'ASHR']


def start_full_recalculation(run_type: str = 'manual'):
    """Start a full recalculation unless one is already running.

    Returns (started: bool, message: str).
    """
    from .unified_calculator import is_calculation_running

    if is_calculation_running():
        return False, 'A recalculation is already in progress'

    threading.Thread(target=_run_full_recalculation, args=(run_type,), daemon=True,
                     name='full-recalculation').start()
    return True, 'Recalculation started'


def _run_full_recalculation(run_type: str):
    from .. import create_app
    app = create_app()
    with app.app_context():
        from ..extensions import db
        from ..models import RecalculationLog
        from .neon_cache import (invalidate_all_public_cache, invalidate_board_cache,
                                 warm_public_caches)
        from .overview_cache import invalidate_cache as invalidate_overview, save_overview_cache
        from .yahooquery_helper import fetch_benchmark_prices
        from .unified_calculator import recalculate_all_unified

        log_entry = RecalculationLog(run_type=run_type)
        db.session.add(log_entry)
        db.session.commit()

        stats = {'analyses_processed': 0, 'prices_updated': 0,
                 'calculations_updated': 0, 'errors_count': 0}
        try:
            end_date = date.today()
            start_date = end_date - timedelta(days=1825)
            for ticker in BENCHMARK_TICKERS:
                try:
                    df = fetch_benchmark_prices(ticker, start_date, end_date)
                    if df is not None and not df.empty:
                        stats['prices_updated'] += len(df)
                except Exception as e:
                    stats['errors_count'] += 1
                    logger.warning(f'Benchmark {ticker} refresh failed: {e}')

            # Drop the caches FIRST. invalidate_cache() deletes the overview
            # rows outright, so invalidating *after* saving would wipe the data
            # that was just computed (that is what left the overview empty and
            # stuck on "refreshing").
            try:
                invalidate_all_public_cache()
                invalidate_board_cache()
                invalidate_overview()
            except Exception as e:
                stats['errors_count'] += 1
                logger.error(f'Cache invalidation failed: {e}')

            try:
                all_views = recalculate_all_unified(force=True) or {}
                for cache_key, view_data in all_views.items():
                    save_overview_cache(cache_key, view_data)
                stats['calculations_updated'] = len(all_views)
            except Exception as e:
                stats['errors_count'] += 1
                logger.error(f'Unified recalculation failed: {e}')

            # Warm the public caches, then the per-analyst dashboards.
            try:
                warm_public_caches()
            except Exception as e:
                stats['errors_count'] += 1
                logger.error(f'Cache warming failed: {e}')

            _warm_dashboards(stats)

            log_entry.mark_completed(stats)
            logger.info(f'Full recalculation finished: {stats}')
        except Exception as e:
            logger.error(f'Full recalculation failed: {e}')
            try:
                log_entry.mark_failed(str(e))
                db.session.commit()
            except Exception:
                pass


def _warm_dashboards(stats=None):
    """Precompute (and cache) every analyst's dashboard so it opens instantly.

    Runs after the data has been refreshed; per-user payloads are cached by
    get_dashboard_data(), so this is what makes the first dashboard load after
    a refresh fast instead of paying ~15s of portfolio/pandas work.
    """
    from ..extensions import db
    from ..models import analysis_analysts
    from ..analyst.routes import get_dashboard_data

    try:
        user_ids = [row[0] for row in db.session.query(analysis_analysts.c.user_id)
                    .filter(analysis_analysts.c.role == 'analyst').distinct().all()]
    except Exception as e:
        logger.warning(f'Could not list analysts to warm: {e}')
        return

    for uid in user_ids:
        try:
            get_dashboard_data(uid, force=True)
        except Exception as e:
            if stats is not None:
                stats['errors_count'] += 1
            logger.warning(f'Dashboard warm failed for user {uid}: {e}')
    logger.info(f'Dashboard caches warmed for {len(user_ids)} analysts')
