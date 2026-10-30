"""Durable calculated results. Reads never start work, even on a cold worker.

Only the scheduled/explicit refresh calls fetchers with force_refresh=True.
The previous successful result remains readable until its replacement commits.
"""
import inspect
import json
from datetime import date, datetime
from decimal import Decimal
from functools import wraps

from ..extensions import db


def encode(value):
    if isinstance(value, datetime):
        return {'__snapshot_datetime__': value.isoformat()}
    if isinstance(value, date):
        return {'__snapshot_date__': value.isoformat()}
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f'Unsupported snapshot value: {type(value).__name__}')


def decode(value):
    if '__snapshot_datetime__' in value:
        return datetime.fromisoformat(value['__snapshot_datetime__'])
    if '__snapshot_date__' in value:
        return date.fromisoformat(value['__snapshot_date__'])
    return value


def snapshot(default=None):
    """Store a fetcher's result centrally; ordinary callers only read it."""
    def decorate(fn):
        signature = inspect.signature(fn)

        @wraps(fn)
        def read_or_publish(*args, **kwargs):
            from ..models import CalculationSnapshot
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            force = bound.arguments.pop('force_refresh', False)
            key = fn.__name__ + ':' + json.dumps(bound.arguments, sort_keys=True)
            row = CalculationSnapshot.query.filter_by(key=key).first()
            if not force:
                if row is not None:
                    return json.loads(row.payload, object_hook=decode)
                return default() if callable(default) else default
            result = fn(*args, **kwargs)
            payload = json.dumps(result, default=encode, allow_nan=False)
            if row is None:
                row = CalculationSnapshot(key=key)
                db.session.add(row)
            row.payload = payload
            row.cached_at = datetime.utcnow()
            db.session.commit()
            return result
        return read_or_publish
    return decorate


def empty_main_stats():
    return dict.fromkeys([
        'total_users', 'total_analyses', 'approved_analyses', 'portfolio_positions',
        'total_meetings', 'portfolio_return', 'portfolio_return_inception',
        'portfolio_updated', 'benchmark_spy', 'benchmark_ftse', 'benchmark_eems',
        'max_drawdown', 'volatility', 'beta', 'alpha_spy', 'sharpe_ratio', 'win_rate',
    ])
