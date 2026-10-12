"""
Background scheduler for KI Asset Management.

Two autonomous jobs run here, both in Europe/Prague local time:

  * ``daily_notion_import``    - every day at 04:00, pulls the Notion analysis
    schedule into the database (analysis_schedule import).
  * ``automated_recalc``       - the full data refresh + recalculation, weekly on
    Monday at 04:00 (day/hour/minute are configurable from SystemSettings).

The recalculation's schedule is driven by SystemSettings so the admin UI can
change it; the daily Notion import is intentionally not gated on that toggle,
because keeping the site in step with Notion is the point of the job.

Render's free instance sleeps when idle. The club keeps it awake with UptimeRobot
pinging /health every few minutes, which is what lets these in-process jobs fire
at 04:00; without that keep-alive the instance would be asleep at 04:00.
"""

import functools
import logging
import threading
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()

# Wall-clock timezone for the cron jobs. The club is in Czechia and "04:00" is
# meant as local time; APScheduler would otherwise use the process timezone (UTC
# on Render) and run two hours off.
TIMEZONE = 'Europe/Prague'
DAILY_IMPORT_HOUR = 4
DAILY_IMPORT_MINUTE = 0

# The Flask app, captured in init_scheduler so jobs can push an app context.
_app = None

# Serialises the heavy jobs so the daily import and the weekly recalculation can
# never touch the database at the same time (they share the 04:00 slot on Monday).
_run_lock = threading.Lock()


def _with_app_context(job_func):
    """Wrap a job so it runs inside a Flask application context.

    APScheduler runs jobs in its own worker thread, which does not inherit the
    app context that was active when the job was registered. Without this the
    first database access inside a job raises "Working outside of application
    context" - which is what silently killed the previous automated
    recalculation whenever it was switched on.
    """
    @functools.wraps(job_func)
    def wrapper(*args, **kwargs):
        app = _app
        if app is None:
            from . import create_app
            app = create_app()
        with app.app_context():
            return job_func(*args, **kwargs)
    return wrapper


def get_scheduler_settings():
    """Get scheduler settings from database."""
    from .models import SystemSettings

    return {
        'enabled': SystemSettings.get('auto_recalc_enabled', False),
        'day_of_week': SystemSettings.get('auto_recalc_day', 'mon'),
        'hour': SystemSettings.get('auto_recalc_hour', 4),
        'minute': SystemSettings.get('auto_recalc_minute', 0)
    }


def import_notion_daily():
    """Pull the Notion analysis schedule into the database.

    Runs every day at 04:00. Never raises for a Notion/transport error: it logs
    the outcome so the autonomous run is visible in the app log.
    """
    from .utils.notion_import import run_notion_import

    logger.info("=" * 60)
    logger.info("Daily Notion import starting...")
    logger.info("=" * 60)

    with _run_lock:
        stats = run_notion_import()

    if stats.get('success'):
        logger.info(
            "Daily Notion import finished: %s created, %s updated, %s skipped "
            "(%s blank, %s unchanged)",
            stats.get('created', 0), stats.get('updated', 0), stats.get('skipped', 0),
            stats.get('blank', 0), stats.get('unchanged', 0),
        )
        errors = stats.get('errors') or []
        if errors:
            logger.warning("Daily Notion import had %s row error(s)", len(errors))
    else:
        logger.error("Daily Notion import failed: %s", stats.get('error'))
    logger.info("=" * 60)


def weekly_data_refresh():
    """Full data refresh + recalculation (the weekly job).

    Runs under the shared lock so it cannot overlap the daily Notion import on a
    Monday, and inside an app context (via _with_app_context at registration).
    """
    with _run_lock:
        return refresh_all_cached_data(run_type='scheduled')


def refresh_all_cached_data(run_type='scheduled'):
    """
    Refresh all cached data.
    Called automatically by scheduler or manually.
    
    Args:
        run_type: Type of run ('scheduled', 'manual', 'automated')
    """
    from .models import RecalculationLog
    from .utils.overview_cache import save_overview_cache
    from .utils.presentation_export import get_growth_timeline, get_sector_analysis
    from .utils.export_helper import generate_comprehensive_export
    from .utils.neon_cache import warm_public_caches, invalidate_all_public_cache
    from .utils.performance import PerformanceCalculator
    from .utils.unified_calculator import recalculate_all_unified
    from .extensions import db
    
    logger.info("=" * 60)
    logger.info(f"Starting {run_type} data refresh...")
    logger.info("=" * 60)
    
    start_time = datetime.now()
    
    # Create log entry
    log_entry = RecalculationLog(run_type=run_type)
    db.session.add(log_entry)
    db.session.commit()
    
    stats = {
        'analyses_processed': 0,
        'prices_updated': 0,
        'calculations_updated': 0,
        'errors_count': 0
    }
    
    try:
        # Step 1: Update benchmarks - incrementally. Only the missing tail per
        # index is downloaded and stored; never a full 5-year re-download.
        logger.info("Updating benchmark prices (incremental)...")
        from .utils.yahooquery_helper import update_benchmark_prices
        bm = update_benchmark_prices()
        stats['prices_updated'] += bm.get('new_records', 0)
        stats['errors_count'] += bm.get('errors', 0)
        logger.info(f"  benchmarks: {bm}")
        
        # Step 2: Recalculate all performance
        logger.info("Recalculating performance metrics...")
        calculator = PerformanceCalculator()
        perf_stats = calculator.recalculate_all()
        stats['analyses_processed'] = perf_stats.get('total_analyses', 0)
        stats['calculations_updated'] = perf_stats.get('calculated', 0)
        stats['errors_count'] += len(perf_stats.get('errors', []))
        
        if perf_stats.get('errors'):
            for err in perf_stats['errors'][:5]:
                logger.warning(f"  Performance error: {err}")
        
        # Step 3: Unified recalculation
        logger.info("Running unified recalculation...")
        try:
            all_views = recalculate_all_unified(force=True) or {}
            # SAVE the results. This job used to recompute everything and then
            # throw the data away, before deleting the overview cache outright -
            # so every scheduled run left the overview page blank until some
            # other code path happened to repopulate it. Saving is the caller's
            # job: recalculate_all_unified() only computes.
            for cache_key, view_data in all_views.items():
                save_overview_cache(cache_key, view_data)
            logger.info(f"Saved {len(all_views)} overview view(s) to cache")
        except Exception as e:
            stats['errors_count'] += 1
            logger.error(f"Unified recalculation error: {e}")
        
        # Step 4: Invalidate the derived caches only. NEVER the overview rows:
        # those hold the page's data and were just written above.
        logger.info("Invalidating caches...")
        invalidate_all_public_cache()
        
        # Step 5: Warm caches
        logger.info("Warming caches...")
        warmed = warm_public_caches()
        logger.info(f"Warmed caches: {', '.join(warmed)}")
        
        # Step 6: Refresh presentation exports
        logger.info("Refreshing growth timeline...")
        growth_data = get_growth_timeline(use_cache=False)
        
        logger.info("Refreshing sector analysis...")
        sector_data = get_sector_analysis(use_cache=False)
        
        logger.info("Refreshing comprehensive export...")
        # Best-effort, bounded: the comprehensive Excel is a downloadable artifact,
        # not needed by any page. On the 512 MB instance it can be slow, so run it
        # detached and never let it block the recalculation from completing.
        import threading as _threading

        def _build_export():
            try:
                generate_comprehensive_export(force_new=True)
            except Exception as exc:  # noqa: BLE001 - an artifact must not fail the job
                logger.warning("Comprehensive export failed: %s", exc)

        _export_thread = _threading.Thread(target=_build_export, daemon=True, name='recalc-export')
        _export_thread.start()
        _export_thread.join(timeout=180)
        if _export_thread.is_alive():
            logger.warning(
                "Comprehensive export exceeded 180s; recalculation completes without it "
                "(the export will finish in the background or be rebuilt on demand)"
            )
        
        elapsed = (datetime.now() - start_time).total_seconds()
        stats['duration_seconds'] = elapsed
        
        # Mark log as completed
        log_entry.mark_completed(stats)
        
        logger.info("=" * 60)
        logger.info(f"{run_type.title()} refresh completed in {elapsed:.1f}s")
        logger.info(f"  Analyses: {stats['analyses_processed']}")
        logger.info(f"  Prices: {stats['prices_updated']}")
        logger.info(f"  Calculations: {stats['calculations_updated']}")
        logger.info(f"  Errors: {stats['errors_count']}")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Error during {run_type} refresh: {e}")
        logger.exception(f"{run_type.title()} refresh failed")
        log_entry.mark_failed(str(e))


def retry_queued_emails():
    """Retry emails parked in the outbox by earlier failed sends.

    This is what makes a mail provider outage non-lossy: a password reset that
    nobody could deliver is retried here instead of vanishing. Provider
    selection is the same chain send_email() uses (see app/email_service.py).
    """
    try:
        from .email_service import drain_outbox
        sent, failed = drain_outbox(limit=20)
        if sent or failed:
            logger.info(f"Email outbox retry: {sent} sent, {failed} still failing")
    except Exception as e:
        logger.warning(f"Email outbox retry failed: {e}")


def init_scheduler(app):
    """Initialize and start the background scheduler."""
    global _app
    _app = app

    with app.app_context():
        # Always scheduled, and never gated on the recalculation setting: this
        # is the safety net for undeliverable mail.
        scheduler.add_job(
            func=_with_app_context(retry_queued_emails),
            trigger=IntervalTrigger(minutes=15),
            id='email_outbox_retry',
            name='Email outbox retry',
            replace_existing=True,
        )

        # Daily autonomous Notion import. Deliberately always on: keeping the
        # site in step with Notion is the point, and the job is a no-op when
        # nothing changed.
        scheduler.add_job(
            func=_with_app_context(import_notion_daily),
            trigger=CronTrigger(hour=DAILY_IMPORT_HOUR, minute=DAILY_IMPORT_MINUTE,
                                timezone=TIMEZONE),
            id='daily_notion_import',
            name='Daily Notion import',
            replace_existing=True,
        )
        logger.info(f"Daily Notion import scheduled for "
                    f"{DAILY_IMPORT_HOUR:02d}:{DAILY_IMPORT_MINUTE:02d} {TIMEZONE}")

        settings = get_scheduler_settings()

        if settings['enabled']:
            # Remove existing job if present
            if scheduler.get_job('automated_recalc'):
                scheduler.remove_job('automated_recalc')

            day_map = {
                'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3,
                'fri': 4, 'sat': 5, 'sun': 6
            }

            day_of_week = day_map.get(settings['day_of_week'], 0)  # Default to Monday

            scheduler.add_job(
                func=_with_app_context(weekly_data_refresh),
                trigger=CronTrigger(day_of_week=day_of_week, hour=settings['hour'],
                                    minute=settings['minute'], timezone=TIMEZONE),
                id='automated_recalc',
                name='Automated Data Refresh',
                replace_existing=True
            )

            logger.info(f"Automated recalculation scheduled for "
                       f"{settings['day_of_week']} at {settings['hour']:02d}:{settings['minute']:02d} {TIMEZONE}")
        else:
            logger.info("Automated recalculation is disabled in settings")

        if not scheduler.running:
            scheduler.start()
            logger.info("Background scheduler started")


def shutdown_scheduler():
    """Shutdown the scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Background scheduler shut down")


def update_scheduler_settings():
    """Update scheduler based on current settings (call after settings change)."""
    settings = get_scheduler_settings()
    
    if not settings['enabled']:
        # Remove scheduled job if exists
        if scheduler.get_job('automated_recalc'):
            scheduler.remove_job('automated_recalc')
            logger.info("Automated recalculation disabled")
        return
    
    # Update or add job
    day_map = {
        'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 
        'fri': 4, 'sat': 5, 'sun': 6
    }
    
    day_of_week = day_map.get(settings['day_of_week'], 0)
    
    # Remove existing job
    if scheduler.get_job('automated_recalc'):
        scheduler.remove_job('automated_recalc')
    
    # Add new job
    scheduler.add_job(
        func=_with_app_context(weekly_data_refresh),
        trigger=CronTrigger(day_of_week=day_of_week, hour=settings['hour'],
                            minute=settings['minute'], timezone=TIMEZONE),
        id='automated_recalc',
        name='Automated Data Refresh',
        replace_existing=True
    )
    
    logger.info(f"Scheduler updated: {settings['day_of_week']} at {settings['hour']:02d}:{settings['minute']:02d} {TIMEZONE}")


# Make db accessible
from .extensions import db
