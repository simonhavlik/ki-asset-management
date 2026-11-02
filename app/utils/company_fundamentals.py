"""Yahoo key statistics, centrally refreshed; page reads never use the network."""
import json
import logging
import math
import re
from datetime import date, datetime, timedelta
from urllib.parse import quote

from ..extensions import db
from ..models import Analysis, CalculationSnapshot, Company, CompanyTickerMapping

logger = logging.getLogger(__name__)
MODULES = ['price', 'summaryDetail', 'defaultKeyStatistics', 'financialData', 'assetProfile']
PREFIX = 'company-fundamentals:'
# key, label, format; percent values from Yahoo are fractions except debtToEquity.
GROUPS = {
    'valuation': [
        ('marketCap', 'Market cap', 'money_quote'), ('enterpriseValue', 'Enterprise value', 'money_quote'),
        ('trailingPE', 'P/E · TTM', 'ratio'), ('forwardPE', 'P/E · forward', 'ratio'),
        ('pegRatio', 'PEG', 'ratio'), ('trailingPegRatio', 'PEG · trailing', 'ratio'),
        ('priceToSalesTrailing12Months', 'P/S · TTM', 'ratio'), ('priceToBook', 'P/B', 'ratio'),
        ('enterpriseToRevenue', 'EV / revenue', 'ratio'), ('enterpriseToEbitda', 'EV / EBITDA', 'ratio'),
        ('fcfYield', 'FCF yield', 'percent'), ('trailingEps', 'EPS · TTM', 'quote'),
        ('forwardEps', 'EPS · forward', 'quote'), ('bookValue', 'Book value / share', 'quote'),
    ],
    'debt': [
        ('totalDebt', 'Total debt', 'money_financial'), ('totalCash', 'Cash', 'money_financial'),
        ('netDebt', 'Net debt', 'money_financial'), ('debtToEquity', 'Debt / equity', 'percent_points'),
        ('debtToEbitda', 'Debt / EBITDA', 'ratio'), ('currentRatio', 'Current ratio', 'ratio'),
        ('quickRatio', 'Quick ratio', 'ratio'), ('totalCashPerShare', 'Cash / share', 'financial'),
    ],
    'profitability': [
        ('grossMargins', 'Gross margin', 'percent'), ('operatingMargins', 'Operating margin', 'percent'),
        ('ebitdaMargins', 'EBITDA margin', 'percent'), ('profitMargins', 'Net margin', 'percent'),
        ('returnOnAssets', 'ROA', 'percent'), ('returnOnEquity', 'ROE', 'percent'),
        ('totalRevenue', 'Revenue · TTM', 'money_financial'), ('ebitda', 'EBITDA · TTM', 'money_financial'),
        ('netIncomeToCommon', 'Net income · TTM', 'money_financial'),
        ('operatingCashflow', 'Operating cash flow · TTM', 'money_financial'),
        ('freeCashflow', 'Free cash flow · TTM', 'money_financial'),
        ('revenuePerShare', 'Revenue / share', 'financial'),
    ],
    'growth': [
        ('revenueGrowth', 'Revenue growth · YoY', 'percent'), ('earningsGrowth', 'Earnings growth · YoY', 'percent'),
        ('earningsQuarterlyGrowth', 'Quarterly earnings growth · YoY', 'percent'),
        ('targetLowPrice', 'Target · low', 'quote'), ('targetMeanPrice', 'Target · mean', 'quote'),
        ('targetHighPrice', 'Target · high', 'quote'), ('numberOfAnalystOpinions', 'Analyst estimates', 'integer'),
        ('recommendationMean', 'Recommendation · 1–5', 'number'),
    ],
    'trading': [
        ('regularMarketPrice', 'Price', 'quote'), ('beta', 'Beta', 'number'),
        ('fiftyTwoWeekLow', '52-week low', 'quote'), ('fiftyTwoWeekHigh', '52-week high', 'quote'),
        ('52WeekChange', '52-week change', 'percent'), ('fiftyDayAverage', '50-day average', 'quote'),
        ('twoHundredDayAverage', '200-day average', 'quote'), ('averageVolume', 'Average volume', 'integer'),
        ('sharesOutstanding', 'Shares outstanding', 'integer'), ('floatShares', 'Float', 'integer'),
        ('shortRatio', 'Short ratio', 'ratio'), ('shortPercentOfFloat', 'Short / float', 'percent'),
        ('heldPercentInsiders', 'Insider ownership', 'percent'), ('heldPercentInstitutions', 'Institutional ownership', 'percent'),
    ],
    'dividends': [
        ('dividendRate', 'Dividend / share · forward', 'quote'), ('dividendYield', 'Dividend yield · forward', 'percent'),
        ('trailingAnnualDividendYield', 'Dividend yield · trailing', 'percent'),
        ('payoutRatio', 'Payout ratio', 'percent'), ('fiveYearAvgDividendYield', '5-year avg. dividend yield', 'percent_points'),
        ('lastDividendValue', 'Last dividend / share', 'quote'),
    ],
}
COMPARISON = {
    'valuation': ['marketCap', 'trailingPE', 'forwardPE', 'priceToBook', 'priceToSalesTrailing12Months', 'enterpriseToEbitda', 'fcfYield'],
    'debt': ['totalDebt', 'totalCash', 'netDebt', 'debtToEquity', 'debtToEbitda', 'currentRatio', 'quickRatio'],
    'profitability': ['grossMargins', 'operatingMargins', 'profitMargins', 'returnOnEquity', 'returnOnAssets', 'freeCashflow'],
    'growth': ['revenueGrowth', 'earningsGrowth', 'earningsQuarterlyGrowth', 'targetMeanPrice', 'numberOfAnalystOpinions'],
    'trading': ['regularMarketPrice', 'beta', 'fiftyTwoWeekLow', 'fiftyTwoWeekHigh', '52WeekChange', 'shortPercentOfFloat'],
    'dividends': ['dividendYield', 'trailingAnnualDividendYield', 'payoutRatio', 'dividendRate', 'fiveYearAvgDividendYield'],
}
METRICS = {key: (label, kind) for group in GROUPS.values() for key, label, kind in group}


def _number(value):
    if isinstance(value, dict):
        value = value.get('raw')
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def _clean(value):
    if isinstance(value, dict):
        if 'raw' in value:
            return _clean(value['raw'])
        return {str(k): _clean(v) for k, v in value.items() if not isinstance(v, list)}
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value if isinstance(value, (str, int, float, bool)) or value is None else None


def _values(modules):
    values = {}
    for module in ('price', 'summaryDetail', 'defaultKeyStatistics', 'financialData'):
        values.update({key: value for key, value in modules.get(module, {}).items() if value is not None})
    debt, cash, ebitda = (_number(values.get(key)) for key in ('totalDebt', 'totalCash', 'ebitda'))
    if debt is not None and cash is not None:
        values['netDebt'] = debt - cash
    if debt is not None and ebitda is not None and ebitda > 0:
        values['debtToEbitda'] = debt / ebitda
    cap, fcf = (_number(values.get(key)) for key in ('marketCap', 'freeCashflow'))
    if cap and cap > 0 and fcf is not None and values.get('currency') and values.get('currency') == values.get('financialCurrency'):
        values['fcfYield'] = fcf / cap
    return values


def refresh_fundamentals(force=False, progress=None):
    """One get_modules call per batch, one combined HTTP request per symbol.

    All five modules travel together. Batches limit concurrency to two; failures
    keep the previous successful snapshot. Runs only from explicit/scheduled work.
    """
    from yahooquery import Ticker
    from .performance import PerformanceCalculator
    other = db.session.query(CompanyTickerMapping.id).filter(
        CompanyTickerMapping.company_name == Company.name,
        CompanyTickerMapping.is_other_event.is_(True)).exists()
    tickers = sorted({c.ticker_symbol.strip().upper() for c in Company.query.join(Analysis).filter(
        Analysis.status.in_(PerformanceCalculator.STATUS_CATEGORIES['all_stock']),
        Analysis.analysis_date <= date.today(), Company.ticker_symbol.isnot(None), ~other).all()
        if c.ticker_symbol and re.fullmatch(r'[A-Za-z0-9.^=\-]+', c.ticker_symbol.strip())})
    cutoff = datetime.utcnow() - timedelta(days=1)
    saved = {r.key: r for r in CalculationSnapshot.query.filter(CalculationSnapshot.key.in_([PREFIX+t for t in tickers])).all()}
    pending = [t for t in tickers if force or PREFIX+t not in saved or saved[PREFIX+t].cached_at < cutoff]
    stats = dict(updated=0, failed=0, fresh=len(tickers)-len(pending), total=len(tickers))
    db.session.commit()  # release the DB connection before network I/O
    for offset in range(0, len(pending), 10):
        batch = pending[offset:offset+10]
        client = None
        try:
            client = Ticker(batch, asynchronous=True, max_workers=2, timeout=10, retry=1)
            response = client.get_modules(MODULES)
        except Exception:
            logger.warning('Yahoo fundamental batch unavailable', exc_info=True)
            response = {}
        finally:
            if client is not None and getattr(client, 'session', None):
                client.session.close()
        for ticker in batch:
            data = response.get(ticker) if isinstance(response, dict) else None
            modules = {key: _clean(data[key]) for key in MODULES if isinstance(data, dict) and isinstance(data.get(key), dict)}
            values = _values(modules)
            if not any(_number(values.get(key)) is not None for key in METRICS):
                stats['failed'] += 1
                continue
            row = db.session.get(CalculationSnapshot, PREFIX+ticker)
            if row is None:
                row = CalculationSnapshot(key=PREFIX+ticker)
                db.session.add(row)
            row.payload = json.dumps({'ticker': ticker, 'modules': modules}, allow_nan=False)
            row.cached_at = datetime.utcnow()
            stats['updated'] += 1
        db.session.commit()
        if progress:
            progress(f"Yahoo fundamentals: {stats['updated']} refreshed, {stats['failed']} unavailable")
    return stats


def _format(value, kind, quote_currency, financial_currency):
    number = _number(value)
    if number is None:
        return '—'
    currency = financial_currency if kind in ('money_financial', 'financial') else quote_currency
    if kind == 'percent':
        return f'{number*100:,.1f}%'
    if kind == 'percent_points':
        return f'{number:,.1f}%'
    if kind.startswith('money_'):
        scale, suffix = next(((scale, suffix) for scale, suffix in [(1e12, 'T'), (1e9, 'B'), (1e6, 'M'), (1e3, 'K')] if abs(number) >= scale), (1, ''))
        return f'{number/scale:,.2f}{suffix} {currency or ""}'.strip()
    if kind in ('quote', 'financial'):
        return f'{number:,.2f} {currency or ""}'.strip()
    if kind == 'integer':
        return f'{number:,.0f}'
    return f'{number:,.2f}' + ('×' if kind == 'ratio' else '')


def fundamentals_context(companies):
    """A single DB read; cache misses stay misses, never trigger Yahoo calls."""
    companies = sorted({c.id: c for c in companies}.values(), key=lambda c: c.name.lower())
    keys = {PREFIX+c.ticker_symbol.strip().upper() for c in companies if c.ticker_symbol}
    snapshots = {r.key: r for r in CalculationSnapshot.query.filter(CalculationSnapshot.key.in_(keys)).all()} if keys else {}
    rows = []
    for company in companies:
        ticker = (company.ticker_symbol or '').strip().upper()
        snapshot = snapshots.get(PREFIX+ticker)
        try:
            payload = json.loads(snapshot.payload) if snapshot else {}
        except (ValueError, TypeError):
            payload = {}
        modules = payload.get('modules', {}) if payload.get('ticker') == ticker else {}
        values = _values(modules)
        quote_currency, financial_currency = values.get('currency'), values.get('financialCurrency')
        formatted = {key: _format(values.get(key), kind, quote_currency, financial_currency) for key, (label, kind) in METRICS.items()}
        raw_groups = {module: [(key, str(value)) for key, value in data.items()
                              if value is not None and isinstance(value, (str, int, float, bool))]
                      for module, data in modules.items() if module != 'assetProfile'}
        rows.append(dict(company=company, ticker=ticker, values=formatted,
                         numeric={key: _number(values.get(key)) for key in METRICS},
                         cached_at=snapshot.cached_at if snapshot and modules else None,
                         stale=bool(snapshot and snapshot.cached_at < datetime.utcnow()-timedelta(days=8)),
                         financial_currency=financial_currency, quote_currency=quote_currency,
                         sector=modules.get('assetProfile', {}).get('sector') or company.sector,
                         groups=raw_groups,
                         yahoo_url='https://finance.yahoo.com/quote/'+quote(ticker, safe='')+'/key-statistics/' if ticker else None))
    return dict(fundamentals=rows, metric_groups=GROUPS, metric_columns=COMPARISON,
                metric_definitions=METRICS, fundamentals_available=sum(bool(r['cached_at']) for r in rows))
