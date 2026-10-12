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
    """Reject unless a valid REFRESH_API_KEY is supplied."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        configured = (current_app.config.get('REFRESH_API_KEY') or '').strip()
        if not configured:
            return jsonify({'error': 'refresh API is not configured on the server'}), 503
        provided = (request.headers.get('X-API-Key') or request.args.get('key') or '').strip()
        if not provided or provided != configured:
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
    """The scheduler's jobs, their next run times, and the recalc settings."""
    from ..scheduler import scheduler, get_scheduler_settings
    out = []
    for j in scheduler.get_jobs():
        nxt = getattr(j, 'next_run_time', None)
        out.append({'id': j.id, 'name': j.name,
                    'next_run': nxt.isoformat() if nxt else None,
                    'trigger': str(j.trigger)})
    return jsonify({'scheduler_running': scheduler.running,
                    'settings': get_scheduler_settings(), 'jobs': out})


@api_bp.route('/logs', methods=['GET'])
@require_api_key
def logs():
    """Recent in-process log lines (so a forced run can be read back)."""
    try:
        lines = int(request.args.get('lines', 200))
    except (TypeError, ValueError):
        lines = 200
    return jsonify({'lines': LOG_BUFFER.tail(lines, request.args.get('level', 'INFO'))})
