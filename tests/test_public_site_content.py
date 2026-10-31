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
        SystemSettings.query.filter(SystemSettings.key.in_(['site_partners','site_market_tape'])).delete(synchronize_session=False)
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


def test_homepage_uses_published_purchased_positions(application, monkeypatch):
    from app.main import routes
    from app.utils import neon_cache

    calls = []
    published = {'dates': ['2026-05-01'], 'portfolio_series': [0]}

    def purchased_series(**kwargs):
        calls.append(kwargs)
        return published

    def forbidden(*args, **kwargs):
        raise AssertionError('Homepage used the legacy analysis simulation')

    context = {}

    def render(template, **values):
        context.update(values)
        return 'ok'

    monkeypatch.setattr(neon_cache, 'get_cached_board_portfolio_series', purchased_series)
    monkeypatch.setattr(neon_cache, 'get_cached_portfolio_chart', forbidden)
    monkeypatch.setattr(routes, 'render_template', render)
    assert application.test_client().get('/').status_code == 200
    assert calls == [{'purchased_only': True, 'years': None}]
    assert context['chart_data'] is published


def test_quote_publication_and_failed_refresh_preserve_snapshot(application,monkeypatch):
    from app.utils.site_content import refresh_market_tape,get_market_tape,MARKETS
    class Quotes:
        def __init__(self,*a,**kw):pass
        price={symbol:{'regularMarketPrice':110,'regularMarketPreviousClose':100} for symbol,_ in MARKETS}
    monkeypatch.setattr('yahooquery.Ticker',Quotes)
    refresh_market_tape()
    stored=get_market_tape()
    assert stored['quotes'][0]['change_pct']==pytest.approx(10)
    assert stored['as_of'].endswith('+00:00')
    Quotes.price={}
    with pytest.raises(RuntimeError):refresh_market_tape()
    assert get_market_tape()==stored


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
