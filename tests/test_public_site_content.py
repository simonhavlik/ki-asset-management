"""Public content reads remain cheap; only admins can change partner content."""
import pytest
from app import create_app
from app.extensions import db
from app.models import User, SystemSettings


@pytest.fixture()
def application():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        SystemSettings.query.filter(SystemSettings.key.in_(['site_partners','site_market_tape','site_public_portfolio_mode'])).delete(synchronize_session=False)
        db.session.commit()
        yield app


def login(client, admin):
    from flask import g
    user = User.query.filter_by(email='content-admin@klubinvestoru.com' if admin else 'content-user@klubinvestoru.com').first()
    if user is None:
        user=User(email='content-admin@klubinvestoru.com' if admin else 'content-user@klubinvestoru.com',is_active=True,is_admin=admin)
        db.session.add(user);db.session.commit()
    with client.session_transaction() as session:
        session['_user_id']=str(user.id);session['_fresh']=True
    g.pop('_login_user',None)


def test_partner_edit_requires_admin(application):
    client=application.test_client()
    assert client.get('/admin/site-partners').status_code in (302,401)
    login(client,False)
    assert client.post('/admin/site-partners',data={'partners-0-name':'Unauthorized'}).status_code==302
    assert SystemSettings.get('site_partners') is None


def test_admin_can_replace_and_remove_partners(application):
    client=application.test_client();login(client,True)
    assert client.get('/admin/site-partners').status_code==200
    assert '/admin/site-partners' in client.get('/').get_data(as_text=True)
    response=client.post('/admin/site-partners',data={'partners-0-name':'Example partner','partners-0-website':'https://example.com','partners-0-logo':'https://example.com/logo.png'})
    assert response.status_code==302
    assert SystemSettings.get('site_partners')[0]['name']=='Example partner'
    assert 'Example partner' in client.get('/').get_data(as_text=True)
    assert client.post('/admin/site-partners',data={}).status_code==302
    assert SystemSettings.get('site_partners')==[]


def test_unsafe_links_are_rejected(application):
    client=application.test_client();login(client,True)
    response=client.post('/admin/site-partners',data={'partners-0-name':'Test','partners-0-logo':'javascript:alert(1)','partners-0-website':'https://example.com'})
    assert response.status_code==200
    assert SystemSettings.get('site_partners') is None


def test_public_reads_do_not_fetch_quotes(application,monkeypatch):
    from app.utils.site_content import get_market_tape
    def forbidden(*a,**kw):raise AssertionError('page load fetched live quotes')
    monkeypatch.setattr('yahooquery.Ticker',forbidden)
    assert get_market_tape()=={}
    assert application.test_client().get('/').status_code==200


def test_quote_publication_and_failed_refresh_preserve_snapshot(application,monkeypatch):
    from datetime import datetime,timedelta,timezone
    from app.utils.site_content import (MARKET_STALE_ALERT_HOURS,refresh_market_tape,
                                        get_market_tape,MARKETS)
    class Quotes:
        def __init__(self,*a,**kw):pass
        price={symbol:{'regularMarketPrice':110,'regularMarketPreviousClose':100} for symbol,_ in MARKETS}
    monkeypatch.setattr('yahooquery.Ticker',Quotes)
    monkeypatch.setattr('app.utils.site_content._chart_quotes',lambda:[])
    refresh_market_tape()
    stored=get_market_tape()
    assert stored['quotes'][0]['change_pct']==pytest.approx(10)
    assert stored['as_of'].endswith('+00:00')

    # Provider outage with a fresh snapshot is a skip: the tape keeps serving and
    # the job is not marked failed (a failed run is what pages the health check).
    Quotes.price={}
    assert refresh_market_tape()['skipped']=='upstream'
    assert get_market_tape()==stored

    # Once the published snapshot itself is stale, the outage is a real incident.
    stale=dict(stored)
    stale['as_of']=(datetime.now(timezone.utc)-timedelta(hours=MARKET_STALE_ALERT_HOURS+1)).isoformat()
    SystemSettings.set('site_market_tape',stale,value_type='json')
    with pytest.raises(RuntimeError):refresh_market_tape()
    assert get_market_tape()['as_of']==stale['as_of']


def test_admin_csrf_is_required(application):
    application.config['WTF_CSRF_ENABLED']=True
    client=application.test_client();login(client,True)
    assert client.post('/admin/site-partners',data={'partners-0-name':'Test'}).status_code==400


def test_default_local_logo_addresses_can_be_saved(application):
    from app.utils.site_content import DEFAULT_PARTNERS
    client=application.test_client();login(client,True)
    data={f'partners-{i}-{field}':partner[field] for i,partner in enumerate(DEFAULT_PARTNERS) for field in ('name','logo','website')}
    assert client.post('/admin/site-partners',data=data).status_code==302
    assert len(SystemSettings.get('site_partners'))==5


@pytest.mark.parametrize('mode,purchased', [('approved', False), ('purchased', True), ('invalid', False)])
def test_homepage_selects_one_published_portfolio(application, monkeypatch, mode, purchased):
    from app.main import routes
    from app.utils import neon_cache as nc
    SystemSettings.set('site_public_portfolio_mode', mode)
    monkeypatch.setattr(routes, 'get_dashboard_stats', lambda **kw: pytest.fail('GET calculated'))
    monkeypatch.setattr(nc, 'get_cached_main_stats', lambda: {'source': 'approved'})
    monkeypatch.setattr(nc, 'get_cached_purchased_main_stats', lambda: {'source': 'purchased'})
    calls = []
    monkeypatch.setattr(nc, 'get_cached_board_portfolio_series', lambda **kw: calls.append(kw) or {'source': purchased})
    captured = {}
    monkeypatch.setattr(routes, 'render_template', lambda template, **kw: captured.update(kw) or 'ok')
    assert application.test_client().get('/').status_code == 200
    assert captured['stats']['source'] == ('purchased' if purchased else 'approved')
    assert calls == [{'purchased_only': purchased, 'years': None}]


def test_public_portfolio_change_is_admin_only_validated_and_never_calculates(application, monkeypatch):
    from app.main import routes
    from app.models import CalculationSnapshot
    monkeypatch.setattr(routes, 'get_dashboard_stats', lambda **kw: pytest.fail('switch calculated'))
    client = application.test_client()
    assert client.post('/admin/board/public-portfolio', data={'mode': 'purchased'}).status_code in (302, 401)
    login(client, False)
    assert client.post('/admin/board/public-portfolio', data={'mode': 'purchased'}).status_code == 302
    assert SystemSettings.get('site_public_portfolio_mode') is None
    login(client, True)
    assert client.post('/admin/board/public-portfolio', data={'mode': 'invalid'}).status_code == 400
    CalculationSnapshot.query.filter_by(key='get_cached_purchased_main_stats:{}').delete()
    db.session.commit()
    assert client.post('/admin/board/public-portfolio', data={'mode': 'purchased'}).status_code == 302
    assert SystemSettings.get('site_public_portfolio_mode') is None
    db.session.add(CalculationSnapshot(key='get_cached_purchased_main_stats:{}', payload='{}'))
    db.session.commit()
    assert client.post('/admin/board/public-portfolio', data={'mode': 'purchased'}).status_code == 302
    assert SystemSettings.get('site_public_portfolio_mode') == 'purchased'
    assert client.post('/admin/board/public-portfolio', data={'mode': 'approved'}).status_code == 302
    assert SystemSettings.get('site_public_portfolio_mode') == 'approved'
    application.config['WTF_CSRF_ENABLED'] = True
    assert client.post('/admin/board/public-portfolio', data={'mode': 'approved'}).status_code == 400


def test_purchased_metrics_are_published_once_then_read_only(application, monkeypatch):
    from app.main import routes
    from app.utils.neon_cache import get_cached_purchased_main_stats
    from app.models import CalculationSnapshot
    CalculationSnapshot.query.filter_by(key='get_cached_purchased_main_stats:{}').delete()
    db.session.commit()
    calls = []
    monkeypatch.setattr(routes, 'get_dashboard_stats', lambda **kw: calls.append(kw) or {'portfolio_return': 12.5})
    assert get_cached_purchased_main_stats()['portfolio_return'] is None
    assert calls == []
    published = get_cached_purchased_main_stats(force_refresh=True)
    assert get_cached_purchased_main_stats() == published
    assert calls == [{'purchased_only': True}]
