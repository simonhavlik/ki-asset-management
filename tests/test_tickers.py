"""
Ticker lookup tests.

This replaces a script that started with ``import yfinance``. yfinance is not a
dependency any more (the project uses yahooquery), so the module could not be
imported at all and pytest aborted collection.

Network access is opt-in:

    KI_NETWORK_TESTS=1 venv/bin/python -m pytest tests/test_tickers.py
"""

import os

import pytest

from app import create_app

RUN_NETWORK = os.environ.get("KI_NETWORK_TESTS") == "1"


@pytest.fixture()
def app():
    application = create_app()
    with application.app_context():
        yield application


def test_yahooquery_helper_is_the_live_price_source(app):
    """The project fetches prices through yahooquery, not yfinance."""
    from app.utils.yahooquery_helper import fetch_prices

    assert callable(fetch_prices)


def test_yfinance_helper_is_not_used_by_the_app():
    """yfinance_helper imports yfinance, which is not installed; nothing in app/
    may import it, otherwise that code path would fail at runtime."""
    import pathlib
    import re

    app_dir = pathlib.Path(__file__).resolve().parent.parent / "app"
    offenders = []
    for path in app_dir.rglob("*.py"):
        if path.name == "yfinance_helper.py":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r"^\s*(from|import)\s+.*yfinance_helper", text, re.M):
            offenders.append(str(path.relative_to(app_dir)))
    assert not offenders, f"modules still importing yfinance_helper: {offenders}"


@pytest.mark.skipif(not RUN_NETWORK, reason="hits Yahoo Finance; set KI_NETWORK_TESTS=1")
@pytest.mark.parametrize(
    "name,expected",
    [("Apple Inc.", "AAPL"), ("Microsoft Corporation", "MSFT")],
)
def test_known_companies_resolve(app, name, expected):
    from app.utils.ticker_resolver import resolve_ticker

    ticker, _is_other, _source = resolve_ticker(name, force_refresh=True)
    assert ticker == expected
