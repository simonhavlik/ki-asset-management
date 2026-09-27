"""
Brave Search / ticker-extraction integration tests.

These helpers read ``current_app.config``, so they need an application context -
calling them outside one raises "Working outside of application context", which
is what the previous version of this file did.

They also hit real third-party APIs, so they are opt-in:

    KI_NETWORK_TESTS=1 venv/bin/python -m pytest tests/test_brave_search.py
"""

import os

import pytest

from app import create_app

RUN_NETWORK = os.environ.get("KI_NETWORK_TESTS") == "1"

pytestmark = pytest.mark.skipif(
    not RUN_NETWORK,
    reason="external API test; set KI_NETWORK_TESTS=1 to run",
)


@pytest.fixture()
def app():
    application = create_app()
    with application.app_context():
        yield application


@pytest.mark.skipif(
    not os.environ.get("BRAVE_SEARCH_API_KEY"),
    reason="BRAVE_SEARCH_API_KEY not configured",
)
def test_brave_search_degrades_gracefully(app):
    """Brave is quota-limited (it returns HTTP 429 when the free tier is
    exhausted), so the contract we can rely on is: return a string or None, and
    never raise. Exact ticker values are asserted in test_tickers.py, which goes
    through resolve_ticker() and therefore has DeepSeek/Yahoo fallbacks."""
    from app.utils.brave_search import search_ticker_via_brave

    result = search_ticker_via_brave("Apple")
    assert result is None or isinstance(result, str)


def test_extract_ticker_with_fallback_never_raises(app):
    from app.utils.brave_search import extract_ticker_with_fallback

    # Returns (ticker, source). This raw helper is NOT authoritative: the model
    # can return a plausible-looking symbol for a made-up company, so only the
    # shape is asserted here. resolve_ticker() is what validates against real
    # price data - see test_resolver_rejects_a_hallucinated_ticker.
    ticker, source = extract_ticker_with_fallback("Microsoft")
    assert ticker in (None, "MSFT")
    assert source in (None, "deepseek", "brave")

    hallucinated, _ = extract_ticker_with_fallback("NonexistentCompanyXYZ12345")
    assert hallucinated is None or isinstance(hallucinated, str)
