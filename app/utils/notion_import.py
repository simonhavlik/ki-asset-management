"""Import the Notion "Analysis Schedule" database into the app.

One code path shared by three callers:
  * ``flask notion-import`` (manual, from a shell)
  * the Admin "Download from Notion" button (app/admin/routes.py)
  * the autonomous daily job in app/scheduler.py

Notion is a read-only source: this pulls the database, maps its properties to
the CSV columns CsvImporter expects, and imports - it never writes back to
Notion. Re-running is safe: unchanged rows are detected and left alone.
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def notion_credentials():
    """Return (api_key, database_id) from the environment, then SystemSettings.

    The environment wins because that is where Render sets it; SystemSettings is
    the admin-UI fallback used when the row is present in the database.
    """
    import os
    from ..models import SystemSettings

    api_key = (os.environ.get('NOTION_API_KEY', '')
               or SystemSettings.get('notion_api_key', ''))
    database_id = (os.environ.get('NOTION_DATABASE_ID', '')
                   or SystemSettings.get('notion_database_id', ''))
    return api_key, database_id


import threading
_import_lock = threading.Lock()


def run_notion_import(uploaded_by=None, run_type='manual'):
    """One import across scheduler/manual requests and overlapping deployments."""
    from ..extensions import db
    connection = None
    acquired = False
    if not _import_lock.acquire(blocking=False):
        return {'success': False, 'busy': True, 'error': 'An import is already running'}
    try:
        if db.engine.dialect.name == 'postgresql':
            connection = db.engine.raw_connection()
            cursor = connection.cursor()
            cursor.execute('SELECT pg_try_advisory_lock(%s)', (0x6B696E6F74696F6E,))
            acquired = bool(cursor.fetchone()[0])
            cursor.close()
            connection.commit()
            if not acquired:
                return {'success': False, 'busy': True, 'error': 'An import is already running'}
        return _recorded_notion_import(uploaded_by, run_type)
    finally:
        if connection is not None:
            try:
                if acquired:
                    cursor = connection.cursor()
                    cursor.execute('SELECT pg_advisory_unlock(%s)', (0x6B696E6F74696F6E,))
                    cursor.close()
                    connection.commit()
            finally:
                connection.close()
        _import_lock.release()


def _recorded_notion_import(uploaded_by=None, run_type='manual'):
    from ..extensions import db
    from ..models import MaintenanceRun
    run = MaintenanceRun(job='notion', run_type=run_type, status='running')
    db.session.add(run)
    db.session.commit()
    try:
        stats = _import_notion(uploaded_by)
        run.status = 'completed' if stats.get('success') else 'failed'
        run.details = stats
        run.error = stats.get('error')
        return stats
    except Exception as exc:
        db.session.rollback()
        run.status, run.error = 'failed', str(exc)
        raise
    finally:
        run.completed_at = datetime.utcnow()
        db.session.commit()


def _import_notion(uploaded_by=None):
    """Fetch the Notion database and import it into the analyses table.

    Returns the CsvImporter stats dict (``success`` + ``created``/``updated``/
    ``skipped``/``unchanged``/``blank``/``total``/``errors``). It never raises
    for a Notion or transport problem - it logs and returns ``success: False`` -
    so a scheduled caller can record the outcome and carry on.

    Public caches for the cheap, public pages are invalidated when the import
    actually changed something, so new rows show up without waiting for the
    weekly recalculation. The heavy overview/board/dashboard caches are left to
    that recalculation on purpose.
    """
    from .notion_helper import NotionClient, NotionAPIError, build_notion_column_mapping
    from .csv_import import CsvImporter

    api_key, database_id = notion_credentials()
    if not api_key or not database_id:
        logger.warning(
            'Notion import skipped: NOTION_API_KEY/NOTION_DATABASE_ID are not configured'
        )
        return {'success': False, 'error': 'Notion not configured', 'errors': []}

    client = NotionClient(api_key)
    try:
        properties = client.get_database_properties(database_id)
        column_mapping = build_notion_column_mapping(properties)
        resolved = {prop.strip() or prop: col for prop, col in column_mapping.items()}
        logger.info('Notion column mapping: %s', resolved)
        missing = [col for prop, col in column_mapping.items()
                   if prop.startswith('__missing__')]
        if missing:
            logger.warning(
                'Notion has no property for %s - those columns import empty', missing
            )

        csv_content = client.export_database_as_csv(database_id, column_mapping)
        if not csv_content:
            logger.warning('Notion import: the database returned no rows')
            return {'success': True, 'created': 0, 'updated': 0, 'skipped': 0,
                    'unchanged': 0, 'blank': 0, 'total': 0, 'errors': []}

        importer = CsvImporter(
            csv_content=csv_content,
            filename=f'notion_import_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv',
            uploaded_by=uploaded_by,
        )
        stats = importer.process()

        if not stats.get('success'):
            logger.error('Notion import failed: %s', stats.get('error'))
            return stats

        changed = stats.get('created', 0) + stats.get('updated', 0)
        logger.info(
            'Notion import done: %s created, %s updated, %s skipped '
            '(%s blank, %s unchanged), %s errors',
            stats.get('created', 0), stats.get('updated', 0), stats.get('skipped', 0),
            stats.get('blank', 0), stats.get('unchanged', 0),
            len(stats.get('errors') or []),
        )

        if changed:
            _invalidate_public_pages()
        else:
            logger.info('Notion import changed nothing; caches left as-is')
        return stats

    except NotionAPIError as e:
        logger.error('Notion import failed: %s', e)
        return {'success': False, 'error': str(e), 'errors': []}
    except Exception as e:  # noqa: BLE001 - a scheduled job must not crash the worker
        logger.exception('Notion import failed')
        return {'success': False, 'error': str(e), 'errors': []}


def _invalidate_public_pages():
    """Drop the cheap public page caches so imported rows are visible.

    Deliberately not ``invalidate_all_public_cache()``: that also bumps the
    dashboard generation, and re-warming every analyst dashboard is exactly the
    cost the weekly recalculation exists to absorb once, not the daily import.
    """
    from .neon_cache import invalidate_main_cache, invalidate_blog_cache, invalidate_wall_cache

    for name, invalidate in (
        ('main', invalidate_main_cache),
        ('blog', invalidate_blog_cache),
        ('wall', invalidate_wall_cache),
    ):
        try:
            invalidate()
        except Exception as e:  # noqa: BLE001
            logger.warning('Could not invalidate %s cache after Notion import: %s', name, e)
