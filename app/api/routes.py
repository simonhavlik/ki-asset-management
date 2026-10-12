"""Key-secured server-to-server API.

Every endpoint here requires the ``REFRESH_API_KEY`` (a key separate from
``SECRET_KEY``), passed as the ``X-API-Key`` header or a ``?key=`` query param.

    POST /api/refresh-prices         -> start an incremental Yahoo price refresh
                                        (downloads only the missing tail per stock)
    GET  /api/refresh-prices/status  -> whether a run is in flight + last result
"""
import functools
import logging
import threading
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__)

_run_lock = threading.Lock()
_state = {'running': False, 'started_at': None, 'last': None}


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


def _run_incremental_update():
    global _state
    from .. import create_app
    from ..utils.yahooquery_helper import update_all_prices

    app = create_app()
    with app.app_context():
        try:
            result = update_all_prices()  # incremental: only the missing tail per company
            _state['last'] = {
                'finished_at': datetime.now(timezone.utc).isoformat(),
                'ok': True, 'result': result,
            }
            logger.info(f"/api/refresh-prices finished: {result}")
        except Exception as e:  # never let the thread die silently
            logger.exception('refresh-prices failed')
            _state['last'] = {
                'finished_at': datetime.now(timezone.utc).isoformat(),
                'ok': False, 'error': str(e),
            }
        finally:
            _state['running'] = False


@api_bp.route('/refresh-prices', methods=['POST'])
@require_api_key
def refresh_prices():
    """Kick off an incremental price refresh in a background thread."""
    with _run_lock:
        if _state['running']:
            return jsonify({'started': False, 'reason': 'a refresh is already running',
                            'started_at': _state['started_at']}), 409
        _state['running'] = True
        _state['started_at'] = datetime.now(timezone.utc).isoformat()
    threading.Thread(target=_run_incremental_update, daemon=True,
                     name='api-refresh-prices').start()
    return jsonify({'started': True, 'mode': 'incremental'}), 202


@api_bp.route('/refresh-prices/status', methods=['GET'])
@require_api_key
def refresh_prices_status():
    return jsonify({'running': _state['running'],
                    'started_at': _state['started_at'],
                    'last': _state['last']})
