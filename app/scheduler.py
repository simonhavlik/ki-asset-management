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
import time
from datetime import datetime, timedelta, timezone
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

# Last-run bookkeeping per job id, surfaced by GET /api/jobs so an operator can
# see whether the automation actually ran, how long it took and what it returned
# — without reading Render's (paid) logs. One small record per job, overwritten
# on every run; the process restart clears it, which is fine: next_run shows the
# schedule and the log buffer holds the detail.
JOB_RUNS = {}


# --- who owns the schedule ---------------------------------------------------
# A preloaded gunicorn master and the worker it forks both build the app, so both
# would add the jobs and both would run them (the daily import twice, the weekly
# recalculation twice). A Postgres advisory lock on a dedicated connection decides:
# the process that acquires it runs the jobs ("owner"), every other process only
# reports ("follower") and never starts a scheduler of its own.
SCHEDULER_LOCK_KEY = 0x6B692121          # 'ki!!'
SCHEDULER_ROLE = 'unknown'
_owner_conn = None                       # held open for the process's lifetime
_ownership_decided = False               # create_app() may run several times


def _try_owner_lock():
    """One-shot attempt at the advisory lock (True = this process owns it)."""
    from .models import db

    global _owner_conn
    try:
        if db.engine.dialect.name != 'postgresql':
            return True                  # SQLite/tests: one process anyway
        conn = db.engine.raw_connection()   # dedicated: the pool must not recycle it
        cur = conn.cursor()
        cur.execute("select pg_try_advisory_lock(%s)", (SCHEDULER_LOCK_KEY,))
        got = bool(cur.fetchone()[0])
        cur.close()
        if got:
            _owner_conn = conn
            return True
        conn.close()
        return False
    except Exception as exc:  # noqa: BLE001 - better to run than to stay idle
        logger.warning("scheduler ownership check failed (%s); assuming owner", exc)
        return True


def _acquire_owner_lock(app):
    """Decide, once per process, whether this process runs the jobs.

    create_app() runs several times per process (render_start.py's helpers, then
    gunicorn), so the answer has to stick: a second attempt would find the lock
    already held by this same process and wrongly demote it to follower.
    """
    global _ownership_decided, SCHEDULER_ROLE
    if _ownership_decided:
        return SCHEDULER_ROLE == 'owner'
    _ownership_decided = True
    owner = _try_owner_lock()
    SCHEDULER_ROLE = 'owner' if owner else 'follower'
    return owner


def _ensure_job_runs_table(app):
    """Last-run records that survive a restart and are readable by any process.

    The in-memory JOB_RUNS dict only describes the process that ran the job; the
    API is served by a different one when gunicorn preloads, so the record has to
    live in the database to be truthful.
    """
    from sqlalchemy import text as _sa_text
    from .models import db

    try:
        if db.engine.dialect.name != 'postgresql':
            return
        with db.engine.begin() as conn:
            conn.execute(_sa_text("""
                create table if not exists job_runs (
                    job_id text primary key,
                    status text,
                    started_at timestamptz,
                    finished_at timestamptz,
                    duration_seconds double precision,
                    error text,
                    result text
                )"""))
    except Exception as exc:  # noqa: BLE001 - bookkeeping must never block boot
        app.logger.warning("job_runs table check failed: %s", exc)


def _persist_run(record):
    """Best-effort write of one run record (never raises)."""
    from sqlalchemy import text as _sa_text
    from .models import db

    try:
        if db.engine.dialect.name != 'postgresql':
            return
        import json as _json
        with db.engine.begin() as conn:
            conn.execute(_sa_text("""
                insert into job_runs (job_id, status, started_at, finished_at,
                                      duration_seconds, error, result)
                values (:job_id, :status, cast(:started_at as timestamptz),
                        cast(:finished_at as timestamptz), :duration_seconds, :error, :result)
                on conflict (job_id) do update set
                    status = excluded.status, started_at = excluded.started_at,
                    finished_at = excluded.finished_at,
                    duration_seconds = excluded.duration_seconds,
                    error = excluded.error, result = excluded.result
            """), {'job_id': record.get('job_id'), 'status': record.get('status'),
                   'started_at': record.get('started_at'), 'finished_at': record.get('finished_at'),
                   'duration_seconds': record.get('duration_seconds'),
                   'error': record.get('error'),
                   'result': _json.dumps(record.get('result'), ensure_ascii=False)
                   if record.get('result') is not None else None})
    except Exception:  # noqa: BLE001
        pass


def load_run(job_id):
    """The last recorded run of a job, from this process or the database."""
    from sqlalchemy import text as _sa_text
    from .models import db

    rec = JOB_RUNS.get(job_id)
    if rec:
        return rec
    try:
        if db.engine.dialect.name != 'postgresql':
            return None
        import json as _json
        with db.engine.connect() as conn:
            row = conn.execute(_sa_text("""select job_id, status, started_at, finished_at,
                                                  duration_seconds, error, result
                                           from job_runs where job_id = :j"""),
                               {'j': job_id}).fetchone()
        if not row:
            return None
        out = {'job_id': row[0], 'status': row[1],
               'started_at': row[2].isoformat() if row[2] else None,
               'finished_at': row[3].isoformat() if row[3] else None,
               'duration_seconds': row[4], 'error': row[5]}
        try:
            out['result'] = _json.loads(row[6]) if row[6] else None
        except (TypeError, ValueError):
            out['result'] = None
        return out
    except Exception:  # noqa: BLE001
        return None


def _iso(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec='seconds')


def _summarize(value):
    """Small, JSON-safe summary of whatever a job returned."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {k: v for k, v in list(value.items())[:8]
                if isinstance(v, (bool, int, float, str))}
    if isinstance(value, (list, tuple)):
        return f'{len(value)} item(s)'
    return None


def _tracked(job_id, job_func):
    """Wrap a job so its outcome lands in JOB_RUNS (never swallows the error)."""
    @functools.wraps(job_func)
    def wrapper(*args, **kwargs):
        started = time.time()
        record = {'job_id': job_id, 'status': 'running', 'started_at': _iso(started),
                  'finished_at': None, 'duration_seconds': None, 'error': None,
                  'result': None}
        JOB_RUNS[job_id] = record
        try:
            result = job_func(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - record, then let APScheduler log it
            record.update(status='error', error=f'{type(exc).__name__}: {exc}')
            raise
        else:
            record.update(status='ok', result=_summarize(result))
            return result
        finally:
            record['finished_at'] = _iso(time.time())
            record['duration_seconds'] = round(time.time() - started, 2)
            _persist_run(record)
    return wrapper


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


def notion_import_if_stale(max_age_hours: int = 20) -> None:
    """Run the Notion import only if the last one is older than ``max_age_hours``.

    Safety net for the 04:00 job: if the instance was asleep (or restarting) at
    04:00 and APScheduler skipped the misfired run, this catches up within the
    hour. Normally a no-op, because the 04:00 import ran.
    """
    from .models import CsvUpload
    last = (CsvUpload.query.filter(CsvUpload.filename.like('notion_import_%'))
            .order_by(CsvUpload.id.desc()).first())
    if last and last.processed_at and (datetime.utcnow() - last.processed_at) < timedelta(hours=max_age_hours):
        logger.debug("Notion safety net: last import %s is fresh; nothing to do", last.processed_at)
        return
    logger.info("Notion safety net: last import is stale or missing - importing now")
    import_notion_daily()


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


def _register_jobs(app):
    """Create every scheduled job on the module-level scheduler.

    Called at boot, and again after the watchdog restarts a scheduler whose
    worker thread was lost: the job store is in memory, so jobs have to be
    re-added if the scheduler was rebuilt from empty.
    """
    with app.app_context():
        # Always scheduled, and never gated on the recalculation setting: this
        # is the safety net for undeliverable mail.
        scheduler.add_job(
            func=_tracked('email_outbox_retry', _with_app_context(retry_queued_emails)),
            trigger=IntervalTrigger(minutes=15),
            id='email_outbox_retry',
            name='Email outbox retry',
            replace_existing=True,
            coalesce=True,
            misfire_grace_time=300,
        )

        # Daily autonomous Notion import. Deliberately always on: keeping the
        # site in step with Notion is the point, and the job is a no-op when
        # nothing changed.
        scheduler.add_job(
            func=_tracked('daily_notion_import', _with_app_context(import_notion_daily)),
            trigger=CronTrigger(hour=DAILY_IMPORT_HOUR, minute=DAILY_IMPORT_MINUTE,
                                timezone=TIMEZONE),
            id='daily_notion_import',
            name='Daily Notion import',
            replace_existing=True,
            coalesce=True,
            misfire_grace_time=60,
        )
        logger.info(f"Daily Notion import scheduled for "
                    f"{DAILY_IMPORT_HOUR:02d}:{DAILY_IMPORT_MINUTE:02d} {TIMEZONE}")

        # Safety net: guarantee the daily Notion sync even if the 04:00 slot was
        # missed (instance asleep/restarting). Runs hourly but only acts when the
        # last import is stale, so 04:00 stays the primary trigger.
        scheduler.add_job(
            func=_tracked('notion_import_guard', _with_app_context(notion_import_if_stale)),
            trigger=IntervalTrigger(hours=1),
            id='notion_import_guard',
            name='Notion import safety net',
            replace_existing=True,
            coalesce=True,
            misfire_grace_time=600,
        )

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
                func=_tracked('automated_recalc', _with_app_context(weekly_data_refresh)),
                trigger=CronTrigger(day_of_week=day_of_week, hour=settings['hour'],
                                    minute=settings['minute'], timezone=TIMEZONE),
                id='automated_recalc',
                name='Automated Data Refresh',
                replace_existing=True,
                # A missed Monday slot is DROPPED, never caught up: the jobstore is
                # in-memory, so a restarted/asleep instance simply schedules the next
                # Monday. Starting a multi-minute full recalculation on boot or on
                # wake is far worse than skipping one week - the 04:00 slot (and the
                # manual /api/recalculate endpoint) is the only place it may start.
                coalesce=True,
                misfire_grace_time=1,
            )

            logger.info(f"Automated recalculation scheduled for "
                       f"{settings['day_of_week']} at {settings['hour']:02d}:{settings['minute']:02d} {TIMEZONE}")
        else:
            logger.info("Automated recalculation is disabled in settings")


def init_scheduler(app):
    """Initialize and start the background scheduler (owner process only)."""
    global _app, SCHEDULER_ROLE
    _app = app

    # A preloaded master and its forked worker both build the app: without this
    # gate, both would run every job. Reporters never start a scheduler.
    if not _acquire_owner_lock(app):
        SCHEDULER_ROLE = 'follower'
        # Still register the jobs and start the scheduler *paused*: nothing runs
        # (the owner has the schedule), but /api/jobs can report every job, its
        # trigger and its persisted last run from whichever process serves the
        # request.
        _register_jobs(app)
        if not scheduler.running:
            try:
                scheduler.start(paused=True)
            except Exception as exc:  # noqa: BLE001
                logger.exception("paused scheduler start failed: %s", exc)
        logger.info("another process owns the job schedule; this one only reports")
        _start_watchdog()
        return

    SCHEDULER_ROLE = 'owner'
    _register_jobs(app)

    if not scheduler.running:
        try:
            scheduler.start()
            logger.info("Background scheduler started (owner)")
        except Exception as exc:  # noqa: BLE001 - a broken scheduler must not
            logger.exception("scheduler start failed: %s", exc)  # kill the app

    _start_watchdog()


# ---------------------------------------------------------------------------
# Liveness watchdog
# ---------------------------------------------------------------------------
# A BackgroundScheduler whose worker thread is gone reports next_run times in the
# past for ever and silently stops running the club's imports and the email
# retry - exactly what production showed (a live, HTTP-answering process with a
# next_run 17 minutes stale). Nothing else watches it on a single-worker free
# instance, so a small daemon thread does: it records a heartbeat (exposed by
# /api/jobs) and restarts the scheduler when the thread is gone or when a job
# has been overdue far longer than any plausible scheduling delay.
HEARTBEAT = {'at': None, 'running': None, 'thread_alive': None, 'next': {},
             'restarts': 0, 'last_error': None}
WATCHDOG_INTERVAL = 60          # seconds between liveness checks
STALE_JOB_SECONDS = 900         # a job overdue by this much means the loop is gone
HEARTBEAT_EVERY = 5             # log a heartbeat every N checks (5 minutes)

_watchdog_thread = None              # the watchdog thread of *this* process
_watchdog_stop = threading.Event()   # set on shutdown: never restart a dying app


def scheduler_thread_alive():
    """Whether the scheduler's own worker thread is alive."""
    thread = getattr(scheduler, '_thread', None)
    return bool(thread and thread.is_alive())


def _stalest_job(now):
    """(job_id, seconds_overdue) for the job furthest past its scheduled time."""
    worst = None
    for job in scheduler.get_jobs():
        nxt = getattr(job, 'next_run_time', None)
        if nxt is None:
            continue
        late = (now - nxt).total_seconds()
        if late > 0 and (worst is None or late > worst[1]):
            worst = (job.id, late)
    return worst


def _restart_scheduler(reason):
    """Replace the scheduler with a fresh, running one.

    APScheduler's ``shutdown()`` also shuts down the executors, and the default
    ThreadPoolExecutor cannot be reused ("cannot schedule new futures after
    shutdown"), so the object has to be rebuilt rather than restarted. The module
    global is rebound: every caller resolves it at call time (routes.py imports it
    inside the view), so they all pick up the new instance.
    """
    global scheduler
    old = scheduler
    try:
        if old.running:
            old.shutdown(wait=False)
    except Exception as exc:  # noqa: BLE001 - the old one is being discarded anyway
        logger.warning("scheduler shutdown during restart failed: %s", exc)
    try:
        scheduler = BackgroundScheduler()
        if _app is not None:
            _register_jobs(_app)
        scheduler.start()
        HEARTBEAT['restarts'] += 1
        HEARTBEAT['last_error'] = reason
        logger.warning("scheduler restarted (%s); %d job(s)", reason, len(scheduler.get_jobs()))
        return True
    except Exception as exc:  # noqa: BLE001 - record and keep the app serving
        HEARTBEAT['last_error'] = f'{type(exc).__name__}: {exc}'
        logger.exception("scheduler restart failed: %s", exc)
        return False


def _watchdog_loop():
    checks = 0
    while not _watchdog_stop.is_set():
        time.sleep(WATCHDOG_INTERVAL)
        if _watchdog_stop.is_set():
            return
        checks += 1
        try:
            now = datetime.now(timezone.utc)
            alive = scheduler_thread_alive()
            HEARTBEAT.update({'at': now.isoformat(timespec='seconds'),
                              'running': scheduler.running,
                              'thread_alive': alive,
                              'next': {j.id: (j.next_run_time.isoformat(timespec='seconds')
                                              if j.next_run_time else None)
                                       for j in scheduler.get_jobs()}})
            if SCHEDULER_ROLE != 'owner':
                # Reporters must never start a scheduler: that would double-run
                # every job next to the process that owns the schedule.
                if checks % HEARTBEAT_EVERY == 0:
                    logger.info("scheduler heartbeat: follower (schedule owned by another process)")
                continue
            if not alive:
                _restart_scheduler('worker thread not alive')
            else:
                stale = _stalest_job(now)
                if stale and stale[1] > STALE_JOB_SECONDS:
                    _restart_scheduler(f'{stale[0]} overdue by {stale[1] / 60:.1f} min')
            if checks % HEARTBEAT_EVERY == 0:
                logger.info("scheduler heartbeat: running=%s thread=%s next=%s",
                            HEARTBEAT['running'], HEARTBEAT['thread_alive'], HEARTBEAT['next'])
        except Exception as exc:  # noqa: BLE001 - the watchdog itself must never die
            logger.warning("scheduler watchdog error: %s", exc)


def _start_watchdog():
    global _watchdog_thread
    if _watchdog_thread is not None and _watchdog_thread.is_alive():
        return
    # Deliberately not a boolean flag: after a gunicorn fork the parent's thread
    # object is still referenced but its thread does not exist in the child, and a
    # flag would make the child believe it already has a watchdog.
    _watchdog_thread = threading.Thread(target=_watchdog_loop, name='scheduler-watchdog',
                                        daemon=True)
    _watchdog_thread.start()
    logger.info("scheduler watchdog started (checks every %ss)", WATCHDOG_INTERVAL)


# --- request-path safety net -------------------------------------------------
# create_app() is also called by the pre-start helpers (render_start.py) and, if
# the service ever runs gunicorn with --preload, by the gunicorn master - whose
# threads do not survive the fork into the worker that actually serves requests.
# So the process that answers HTTP re-checks its own scheduler on the request
# path: cheap (a timestamp comparison), idempotent, and it means a lost or
# never-started scheduler recovers on the first request instead of never.
_last_ensure = 0.0
_ensure_lock = threading.Lock()


def ensure_scheduler_healthy(max_age_seconds=30):
    """Owner: revive the scheduler if its thread died. Follower: report only.

    Never starts a scheduler in a process that does not own the schedule - a
    preloaded master's worker would otherwise run every job a second time.
    """
    global _last_ensure
    now = time.time()
    with _ensure_lock:
        if now - _last_ensure < max_age_seconds:
            return False
        _last_ensure = now
    _start_watchdog()
    if _watchdog_stop.is_set() or SCHEDULER_ROLE != 'owner':
        return False
    if not scheduler_thread_alive():
        return _restart_scheduler('request path: scheduler thread not alive')
    return False


def shutdown_scheduler():
    """Shutdown the scheduler gracefully."""
    _watchdog_stop.set()
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
        func=_tracked('automated_recalc', _with_app_context(weekly_data_refresh)),
        trigger=CronTrigger(day_of_week=day_of_week, hour=settings['hour'],
                            minute=settings['minute'], timezone=TIMEZONE),
        id='automated_recalc',
        name='Automated Data Refresh',
        replace_existing=True,
        # Same policy as init_scheduler: a missed slot is dropped, never caught up.
        coalesce=True,
        misfire_grace_time=1,
    )
    
    logger.info(f"Scheduler updated: {settings['day_of_week']} at {settings['hour']:02d}:{settings['minute']:02d} {TIMEZONE}")


# Make db accessible
from .extensions import db
