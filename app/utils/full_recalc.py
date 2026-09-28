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

# A 'running' log row older than this cannot be a live job (deploys and Render's
# idle spin-down kill the worker), so it must not block a new refresh forever.
REFRESH_INTERRUPTED_AFTER_MINUTES = 45

_job_lock = threading.Lock()
_job_thread = None


def start_full_recalculation(run_type: str = 'manual'):
    """Start a full recalculation unless one is already running.

    Returns (started: bool, message: str).

    Two guards, because the obvious one is not enough: the calculator's own lock
    is only taken once the job reaches the recalculation stage, so a second
    press during the benchmark phase (seconds long) used to start a *second*
    whole-system job. The in-process thread handle closes that window atomically,
    and a recent 'running' log row covers a second worker or a restart.
    """
    from datetime import datetime, timedelta
    from .unified_calculator import is_calculation_running

    global _job_thread
    with _job_lock:
        if _job_thread is not None and _job_thread.is_alive():
            return False, 'A refresh is already running'
        if is_calculation_running():
            return False, 'A recalculation is already in progress'

        # Cross-worker guard: another process (or the same one before a restart)
        # may be mid-run. A 'running' row older than the interruption window is
        # a corpse, so it does not block anything.
        try:
            from ..models import RecalculationLog
            cutoff = datetime.utcnow() - timedelta(minutes=REFRESH_INTERRUPTED_AFTER_MINUTES)
            recent = (RecalculationLog.query
                      .filter(RecalculationLog.status == 'running',
                              RecalculationLog.started_at >= cutoff)
                      .order_by(RecalculationLog.id.desc())
                      .first())
            if recent is not None:
                return False, 'A refresh that started a few minutes ago is still running'
        except Exception as e:
            # A failure here must not block a legitimate refresh.
            logger.warning(f'Could not check for a running refresh: {e}')

        _job_thread = threading.Thread(target=_run_full_recalculation, args=(run_type,),
                                       daemon=True, name='full-recalculation')
        _job_thread.start()
    return True, 'Recalculation started'


def _run_full_recalculation(run_type: str):
    from .. import create_app
    app = create_app()
    with app.app_context():
        from ..extensions import db
        from ..models import RecalculationLog
        from .neon_cache import (invalidate_all_public_cache, invalidate_board_cache,
                                 warm_public_caches)
        from .overview_cache import save_overview_cache
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

            # Compute FIRST, destroy nothing until the new data is safely saved.
            #
            # The refresh used to invalidate the caches up front, then recompute.
            # The recompute takes minutes (76 companies and benchmarks over the
            # network) and runs in a thread inside a free 0.1-CPU instance that
            # sleeps when idle and restarts on every deploy - so it was routinely
            # killed before saving. The caches had already been emptied, leaving
            # the overview blank and stuck on "refreshing" with no way back. A
            # refresh that dies must now leave the previous data in place.
            try:
                all_views = recalculate_all_unified(force=True) or {}
                for cache_key, view_data in all_views.items():
                    save_overview_cache(cache_key, view_data)
                stats['calculations_updated'] = len(all_views)
            except Exception as e:
                stats['errors_count'] += 1
                logger.error(f'Unified recalculation failed: {e}')

            # Only now drop the derived caches. NOT the overview rows: those were
            # just refreshed above and invalidate_cache() deletes them.
            try:
                invalidate_all_public_cache()
                invalidate_board_cache()
            except Exception as e:
                stats['errors_count'] += 1
                logger.error(f'Cache invalidation failed: {e}')

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
