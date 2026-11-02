"""Results must describe the same analyses in totals, bars, series and rows."""
from datetime import date, timedelta
import json
import re
from uuid import uuid4

from flask import template_rendered
import pytest

from app import create_app
from app.extensions import db
from app.models import (Analysis, Company, CompanyTickerMapping,
                        PerformanceCalculation, User, analysis_analysts)
from app.utils.performance import PerformanceCalculator


@pytest.fixture()
def results_case():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        tag = uuid4().hex
        user = User(email=f'results-{tag}@example.com', full_name='Results analyst', is_admin=True)
        other = User(email=f'results-other-{tag}@example.com')
        db.session.add_all([user, other])
        db.session.flush()
        companies, analyses = [], []

        def add(name, status, value, *, role='analyst', owner=None, future=False,
                is_other=False, company=None):
            if company is None:
                company = Company(name=f'{name} {tag}', ticker_symbol='TEST')
                db.session.add(company)
                db.session.flush()
                companies.append(company)
            analysis = Analysis(company_id=company.id, status=status,
                                analysis_date=date.today() + timedelta(days=10) if future
                                else date.today() - timedelta(days=730 + len(analyses)))
            db.session.add(analysis)
            db.session.flush()
            analyses.append(analysis)
            db.session.execute(analysis_analysts.insert().values(
                analysis_id=analysis.id, user_id=(owner or user).id, role=role))
            if value is not None:
                db.session.add(PerformanceCalculation(
                    analysis_id=analysis.id, calculation_date=date.today(),
                    price_at_analysis=100, price_current=100 + value, return_pct=value))
            if is_other:
                db.session.add(CompanyTickerMapping(company_name=company.name, is_other_event=True))
            return analysis

        watchlist = add("Analyst's watchlist", 'On Watchlist', 25)
        # An old calculation must not add a row or affect the average.
        db.session.add(PerformanceCalculation(
            analysis_id=watchlist.id, calculation_date=date.today()-timedelta(days=1),
            price_at_analysis=100, price_current=199, return_pct=99))
        portfolio = add('Bought company', 'Portfolio', 30)
        repeat = add('Repeat', 'Portfolio', 0, company=watchlist.company)
        neutral = add('Neutral company', 'Neutral', -5)
        refused = add('Refused company', 'Refused', -20)
        add('Other event', 'Portfolio', 999, is_other=True)
        add('Future company', 'Portfolio', 500, future=True)
        add('Non-stock status', 'Other', 100)
        add('Missing calculation', 'Portfolio', None)
        add('Opponent only', 'Portfolio', 100, role='opponent')
        add('Different analyst', 'Portfolio', 100, owner=other)
        db.session.commit()
        yield app, user, {
            'approved_only': [watchlist.id, portfolio.id, repeat.id],
            'neutral_approved': [watchlist.id, portfolio.id, repeat.id, neutral.id],
            'all_stock': [watchlist.id, portfolio.id, repeat.id, neutral.id, refused.id],
        }
        ids = [a.id for a in analyses]
        db.session.execute(analysis_analysts.delete().where(analysis_analysts.c.analysis_id.in_(ids)))
        PerformanceCalculation.query.filter(PerformanceCalculation.analysis_id.in_(ids)).delete(synchronize_session=False)
        Analysis.query.filter(Analysis.id.in_(ids)).delete(synchronize_session=False)
        CompanyTickerMapping.query.filter(CompanyTickerMapping.company_name.in_([c.name for c in companies])).delete(synchronize_session=False)
        Company.query.filter(Company.id.in_([c.id for c in companies])).delete(synchronize_session=False)
        User.query.filter(User.id.in_([user.id, other.id])).delete(synchronize_session=False)
        db.session.commit()


@pytest.mark.parametrize('selection', ['approved_only', 'neutral_approved', 'all_stock'])
@pytest.mark.parametrize('annualized', [False, True])
def test_results_summary_list_bars_and_both_series_agree(results_case, monkeypatch, selection, annualized):
    app, user, expected = results_case
    calculator = PerformanceCalculator()
    rows = calculator.get_analyst_analysis_performance(user.id, selection)
    assert {a.id for a, p, c in rows} == set(expected[selection])
    summary = calculator.get_analyst_performance(user.id, selection, annualized)
    assert summary['num_analyses'] == len(rows)
    expected_returns = [calculator.analysis_return(a, p, annualized) for a, p, c in rows]
    assert summary['avg_return'] == round(sum(expected_returns) / len(rows), 2)
    series_inputs = []

    def series(selected, years):
        series_inputs.append((years, [a.id for a, p, c in selected]))
        return None

    monkeypatch.setattr('app.admin.routes._build_analyst_series', series)
    captured = []

    def capture(sender, template, context, **extra):
        captured.append(context)

    client = app.test_client()
    with client.session_transaction() as session:
        session['_user_id'] = str(user.id)
        session['_fresh'] = True
    with template_rendered.connected_to(capture, app):
        response = client.get(f'/admin/analyst/{user.id}', query_string={
            'filter': selection, 'annualized': str(annualized).lower()})
    assert response.status_code == 200
    context = captured[-1]
    ids = [a.id for a, p, c in context['analyses']]
    assert context['analyst'] == dict(analyst_id=user.id, analyst_name=user.full_name, **summary)
    assert series_inputs == [(None, ids), (1, ids)]
    assert set(ids) == set(expected[selection])
    html = response.get_data(as_text=True)
    chart = json.loads(re.search(r'const analysesData = (.*?);', html).group(1))
    assert len(chart) == len(ids) == context['analyst']['num_analyses']
    assert [point['return_pct'] for point in chart] == expected_returns
    assert any("Analyst's watchlist" in point['label'] for point in chart)
    for analysis, perf, company in rows:
        assert f'{context["analysis_returns"][analysis.id]:.2f}%' in html
    assert '0.00%' in html  # zero return is a result, not missing data
    assert f'filter={selection}' in html


def test_leaderboard_detail_links_keep_filter_and_annualization(results_case):
    app, user, expected = results_case
    client = app.test_client()
    with client.session_transaction() as session:
        session['_user_id'] = str(user.id)
        session['_fresh'] = True
    html = client.get('/admin/performance?filter=all_stock&annualized=true').get_data(as_text=True)
    assert f'/admin/analyst/{user.id}?filter=all_stock&amp;annualized=true' in html
    assert PerformanceCalculator().get_analyst_performance(user.id, 'all_stock')['num_analyses'] == 5


def test_no_eligible_analyses_returns_empty_metrics(results_case):
    app, user, expected = results_case
    assert PerformanceCalculator().get_analyst_performance(user.id, 'unknown')['num_analyses'] == 0


def test_fundamentals_batch_snapshot_units_and_failed_refresh_preserves_data(results_case, monkeypatch):
    from app.models import CalculationSnapshot
    from app.utils import company_fundamentals as cf
    app, user, expected = results_case
    calls = []

    class Provider:
        session = None
        def __init__(self, symbols, **options):
            self.symbols = symbols
            assert options['max_workers'] == 2
        def get_modules(self, modules):
            calls.append((self.symbols, modules))
            return {symbol: {
                'price': {'currency': 'USD', 'regularMarketPrice': 125},
                'summaryDetail': {'marketCap': 1000, 'trailingPE': 12, 'dividendYield': .025},
                'defaultKeyStatistics': {'enterpriseToEbitda': 8},
                'financialData': {'financialCurrency': 'USD', 'totalDebt': 90, 'totalCash': 20,
                                  'ebitda': 30, 'freeCashflow': 100, 'debtToEquity': 150,
                                  'grossMargins': .4, 'profitMargins': -.05, 'currentRatio': 0},
                'assetProfile': {'sector': 'Technology', 'companyOfficers': [{'name': 'Ignored'}]},
            } for symbol in self.symbols}

    monkeypatch.setattr('yahooquery.Ticker', Provider)
    result = cf.refresh_fundamentals(force=True)
    assert result['updated'] >= 1 and calls
    assert all(modules == cf.MODULES for symbols, modules in calls)
    company = db.session.get(Analysis, expected['approved_only'][0]).company
    context = cf.fundamentals_context([company, company])
    assert len(context['fundamentals']) == 1
    row = context['fundamentals'][0]
    assert row['values']['debtToEquity'] == '150.0%'
    assert row['values']['grossMargins'] == '40.0%'
    assert row['values']['profitMargins'] == '-5.0%'
    assert row['values']['currentRatio'] == '0.00×'
    assert row['values']['fcfYield'] == '10.0%'
    assert row['numeric']['netDebt'] == 70
    assert row['numeric']['debtToEbitda'] == 3
    snapshot = db.session.get(CalculationSnapshot, cf.PREFIX+'TEST')
    previous = snapshot.payload, snapshot.cached_at

    def no_network(*args, **kwargs):
        raise AssertionError('Page reads must not call Yahoo')

    monkeypatch.setattr('yahooquery.Ticker', no_network)
    assert cf.fundamentals_context([company])['fundamentals_available'] == 1
    assert cf.refresh_fundamentals()['updated'] == 0  # same-day repeated refresh is cheap
    assert cf.refresh_fundamentals(force=True)['failed'] >= 1
    assert (snapshot.payload, snapshot.cached_at) == previous
    CalculationSnapshot.query.filter_by(key=cf.PREFIX+'TEST').delete()
    db.session.commit()


def test_fundamentals_missing_and_mixed_currencies_are_not_invented(results_case, monkeypatch):
    from app.utils import company_fundamentals as cf
    app, user, expected = results_case
    data = cf._values({'price': {'currency': 'USD'}, 'financialData': {
        'financialCurrency': 'EUR', 'freeCashflow': 10, 'totalDebt': 0, 'totalCash': 3,
        'ebitda': -5}, 'summaryDetail': {'marketCap': 100}})
    assert 'fcfYield' not in data  # no EUR / USD calculation without FX
    assert data['netDebt'] == -3
    assert 'debtToEbitda' not in data  # negative EBITDA is not a meaningful debt multiple
    assert cf._number(float('nan')) is None
    assert cf._number({'raw': 0}) == 0
    assert cf._format(None, 'percent', 'USD', 'EUR') == '—'
    company = db.session.get(Analysis, expected['approved_only'][0]).company
    monkeypatch.setattr('yahooquery.Ticker', lambda *a, **k: pytest.fail('A GET called Yahoo'))
    client = app.test_client()
    assert client.get(f'/admin/company/{company.id}/fundamentals').status_code in (302, 401)
    with client.session_transaction() as session:
        session['_user_id'] = str(user.id)
        session['_fresh'] = True
    from flask import g
    g.pop('_login_user', None)
    response = client.get(f'/admin/company/{company.id}/fundamentals')
    assert response.status_code == 200
    assert b'not provided these statistics' in response.data
