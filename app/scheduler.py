"""
Background scheduler for KI Asset Management.

Runs automated data refresh based on configured schedule.
Supports flexible scheduling from SystemSettings.
"""

import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def get_scheduler_settings():
    """Get scheduler settings from database."""
    from .models import SystemSettings
    
    return {
        'enabled': SystemSettings.get('auto_recalc_enabled', False),
        'day_of_week': SystemSettings.get('auto_recalc_day', 'fri'),
        'hour': SystemSettings.get('auto_recalc_hour', 23),
        'minute': SystemSettings.get('auto_recalc_minute', 0)
    }


def refresh_all_cached_data(run_type='scheduled'):
    """
    Refresh all cached data.
    Called automatically by scheduler or manually.
    
    Args:
        run_type: Type of run ('scheduled', 'manual', 'automated')
    """
    from .models import RecalculationLog
    from .utils.overview_cache import invalidate_cache
    from .utils.presentation_export import get_growth_timeline, get_sector_analysis
    from .utils.export_helper import generate_comprehensive_export
    from .utils.neon_cache import warm_public_caches, invalidate_all_public_cache
    from .utils.performance import PerformanceCalculator
    from .utils.unified_calculator import recalculate_all_unified
    from .utils.yahooquery_helper import fetch_benchmark_prices
    from .extensions import db
    from datetime import date, timedelta
    
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
        # Step 1: Update benchmarks
        logger.info("Updating benchmark prices...")
        tickers = ['SPY', 'VT', 'EEMS']
        end_date = date.today()
        start_date = end_date - timedelta(days=1825)
        
        for ticker in tickers:
            try:
                df = fetch_benchmark_prices(ticker, start_date, end_date)
                if not df.empty:
                    stats['prices_updated'] += len(df)
                    logger.info(f"  {ticker}: {len(df)} prices updated")
            except Exception as e:
                stats['errors_count'] += 1
                logger.error(f"Error updating benchmark {ticker}: {e}")
        
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
            recalculate_all_unified(force=True)
        except Exception as e:
            stats['errors_count'] += 1
            logger.error(f"Unified recalculation error: {e}")
        
        # Step 4: Invalidate caches
        logger.info("Invalidating caches...")
        invalidate_cache()
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
        export_data, _, _ = generate_comprehensive_export(force_new=True)
        
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


def init_scheduler(app):
    """Initialize and start the background scheduler."""
    with app.app_context():
        settings = get_scheduler_settings()
        
        if not settings['enabled']:
            logger.info("Automated recalculation is disabled in settings")
            return
        
        # Remove existing job if present
        if scheduler.get_job('automated_recalc'):
            scheduler.remove_job('automated_recalc')
        
        # Add new job based on settings
        day_map = {
            'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 
            'fri': 4, 'sat': 5, 'sun': 6
        }
        
        day_of_week = day_map.get(settings['day_of_week'], 4)  # Default to Friday
        
        scheduler.add_job(
            func=refresh_all_cached_data,
            trigger=CronTrigger(day_of_week=day_of_week, hour=settings['hour'], minute=settings['minute']),
            id='automated_recalc',
            name='Automated Data Refresh',
            replace_existing=True
        )
        
        scheduler.start()
        logger.info(f"Background scheduler started - automated recalculation scheduled for "
                   f"{settings['day_of_week']} at {settings['hour']:02d}:{settings['minute']:02d}")


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
    
    day_of_week = day_map.get(settings['day_of_week'], 4)
    
    # Remove existing job
    if scheduler.get_job('automated_recalc'):
        scheduler.remove_job('automated_recalc')
    
    # Add new job
    scheduler.add_job(
        func=refresh_all_cached_data,
        trigger=CronTrigger(day_of_week=day_of_week, hour=settings['hour'], minute=settings['minute']),
        id='automated_recalc',
        name='Automated Data Refresh',
        replace_existing=True
    )
    
    logger.info(f"Scheduler updated: {settings['day_of_week']} at {settings['hour']:02d}:{settings['minute']:02d}")


# Make db accessible
from .extensions import db
