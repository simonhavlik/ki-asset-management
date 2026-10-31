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
    conn = None
    try:
        if db.engine.dialect.name != 'postgresql':
            return True                  # SQLite/tests: one process anyway
        conn = db.engine.raw_connection()   # dedicated: the pool must not recycle it
        cur = conn.cursor()
        cur.execute("select pg_try_advisory_lock(%s)", (SCHEDULER_LOCK_KEY,))
        got = bool(cur.fetchone()[0])
        cur.close()
        conn.commit()
        if got:
            _owner_conn = conn
            return True
        conn.close()
        return False
    except Exception as exc:  # noqa: BLE001 - better to run than to stay idle
        if conn is not None:
            conn.close()
        logger.warning("scheduler ownership check failed (%s); waiting to retry", exc)
        return False


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

    from flask import has_app_context
    if not has_app_context() and _app is not None:
        with _app.app_context():
            return _persist_run(record)
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
        _persist_run(record)
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
    from .utils.maintenance import schedule_settings
    return schedule_settings('recalc')


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
        stats = run_notion_import(run_type='scheduled')

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
    if not stats.get('success') and not stats.get('busy'):
        raise RuntimeError(stats.get('error') or 'Notion import failed')
    return stats


def notion_import_if_stale(max_age_hours: int = 20) -> None:
    """Run the Notion import only if the last one is older than ``max_age_hours``.

    Safety net for the 04:00 job: if the instance was asleep (or restarting) at
    04:00 and APScheduler skipped the misfired run, this catches up within the
    hour. Normally a no-op, because the 04:00 import ran.
    """
    from .models import CsvUpload, MaintenanceRun
    from .utils.maintenance import schedule_settings, due_slot
    settings = schedule_settings('notion')
    if not settings['enabled']:
        return
    due = due_slot(settings).astimezone(timezone.utc).replace(tzinfo=None)
    last = MaintenanceRun.query.filter_by(job='notion', status='completed').order_by(MaintenanceRun.started_at.desc()).first()
    upload = CsvUpload.query.filter(CsvUpload.filename.like('notion_%'), CsvUpload.processed_at.isnot(None)).order_by(CsvUpload.processed_at.desc()).first()
    latest = max([d for d in [last.started_at if last else None, upload.processed_at if upload else None] if d], default=None)
    if latest and latest >= due:
        return
    attempt = MaintenanceRun.query.filter_by(job='notion').order_by(MaintenanceRun.started_at.desc()).first()
    if attempt and attempt.started_at > datetime.utcnow() - timedelta(hours=1):
        return
    return import_notion_daily()


def weekly_data_refresh():
    """Full data refresh + recalculation (the weekly job).

    Runs under the shared lock so it cannot overlap the daily Notion import on a
    Monday, and inside an app context (via _with_app_context at registration).
    """
    with _run_lock:
        return refresh_all_cached_data(run_type='scheduled')


def scheduled_recalc_if_due():
    """Overnight catch-up if a restart missed the weekly slot; never a page hook."""
    from zoneinfo import ZoneInfo
    from .models import RecalculationLog
    settings = get_scheduler_settings()
    if not settings['enabled']:
        return
    from .utils.maintenance import due_slot
    due = due_slot(settings, now=datetime.now(ZoneInfo(TIMEZONE)))
    latest = RecalculationLog.query.filter_by(status='completed').order_by(
        RecalculationLog.started_at.desc()).first()
    due_utc = due.astimezone(timezone.utc).replace(tzinfo=None)
    if latest is None or latest.started_at < due_utc:
        return weekly_data_refresh()


def refresh_all_cached_data(run_type='scheduled'):
    """Use the same complete publisher as an explicit central refresh."""
    from .utils.full_recalc import _run_full_recalculation
    result = _run_full_recalculation(run_type)
    if result is not None and not result.get('skipped'):
        try:
            _refresh_presentation_exports()
        except Exception as exc:
            logger.warning('Presentation export warming failed: %s', exc)
    return result


def _refresh_presentation_exports():
    """Preserve scheduled export warming after the page snapshots are published."""
    from flask import current_app
    from .utils.presentation_export import get_growth_timeline, get_sector_analysis
    from .utils.export_helper import generate_comprehensive_export

    get_growth_timeline(use_cache=False)
    get_sector_analysis(use_cache=False)
    app = current_app._get_current_object()

    def build():
        try:
            with app.app_context():
                generate_comprehensive_export(force_new=True)
        except Exception as exc:
            logger.warning('Comprehensive export failed: %s', exc)

    thread = threading.Thread(target=build, daemon=True, name='recalc-export')
    thread.start()
    thread.join(timeout=180)


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


_applied_schedule_signature = None


def _schedule_signature():
    from .utils.maintenance import schedule_settings
    return repr([schedule_settings('notion'), schedule_settings('recalc')])


def _reload_schedule_if_changed():
    if _applied_schedule_signature != _schedule_signature():
        _register_jobs(_app)


def _register_jobs(app):
    """Create every scheduled job on the module-level scheduler.

    Called at boot, and again after the watchdog restarts a scheduler whose
    worker thread was lost: the job store is in memory, so jobs have to be
    re-added if the scheduler was rebuilt from empty.
    """
    global _applied_schedule_signature
    with app.app_context():
        _applied_schedule_signature = _schedule_signature()
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

        from .utils.maintenance import schedule_settings, schedule_trigger
        notion = schedule_settings('notion')
        if notion['enabled']:
            scheduler.add_job(func=_tracked('daily_notion_import', _with_app_context(import_notion_daily)),
                              trigger=schedule_trigger(notion), id='daily_notion_import',
                              name='Notion import', replace_existing=True, coalesce=True, misfire_grace_time=3600, max_instances=1)
        elif scheduler.get_job('daily_notion_import'):
            scheduler.remove_job('daily_notion_import')
        scheduler.add_job(func=_with_app_context(_reload_schedule_if_changed),
                          trigger=IntervalTrigger(minutes=1), id='schedule_settings_sync',
                          name='Apply saved schedules', replace_existing=True, coalesce=True)

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

        scheduler.add_job(
            func=_tracked('recalc_catchup', _with_app_context(scheduled_recalc_if_due)),
            trigger=CronTrigger(hour='0-5', minute=15, timezone=TIMEZONE),
            id='recalc_catchup', name='Overnight recalculation safety net',
            replace_existing=True, coalesce=True, misfire_grace_time=3600,
        )

        from .utils.site_content import refresh_market_tape
        scheduler.add_job(
            func=_tracked('market_tape', _with_app_context(refresh_market_tape)),
            trigger=IntervalTrigger(minutes=15), id='market_tape',
            name='Market quote snapshot', replace_existing=True,
            coalesce=True, misfire_grace_time=300, max_instances=1,
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
                trigger=schedule_trigger(settings),
                id='automated_recalc',
                name='Automated Data Refresh',
                replace_existing=True,
                # Allow a short scheduler delay; missed runs also have an
                # overnight-only catch-up job, never a page-load fallback.
                coalesce=True,
                misfire_grace_time=3600,
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


_promotion_lock = threading.Lock()


def _promote_if_owner_available():
    """A replacement instance takes over only after the old owner's lock releases."""
    global SCHEDULER_ROLE, _ownership_decided
    if _app is None or SCHEDULER_ROLE == 'owner':
        return False
    with _promotion_lock, _app.app_context():
        if SCHEDULER_ROLE == 'owner' or not _try_owner_lock():
            return False
        SCHEDULER_ROLE, _ownership_decided = 'owner', True
        _register_jobs(_app)
        if scheduler.running:
            scheduler.resume()
        else:
            scheduler.start()
        logger.info('Scheduler ownership acquired after previous instance stopped')
        return True


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
                _promote_if_owner_available()
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
    """Apply saved settings here; the owner also synchronizes every minute."""
    if _app is not None:
        _register_jobs(_app)


# Make db accessible
from .extensions import db
