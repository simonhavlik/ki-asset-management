"""Editable public content and centrally refreshed market quotes."""
import logging
import math
from datetime import datetime, timezone
from ..models import SystemSettings

logger = logging.getLogger(__name__)

DEFAULT_PARTNERS = [
    {'name': 'PwC', 'logo': '/static/images/partners/pwc.svg', 'website': ''},
    {'name': 'J&T Banka', 'logo': '/static/images/partners/jt.png', 'website': ''},
    {'name': 'Pale Fire Capital', 'logo': '/static/images/partners/palefire.jpg', 'website': ''},
    {'name': 'INVESTIKA', 'logo': '/static/images/partners/investika.png', 'website': ''},
    {'name': 'Erste Asset Management', 'logo': '/static/images/partners/erste.png', 'website': ''},
]
MARKETS = [('^GSPC', 'S&P 500'), ('^IXIC', 'NASDAQ'), ('^DJI', 'DOW'),
           ('^VIX', 'VIX'), ('^GDAXI', 'DAX'), ('^FTSE', 'FTSE'),
           ('^N225', 'NIKKEI'), ('GC=F', 'GOLD'), ('BZ=F', 'BRENT'),
           ('BTC-USD', 'BTC'), ('EURUSD=X', 'EUR/USD'), ('^TNX', 'US 10Y')]

# The upstream quote provider rejects bursts and rate-limits datacenter egress; a
# failed 15-minute refresh with a recent snapshot is routine, so it is logged and
# skipped instead of being recorded as a job failure (which pages Simon every 2h).
# Only a snapshot older than this is a real incident worth an alert.
MARKET_STALE_ALERT_HOURS = 24


def get_partners():
    value = SystemSettings.get('site_partners', None)
    return value if isinstance(value, list) else DEFAULT_PARTNERS


def get_market_tape():
    """Read only. A missing quote snapshot must never cause a provider request."""
    payload = SystemSettings.get('site_market_tape', {}) or {}
    if payload.get('as_of'):
        from zoneinfo import ZoneInfo
        try:
            payload['display_as_of'] = datetime.fromisoformat(payload['as_of']).astimezone(
                ZoneInfo('Europe/Prague')).strftime('%d.%m. %H:%M %Z')
        except (ValueError, TypeError):
            payload['display_as_of'] = payload['as_of']
    return payload


def _quote_payload(symbol, label, price, previous):
    return {'symbol': symbol, 'label': label, 'price': price,
            'change_pct': (price / previous - 1) * 100,
            'display_value': f'{price:.2f}%' if symbol == '^TNX' else
                             f'{price:.4f}' if symbol == 'EURUSD=X' else None}


def _chart_quotes():
    """Fallback: Yahoo's chart endpoint, one symbol per request.

    The batch client (yahooquery) is refused outright from some datacenter egress
    ranges; the chart endpoint uses no crumb/cookie handshake and usually answers
    where the batch call does not. Returns nothing on any failure - the caller
    decides whether the gap matters.
    """
    import json
    import urllib.parse
    import urllib.request
    quotes = []
    for symbol, label in MARKETS:
        url = ('https://query1.finance.yahoo.com/v8/finance/chart/'
               f'{urllib.parse.quote(symbol)}?range=5d&interval=1d')
        request = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; VerxlMarketTape/1.0)', 'Accept': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                chart = json.load(response)['chart']['result'][0]['meta']
            price = float(chart['regularMarketPrice'])
            previous = float(chart.get('chartPreviousClose') or chart.get('previousClose'))
            if all(math.isfinite(x) and x > 0 for x in (price, previous)):
                quotes.append(_quote_payload(symbol, label, price, previous))
        except Exception as exc:  # noqa: BLE001 - one symbol failing must not stop the rest
            logger.debug('chart quote failed for %s: %s', symbol, exc)
    return quotes


def refresh_market_tape():
    """Scheduler only: publish timestamped daily moves, retaining old data on failure."""
    from yahooquery import Ticker
    prices = Ticker(' '.join(symbol for symbol, _ in MARKETS), asynchronous=True,
                    max_workers=3, timeout=5, retry=0).price
    quotes = []
    for symbol, label in MARKETS:
        item = prices.get(symbol, {}) if isinstance(prices, dict) else {}
        if not isinstance(item, dict):
            continue
        try:
            price = float(item['regularMarketPrice'])
            previous = float(item['regularMarketPreviousClose'])
            if not all(math.isfinite(x) and x > 0 for x in (price, previous)):
                continue
        except (KeyError, TypeError, ValueError):
            continue
        quotes.append(_quote_payload(symbol, label, price, previous))
    if len(quotes) < 6:
        quotes = _chart_quotes()
        if len(quotes) >= 6:
            logger.info('Market tape served by the chart fallback (%s quotes)', len(quotes))
    if len(quotes) < 6:
        previous = get_market_tape()
        age_h = None
        try:
            as_of = datetime.fromisoformat(previous['as_of'])
            if as_of.tzinfo is None:
                as_of = as_of.replace(tzinfo=timezone.utc)
            age_h = (datetime.now(timezone.utc) - as_of).total_seconds() / 3600
        except (KeyError, TypeError, ValueError):
            age_h = None
        if age_h is not None and age_h < MARKET_STALE_ALERT_HOURS:
            # Transient upstream refusal: the published snapshot stands, so this is
            # a skip rather than a failed run. The health check only pages once the
            # snapshot itself is stale.
            logger.info('Market quote refresh returned %s/12 quotes; keeping snapshot '
                        'from %.1fh ago', len(quotes), age_h)
            return {'quotes': 0, 'skipped': 'upstream',
                    'received': len(quotes), 'snapshot_age_hours': round(age_h, 1)}
        raise RuntimeError(f'Market provider did not return enough valid quotes '
                           f'({len(quotes)}/12); snapshot retained')
    payload = {'quotes': quotes, 'as_of': datetime.now(timezone.utc).isoformat(),
               'source': 'Yahoo Finance'}
    SystemSettings.set('site_market_tape', payload, value_type='json')
    return {'quotes': len(quotes), 'as_of': payload['as_of']}


def get_public_portfolio_mode():
    """Unknown/missing settings always use the established approved portfolio."""
    mode = SystemSettings.get('site_public_portfolio_mode', 'approved')
    return mode if mode in ('approved', 'purchased') else 'approved'
