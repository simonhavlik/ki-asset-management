"""Key-secured server-to-server API.

Every endpoint requires ``REFRESH_API_KEY`` (a key separate from ``SECRET_KEY``),
passed as the ``X-API-Key`` header or a ``?key=`` query param.

    POST /api/refresh-prices          -> incremental Yahoo price refresh (missing tail only)
    GET  /api/refresh-prices/status   -> whether it is in flight + last result
    POST /api/notion-import           -> force the daily Notion import now (returns stats)
    POST /api/recalculate             -> force the weekly full recalculation now
    GET  /api/recalculate/status      -> whether it is in flight + last log row
    GET  /api/jobs                    -> scheduled jobs + next run times + settings
    GET  /api/logs?lines=&level=      -> recent in-process log lines

The force-* endpoints exist so the scheduled jobs can be exercised outside their
cron slot (Render's free instance sleeps when idle, so an on-demand run is how the
schedule is actually verified).
"""
import functools
import hmac
import logging
import threading
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request

from .log_buffer import LOG_BUFFER

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__)

_lock = threading.Lock()
_refresh = {'running': False, 'started_at': None, 'last': None}
_recalc = {'running': False, 'started_at': None, 'last': None}


def _now():
    return datetime.now(timezone.utc).isoformat()


def require_api_key(fn):
    """Reject unless a valid REFRESH_API_KEY is supplied.

    Accepts the same key three ways — ``X-API-Key: <key>``,
    ``Authorization: Bearer <key>`` or ``?key=<key>`` — so a caller cannot fail
    on the header spelling alone.
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        configured = (current_app.config.get('REFRESH_API_KEY') or '').strip()
        if not configured:
            return jsonify({'error': 'refresh API is not configured on the server'}), 503
        authorization = request.headers.get('Authorization') or ''
        bearer = authorization[7:].strip() if authorization.lower().startswith('bearer ') else ''
        provided = (request.headers.get('X-API-Key') or bearer
                    or request.args.get('key') or '').strip()
        if not provided or not hmac.compare_digest(provided, configured):
            return jsonify({'error': 'unauthorized'}), 401
        return fn(*args, **kwargs)
    return wrapper


def _app():
    from .. import create_app
    return create_app()


def _start_run(state, target, thread_name):
    """Atomically claim a run slot; False if one is already running."""
    with _lock:
        if state['running']:
            return False
        state['running'] = True
        state['started_at'] = _now()
    threading.Thread(target=target, daemon=True, name=thread_name).start()
    return True


# ---- incremental price refresh ---------------------------------------------

def _run_incremental_update():
    from ..utils.yahooquery_helper import update_all_prices
    with _app().app_context():
        try:
            result = update_all_prices()  # incremental: only the missing tail per company
            _refresh['last'] = {'finished_at': _now(), 'ok': True, 'result': result}
            logger.info('/api/refresh-prices finished: %s', result)
        except Exception as e:  # never let the thread die silently
            logger.exception('refresh-prices failed')
            _refresh['last'] = {'finished_at': _now(), 'ok': False, 'error': str(e)}
        finally:
            _refresh['running'] = False


@api_bp.route('/refresh-prices', methods=['POST'])
@require_api_key
def refresh_prices():
    """Kick off an incremental price refresh in a background thread."""
    if not _start_run(_refresh, _run_incremental_update, 'api-refresh-prices'):
        return jsonify({'started': False, 'reason': 'a refresh is already running',
                        'started_at': _refresh['started_at']}), 409
    return jsonify({'started': True, 'mode': 'incremental'}), 202


@api_bp.route('/refresh-prices/status', methods=['GET'])
@require_api_key
def refresh_prices_status():
    return jsonify({'running': _refresh['running'], 'started_at': _refresh['started_at'],
                    'last': _refresh['last']})


# ---- forced Notion import (the daily job) ----------------------------------

@api_bp.route('/notion-import', methods=['POST'])
@require_api_key
def notion_import():
    """Run the daily Notion import now and return its stats (synchronous)."""
    from ..utils.notion_import import run_notion_import
    started = _now()
    with _app().app_context():
        stats = run_notion_import()
    ok = bool(stats.get('success'))
    logger.info('/api/notion-import: ok=%s %s', ok, {
        k: stats.get(k) for k in ('created', 'updated', 'skipped', 'blank', 'unchanged', 'total')
    })
    return jsonify({'ok': ok, 'started_at': started, 'finished_at': _now(),
                    'stats': stats, 'logs': LOG_BUFFER.tail(40, 'INFO')}), (200 if ok else 500)


# ---- forced full recalculation (the weekly job) ----------------------------

def _run_recalc():
    from ..models import RecalculationLog
    from ..scheduler import refresh_all_cached_data
    with _app().app_context():
        try:
            refresh_all_cached_data(run_type='api')
            row = RecalculationLog.query.order_by(RecalculationLog.id.desc()).first()
            _recalc['last'] = {
                'finished_at': _now(), 'ok': (row.status == 'completed') if row else None,
                'log_id': row.id if row else None, 'status': row.status if row else None,
                'duration_seconds': row.duration_seconds if row else None,
                'analyses_processed': row.analyses_processed if row else None,
                'prices_updated': row.prices_updated if row else None,
                'calculations_updated': row.calculations_updated if row else None,
                'errors_count': row.errors_count if row else None,
                'error_message': row.error_message if row else None,
                'details': row.details if row else None,
            }
        except Exception as e:
            logger.exception('api recalculate failed')
            _recalc['last'] = {'finished_at': _now(), 'ok': False, 'error': str(e)}
        finally:
            _recalc['running'] = False


@api_bp.route('/recalculate', methods=['POST'])
@require_api_key
def recalculate():
    """Force the weekly full recalculation now (runs in the background)."""
    if not _start_run(_recalc, _run_recalc, 'api-recalculate'):
        return jsonify({'started': False, 'reason': 'a recalculation is already running',
                        'started_at': _recalc['started_at']}), 409
    return jsonify({'started': True, 'mode': 'full-recalculation'}), 202


@api_bp.route('/recalculate/status', methods=['GET'])
@require_api_key
def recalculate_status():
    return jsonify({'running': _recalc['running'], 'started_at': _recalc['started_at'],
                    'last': _recalc['last']})


# ---- visibility ------------------------------------------------------------

@api_bp.route('/jobs', methods=['GET'])
@require_api_key
def jobs():
    """The scheduler's jobs: next run, trigger, and the last run's outcome."""
    import os
    import threading
    import time as _time

    from ..scheduler import HEARTBEAT, SCHEDULER_ROLE, load_run, scheduler, get_scheduler_settings

    out = []
    for j in scheduler.get_jobs():
        nxt = getattr(j, 'next_run_time', None)
        out.append({'id': j.id, 'name': j.name,
                    'next_run': nxt.isoformat() if nxt else None,
                    'trigger': str(j.trigger),
                    'last_run': load_run(j.id)})

    # Diagnostics: a background scheduler that reports next_run in the past is
    # either asleep, restarted, or has lost its worker thread. The process start
    # time and the live thread list say which — without paying for Render logs.
    proc_started = None
    try:
        with open('/proc/self/stat', 'r') as fh:
            fields = fh.read().split()
        ticks = os.sysconf('SC_CLK_TCK')
        uptime = float(open('/proc/uptime').read().split()[0])
        process_age = uptime - (int(fields[21]) / ticks)  # field 22 = starttime
        proc_started = _time.time() - process_age
    except Exception:  # noqa: BLE001 - diagnostics are best effort
        proc_started = None
    try:
        with open('/proc/self/cmdline', 'rb') as fh:
            cmdline = fh.read().decode('utf-8', 'replace').split('\x00')
    except Exception:  # noqa: BLE001
        cmdline = []

    return jsonify({'scheduler_running': scheduler.running,
                    'role': SCHEDULER_ROLE,
                    'settings': get_scheduler_settings(),
                    'diag': {
                        'now': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                        'pid': os.getpid(),
                        'process_started': (datetime.fromtimestamp(proc_started, tz=timezone.utc)
                                            .isoformat(timespec='seconds')) if proc_started else None,
                        'cmdline': [c for c in cmdline if c][:8],
                        'scheduler_thread_alive': bool(getattr(scheduler, '_thread', None)
                                                       and scheduler._thread.is_alive()),
                        'threads': [t.name for t in threading.enumerate()],
                        'gunicorn_env': os.environ.get('GUNICORN_CMD_ARGS'),
                        'skip_warm': os.environ.get('KI_SKIP_WARM'),
                        'heartbeat': HEARTBEAT,
                    },
                    'jobs': out})


@api_bp.route('/logs', methods=['GET'])
@require_api_key
def logs():
    """Recent in-process log lines, filtered.

    Options: ``lines``/``limit`` (count), ``level`` (DEBUG…CRITICAL), ``since``
    (ISO timestamp or a relative window such as ``-30m``), ``logger`` (name
    prefix), ``q`` (case-insensitive substring) and ``include_requests=1`` to
    keep HTTP request lines — they are excluded by default because the public
    site is scanned constantly and that chatter hides the job logs.
    """
    raw = request.args.get('lines') or request.args.get('limit') or '200'
    try:
        lines = max(1, int(raw))
    except (TypeError, ValueError):
        lines = 200
    include_requests = str(request.args.get('include_requests', '')).lower() in ('1', 'true', 'yes', 'on')
    level = request.args.get('level', 'INFO')
    since = request.args.get('since')
    logger_name = request.args.get('logger')
    needle = request.args.get('q')
    rows = LOG_BUFFER.tail(lines, level, since=since, logger=logger_name, q=needle,
                           include_requests=include_requests)
    return jsonify({
        'lines': rows,
        'returned': len(rows),
        'filters': {'level': level, 'since': since, 'logger': logger_name,
                    'q': needle, 'include_requests': include_requests, 'limit': lines},
        'buffer': LOG_BUFFER.stats(),
    })
