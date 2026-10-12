"""The autonomous jobs must be scheduled at the right wall-clock times, and must
run inside a Flask application context.

Two regressions this guards against:

* APScheduler runs each job in its own thread, which does not inherit the app
  context, so an enabled automated recalculation fired and immediately failed
  with "Working outside of application context".
* The daily Notion import had no schedule at all - it only ran by hand.
"""

from datetime import datetime

import pytz
import pytest

from app import create_app
from app.extensions import db

# 2026-10-12 is a Monday; pick 00:00 local so "today's" 04:00 is still ahead.
MONDAY_MIDNIGHT = pytz.timezone('Europe/Prague').localize(datetime(2026, 10, 12, 0, 0))


@pytest.fixture()
def app():
    application = create_app()
    with application.app_context():
        db.create_all()
        yield application


def _enable_monday_4am():
    from app.models import SystemSettings
    SystemSettings.set('auto_recalc_enabled', True, 'boolean')
    SystemSettings.set('auto_recalc_day', 'mon', 'string')
    SystemSettings.set('auto_recalc_hour', 4, 'integer')
    SystemSettings.set('auto_recalc_minute', 0, 'integer')


def test_defaults_are_monday_4am(app):
    from app.models import SystemSettings
    import app.scheduler as sched

    with app.app_context():
        SystemSettings.query.delete()
        db.session.commit()
        settings = sched.get_scheduler_settings()

    assert settings['day_of_week'] == 'mon'
    assert settings['hour'] == 4
    assert settings['minute'] == 0


def test_daily_import_runs_every_day_at_4am(app):
    import app.scheduler as sched

    sched.init_scheduler(app)
    daily = sched.scheduler.get_job('daily_notion_import')
    assert daily is not None, 'the daily Notion import must be scheduled'

    nxt = daily.trigger.get_next_fire_time(None, MONDAY_MIDNIGHT)
    assert (nxt.hour, nxt.minute) == (4, 0)
    assert str(daily.trigger.timezone) == 'Europe/Prague'


def test_recalculation_runs_monday_at_4am(app):
    import app.scheduler as sched

    with app.app_context():
        _enable_monday_4am()
    sched.init_scheduler(app)

    weekly = sched.scheduler.get_job('automated_recalc')
    assert weekly is not None, 'the weekly recalculation must be scheduled when enabled'

    nxt = weekly.trigger.get_next_fire_time(None, MONDAY_MIDNIGHT)
    assert nxt.weekday() == 0, 'recalculation must run on Monday'
    assert (nxt.hour, nxt.minute) == (4, 0)


def test_jobs_run_inside_an_app_context(app):
    from flask import has_app_context
    import app.scheduler as sched

    sched._app = app
    seen = {}

    @sched._with_app_context
    def probe():
        seen['ctx'] = has_app_context()

    probe()
    assert seen['ctx'] is True, 'a job without an app context would crash on first db use'


def test_run_notion_import_creates_analyses(app, monkeypatch):
    """End-to-end through the shared import path, with Notion and ticker lookup faked."""
    import app.utils.notion_helper as nh
    import app.utils.csv_import as ci
    from app.models import Analysis
    from app.utils.notion_import import run_notion_import

    csv = (
        'Company,Date,Sector,Analyst,Opponent,Comment,Status,Files & media\n'
        'Notion Test Co,2026-10-01,Technology,analyst@example.com,,,On Watchlist,\n'
    )

    class FakeClient:
        def __init__(self, api_key):
            self.api_key = api_key

        def get_database_properties(self, database_id):
            return {'Name': {'type': 'title'}, 'Date': {'type': 'date'},
                    'Sector': {'type': 'rich_text'}, 'Analyst': {'type': 'people'},
                    'Comment': {'type': 'rich_text'}, 'Status': {'type': 'select'}}

        def export_database_as_csv(self, database_id, column_mapping):
            return csv

    monkeypatch.setattr(nh, 'NotionClient', FakeClient)
    # Keep it hermetic: no DeepSeek/Brave/Yahoo calls for the new company.
    monkeypatch.setattr(ci, 'is_other_event', lambda name: True)
    monkeypatch.setenv('NOTION_API_KEY', 'test-key')
    monkeypatch.setenv('NOTION_DATABASE_ID', 'test-db-id')

    with app.app_context():
        before = Analysis.query.count()
        stats = run_notion_import()

    assert stats['success'] is True
    assert stats['created'] == 1
    with app.app_context():
        assert Analysis.query.count() == before + 1
