"""Explicit admin operations, durable history and configurable autonomous work."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import pytest
from app import create_app
from app.extensions import db
from app.models import Company, CompanyTickerMapping, Analysis, MaintenanceRun, RecalculationLog, SystemSettings, User

@pytest.fixture()
def application(monkeypatch):
    app=create_app();app.config.update(TESTING=True,WTF_CSRF_ENABLED=False)
    with app.app_context():
        MaintenanceRun.query.delete();RecalculationLog.query.delete()
        SystemSettings.query.filter(SystemSettings.key.like('auto_%')).delete(synchronize_session=False)
        db.session.commit()
        yield app


def client_for(app, admin=True):
    user=User.query.filter_by(email='maintenance-admin@klubinvestoru.com').first()
    if user is None:
        user=User(email='maintenance-admin@klubinvestoru.com',is_admin=admin,is_active=True)
        db.session.add(user)
    user.is_admin=admin;db.session.commit()
    client=app.test_client()
    with client.session_transaction() as session:session['_user_id']=str(user.id);session['_fresh']=True
    from flask import g
    g.pop('_login_user',None)
    return client


def test_schedule_settings_validate_and_apply_without_restart(application,monkeypatch):
    from app import scheduler
    from app.utils.maintenance import schedule_settings,schedule_trigger
    calls=[];monkeypatch.setattr(scheduler,'update_scheduler_settings',lambda:calls.append(True))
    client=client_for(application)
    data=dict(job='notion',enabled='on',frequency='weekly',day_of_week='sun',hour='3',minute='15')
    assert client.post('/admin/unified-update/settings',data=data).status_code==302
    settings=schedule_settings('notion')
    assert settings==dict(enabled=True,frequency='weekly',day_of_week='sun',hour=3,minute=15)
    next_run=schedule_trigger(settings).get_next_fire_time(None,datetime(2026,10,31,12,tzinfo=ZoneInfo('Europe/Prague')))
    assert next_run.weekday()==6 and next_run.hour==3 and next_run.minute==15
    assert calls==[True]
    for changes in [dict(hour='24'),dict(minute='60'),dict(frequency='hourly'),dict(day_of_week='bad'),dict(job='unknown')]:
        assert client.post('/admin/unified-update/settings',data=dict(data,**changes)).status_code==400
        assert schedule_settings('notion')==settings
    application.config['WTF_CSRF_ENABLED']=True
    assert client.post('/admin/unified-update/settings',data=data).status_code==400


def test_admin_pages_and_mutations_require_admin(application):
    client=client_for(application,False)
    for path in ['/admin/unified-update','/admin/company-tickers','/admin/unified-update/history/notion/1']:
        assert client.get(path).status_code==302
    assert client.post('/admin/unified-update/settings',data={}).status_code==302
    assert SystemSettings.get('auto_notion_frequency') is None


def test_disabled_and_weekly_notion_catchup_respects_schedule(application,monkeypatch):
    from app import scheduler
    from app.utils.maintenance import save_schedule
    calls=[];monkeypatch.setattr(scheduler,'import_notion_daily',lambda:calls.append('import'))
    settings=dict(enabled=False,frequency='weekly',day_of_week='mon',hour=4,minute=0)
    save_schedule('notion',settings);scheduler.notion_import_if_stale();assert calls==[]
    save_schedule('notion',dict(settings,enabled=True))
    from app.utils.maintenance import due_slot
    due=due_slot(dict(settings,enabled=True)).astimezone(ZoneInfo('UTC')).replace(tzinfo=None)
    row=MaintenanceRun(job='notion',run_type='scheduled',status='completed',started_at=due+timedelta(minutes=1))
    db.session.add(row);db.session.commit()
    scheduler.notion_import_if_stale();assert calls==[]
    row.started_at=due-timedelta(days=1);db.session.commit()
    scheduler.notion_import_if_stale();assert calls==['import']


def test_owner_sync_reloads_changed_schedules(application,monkeypatch):
    from app import scheduler
    calls=[];monkeypatch.setattr(scheduler,'_applied_schedule_signature','old')
    monkeypatch.setattr(scheduler,'_app',application)
    monkeypatch.setattr(scheduler,'_register_jobs',lambda app:calls.append(app))
    scheduler._reload_schedule_if_changed()
    assert calls==[application]


def test_import_history_records_failure_unchanged_and_manual_runs(application,monkeypatch):
    from app.utils import notion_import as ni
    monkeypatch.setattr(ni,'_import_notion',lambda user:dict(success=True,created=0,updated=0,unchanged=12))
    ni.run_notion_import(run_type='scheduled')
    monkeypatch.setattr(ni,'_import_notion',lambda user:dict(success=False,error='Provider unavailable'))
    ni.run_notion_import(run_type='manual')
    rows=MaintenanceRun.query.order_by(MaintenanceRun.id).all()
    assert [(r.run_type,r.status) for r in rows]==[('scheduled','completed'),('manual','failed')]
    assert rows[0].details['unchanged']==12 and rows[1].error=='Provider unavailable'
    client=client_for(application)
    html=client.get('/admin/unified-update').get_data(as_text=True)
    assert '/admin/unified-update/history/notion/' in html
    assert client.get('/admin/unified-update/history/notion/'+str(rows[1].id)).status_code==200


def test_recent_scheduled_refresh_requires_acknowledgement(application,monkeypatch):
    from app.utils import full_recalc
    from app.utils import unified_calculator
    monkeypatch.setattr(unified_calculator,'is_calculation_running',lambda:False)
    row=RecalculationLog(run_type='scheduled',status='completed',started_at=datetime.utcnow()-timedelta(hours=2))
    db.session.add(row);db.session.commit()
    calls=[];monkeypatch.setattr(full_recalc,'start_full_recalculation',lambda **kw:(calls.append(kw) or True,'started'))
    client=client_for(application)
    response=client.post('/admin/unified-update/full-recalc')
    assert response.status_code==409 and response.json['recent'] and calls==[]
    assert response.json['last']['run_type']=='scheduled'
    assert client.post('/admin/unified-update/full-recalc',data={'acknowledge_recent':'1'}).status_code==202
    assert calls==[{'run_type':'manual'}]


def test_stored_progress_is_visible_from_another_worker(application,monkeypatch):
    from app.analyst.routes import build_refresh_state
    from app.utils import unified_calculator
    monkeypatch.setattr(unified_calculator,'is_calculation_running',lambda:False)
    db.session.add(RecalculationLog(run_type='scheduled',status='running',started_at=datetime.utcnow(),details={'progress_pct':42,'message':'Publishing','logs':['Ready']}));db.session.commit()
    state=build_refresh_state()
    assert state['running'] and state['progress_pct']==42 and state['logs']==['Ready']


@pytest.mark.parametrize('name',['Example - update','Example – Update','Example—update Q3','ACME Ltd - update'])
def test_update_marker_overrides_sector_and_old_automatic_cache(application,monkeypatch,name):
    from app.utils.ticker_resolver import is_other_event,resolve_ticker
    monkeypatch.setattr('app.utils.ticker_resolver._resolve_with_fallback',lambda *a:pytest.fail('AI should not be called'))
    db.session.add(CompanyTickerMapping(company_name=name,ticker_symbol='OLD',source='yahoo'));db.session.commit()
    assert is_other_event(name,'Technology')
    assert resolve_ticker(name)==(None,True,'other_auto')


def test_manual_analysis_override_is_preserved(application):
    from app.utils.ticker_resolver import resolve_ticker,is_other_event
    name='Manual approved - update'
    db.session.add(CompanyTickerMapping(company_name=name,ticker_symbol='MAN',source='manual',is_other_event=False));db.session.commit()
    assert resolve_ticker(name)==('MAN',False,'cached')
    assert not is_other_event('Updater Software Inc','Technology')


def test_ticker_manager_orders_by_date_and_changes_kind_without_provider(application,monkeypatch):
    monkeypatch.setattr('app.utils.yahooquery_helper.fetch_prices',lambda *a:pytest.fail('Saving a mapping must not fetch prices'))
    companies=[]
    for name,day in [('Chronology old',date(2098,1,1)),('Chronology new',date(2099,1,1))]:
        c=Company(name=name);db.session.add(c);db.session.flush();db.session.add(Analysis(company_id=c.id,analysis_date=day,status='On Watchlist'));companies.append(c)
    db.session.commit();client=client_for(application)
    html=client.get('/admin/company-tickers?q=Chronology').get_data(as_text=True)
    assert html.index('Chronology new')<html.index('Chronology old')
    html=client.get('/admin/company-tickers?q=Chronology&order=oldest').get_data(as_text=True)
    assert html.index('Chronology old')<html.index('Chronology new')
    c=companies[0]
    assert client.post(f'/admin/company-tickers/company/{c.id}/set',data={'ticker_symbol':'abc.l'}).status_code==302
    assert c.ticker_symbol=='ABC.L'
    assert client.post(f'/admin/company-tickers/company/{c.id}/kind',data={'kind':'other'}).status_code==302
    assert c.ticker_symbol is None
    assert client.post(f'/admin/company-tickers/company/{c.id}/kind',data={'kind':'analysis'}).status_code==302
    assert c.ticker_symbol=='ABC.L'
    assert client.post(f'/admin/company-tickers/company/{c.id}/kind',data={'kind':'invalid'}).status_code==400


def test_progress_writer_retains_complete_run_output(application):
    from app.utils.full_recalc import _progress_recorder
    from app.utils.unified_calculator import reset_progress
    row=RecalculationLog(run_type='manual',status='running');db.session.add(row);db.session.commit()
    progress=reset_progress()
    for i in range(70):progress.log('Output '+str(i))
    stop,thread=_progress_recorder(row.id);stop.set();thread.join(timeout=5)
    assert not thread.is_alive()
    db.session.expire_all()
    assert len(db.session.get(RecalculationLog,row.id).details['logs'])==70


def test_new_instance_waits_then_takes_over_scheduler_ownership(application,monkeypatch):
    from app import scheduler
    from types import SimpleNamespace
    calls=[]
    monkeypatch.setattr(scheduler,'SCHEDULER_ROLE','follower')
    monkeypatch.setattr(scheduler,'_app',application)
    monkeypatch.setattr(scheduler,'scheduler',SimpleNamespace(running=True,resume=lambda:calls.append('resume')))
    monkeypatch.setattr(scheduler,'_register_jobs',lambda app:calls.append('register'))
    monkeypatch.setattr(scheduler,'_try_owner_lock',lambda:False)
    assert not scheduler._promote_if_owner_available() and calls==[]
    monkeypatch.setattr(scheduler,'_try_owner_lock',lambda:True)
    assert scheduler._promote_if_owner_available()
    assert calls==['register','resume'] and scheduler.SCHEDULER_ROLE=='owner'
    assert not scheduler._promote_if_owner_available()


def test_parallel_notion_request_does_not_start_second_import(application,monkeypatch):
    from app.utils import notion_import as ni
    monkeypatch.setattr(ni,'_recorded_notion_import',lambda *a:pytest.fail('duplicate import'))
    ni._import_lock.acquire()
    try:assert ni.run_notion_import()['busy']
    finally:ni._import_lock.release()


def test_reclassifying_existing_update_entries_is_reversible_and_respects_manual(application):
    from app.utils.ticker_resolver import classify_update_entries
    automatic=Company(name='Existing auto - update',ticker_symbol='AUTO')
    manual=Company(name='Existing manual - update',ticker_symbol='MANUAL')
    db.session.add_all([automatic,manual]);db.session.flush()
    db.session.add_all([CompanyTickerMapping(company_name=automatic.name,ticker_symbol='AUTO',source='yahoo'),CompanyTickerMapping(company_name=manual.name,ticker_symbol='MANUAL',source='manual')]);db.session.commit()
    changed=classify_update_entries()
    assert automatic.id in changed and manual.id not in changed
    mapping=CompanyTickerMapping.query.filter_by(company_name=automatic.name).one()
    assert mapping.is_other_event and mapping.ticker_symbol=='AUTO' and automatic.ticker_symbol is None
    assert manual.ticker_symbol=='MANUAL'
    assert automatic.id not in classify_update_entries()
