"""Shared schedule settings. GET requests only read; saving is explicit."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from apscheduler.triggers.cron import CronTrigger
from ..extensions import db
from ..models import SystemSettings

TIMEZONE = 'Europe/Prague'
DAYS = ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')


def schedule_settings(job):
    prefix = 'auto_' + job
    return {
        'enabled': SystemSettings.get(prefix + '_enabled', job == 'notion'),
        'frequency': SystemSettings.get(prefix + '_frequency', 'daily' if job == 'notion' else 'weekly'),
        'day_of_week': SystemSettings.get(prefix + '_day', 'mon'),
        'hour': SystemSettings.get(prefix + '_hour', 4),
        'minute': SystemSettings.get(prefix + '_minute', 0),
    }


def schedule_trigger(settings):
    return CronTrigger(day_of_week=settings['day_of_week'] if settings.get('frequency', 'weekly') == 'weekly' else '*',
                       hour=settings['hour'], minute=settings['minute'], timezone=TIMEZONE)


def due_slot(settings, now=None):
    now = now or datetime.now(ZoneInfo(TIMEZONE))
    days = ((now.weekday() - DAYS.index(settings['day_of_week'])) % 7
            if settings.get('frequency', 'weekly') == 'weekly' else 0)
    due = (now - timedelta(days=days)).replace(hour=settings['hour'], minute=settings['minute'], second=0, microsecond=0)
    if due > now:
        due -= timedelta(days=7 if settings.get('frequency', 'weekly') == 'weekly' else 1)
    return due


def save_schedule(job, values):
    fields = {'enabled': ('boolean', 'true' if values['enabled'] else 'false'),
              'frequency': ('string', values['frequency']), 'day': ('string', values['day_of_week']),
              'hour': ('integer', str(values['hour'])), 'minute': ('integer', str(values['minute']))}
    for suffix, (kind, value) in fields.items():
        key = 'auto_' + job + '_' + suffix
        row = SystemSettings.query.filter_by(key=key).first()
        if row is None:
            row = SystemSettings(key=key)
            db.session.add(row)
        row.value, row.value_type = value, kind
    db.session.commit()


def next_run(settings):
    if not settings['enabled']:
        return None
    now = datetime.now(ZoneInfo(TIMEZONE))
    return schedule_trigger(settings).get_next_fire_time(None, now)
