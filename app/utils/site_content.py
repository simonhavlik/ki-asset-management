"""Editable public content and centrally refreshed market quotes."""
import math
from datetime import datetime, timezone
from ..models import SystemSettings

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
        quotes.append({'symbol': symbol, 'label': label, 'price': price,
                       'change_pct': (price / previous - 1) * 100,
                       'display_value': f'{price:.2f}%' if symbol == '^TNX' else
                                        f'{price:.4f}' if symbol == 'EURUSD=X' else None})
    if len(quotes) < 6:
        raise RuntimeError('Market provider did not return enough valid quotes; snapshot retained')
    payload = {'quotes': quotes, 'as_of': datetime.now(timezone.utc).isoformat(),
               'source': 'Yahoo Finance'}
    SystemSettings.set('site_market_tape', payload, value_type='json')
    return {'quotes': len(quotes), 'as_of': payload['as_of']}
