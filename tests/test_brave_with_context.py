"""
Ticker resolution for companies that are missing one.

This replaces a version that imported ``app.utils.yfinance_helper``. That module
does a top-level ``import yfinance``, but yfinance is no longer a dependency (the
project uses yahooquery), so the file could not even be imported and pytest
aborted collection. The live code path is ``app.utils.ticker_resolver``.

Network access is opt-in:

    KI_NETWORK_TESTS=1 venv/bin/python -m pytest tests/test_brave_with_context.py
"""

import os

import pytest

from app import create_app
from app.extensions import db
from app.models import Company

RUN_NETWORK = os.environ.get("KI_NETWORK_TESTS") == "1"


@pytest.fixture()
def app():
    application = create_app()
    with application.app_context():
        yield application


def test_resolver_importable_without_yfinance(app):
    """The real resolver must import with only the declared dependencies."""
    from app.utils.ticker_resolver import resolve_ticker, is_other_event

    assert callable(resolve_ticker)
    assert callable(is_other_event)


def test_is_other_event_flags_non_stocks(app):
    from app.utils.ticker_resolver import is_other_event

    assert is_other_event("Portfolio Management") is True
    assert is_other_event("Market outlook") is True
    assert is_other_event("") is True
    assert is_other_event("Apple Inc.") is False


@pytest.mark.skipif(not RUN_NETWORK, reason="hits Yahoo/DeepSeek; set KI_NETWORK_TESTS=1")
def test_missing_ticker_is_resolved(app):
    from app.utils.ticker_resolver import resolve_ticker

    ticker, is_other, source = resolve_ticker("Apple Inc.", force_refresh=True)
    assert is_other is False
    assert ticker, f"expected a ticker, got source={source}"


@pytest.mark.skipif(not RUN_NETWORK, reason="hits Yahoo/DeepSeek; set KI_NETWORK_TESTS=1")
def test_unknown_company_resolves_to_none(app):
    from app.utils.ticker_resolver import resolve_ticker

    ticker, is_other, source = resolve_ticker(
        "Zzzqqq Nonexistent Holdings 12345", force_refresh=True
    )
    assert is_other is False
    assert ticker is None
    assert source == "not_found"


@pytest.mark.skipif(not RUN_NETWORK, reason="hits Yahoo/DeepSeek; set KI_NETWORK_TESTS=1")
def test_resolver_rejects_a_hallucinated_ticker(app):
    """The raw AI helper can invent a symbol for a made-up company (observed:
    DeepSeek returned 'ADRS' for 'NonexistentCompanyXYZ12345'). resolve_ticker()
    must reject anything without real price data, so the app never stores a ticker
    it cannot price."""
    from app.utils.ticker_resolver import resolve_ticker

    ticker, _is_other, source = resolve_ticker(
        "NonexistentCompanyXYZ12345", force_refresh=True
    )
    assert ticker is None, f"hallucinated ticker {ticker!r} was accepted"
    assert source == "not_found"


def test_server_side_company_rows_have_the_columns_the_admin_page_needs(app):
    """Regression: /admin/analyst-mappings passed Rows where the template wanted
    AnalystMapping objects, so the page raised 500 on mapping.user."""
    from app.models import AnalystMapping, User

    rows = AnalystMapping.query.join(User, AnalystMapping.user_id == User.id).all()
    for row in rows:
        # This attribute access is what the template does.
        assert hasattr(row, "user")
        assert hasattr(row, "analyst_name")
