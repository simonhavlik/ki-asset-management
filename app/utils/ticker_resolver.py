"""
Robust ticker resolver with caching and "Other" event detection.

This module provides intelligent ticker resolution with the following features:
1. Cache layer - stores resolved tickers to avoid repeated API calls
2. "Other" detection - identifies non-stock events (market commentary, etc.)
3. Multiple source fallback - AI, web search, Yahoo Finance API
4. Manual override support - admin can set ticker mappings
"""

import logging
import re
from typing import Optional, Tuple
from datetime import datetime
from ..extensions import db
from ..models import CompanyTickerMapping

logger = logging.getLogger(__name__)

# Keywords that indicate this is NOT a stock analysis
OTHER_EVENT_KEYWORDS = [
    'market commentary', 'market outlook', 'macro', 'economy', 'fed', 'federal reserve',
    'interest rates', 'inflation', 'recession', 'gdp', 'trade war', 'brexit',
    'portfolio', 'cash position', 'sector', 'industry', 'overview', 'summary',
    'technical analysis', 'chart', 'support', 'resistance', 'trend',
    'crypto', 'bitcoin', 'ethereum', 'blockchain',
    'general meeting', 'board meeting', 'quarterly review'
]

# Keywords that strongly suggest a specific company
COMPANY_INDICATORS = [
    'inc', 'corp', 'corporation', 'ltd', 'limited', 'plc', 'ag', 'se',
    'company', 'co.', 'group', 'holding', 'holdings'
]


def is_other_event(company_name: str) -> bool:
    """
    Detect if this is a non-stock "Other" event (market commentary, macro, etc.)
    
    Args:
        company_name: The name from the CSV/analysis
        
    Returns:
        True if this appears to be a non-stock event
    """
    if not company_name:
        return True
        
    name_lower = company_name.lower()
    
    # Check for explicit "Other" marker
    if name_lower.strip() in ['other', 'n/a', 'na', '-', '']:
        return True
    
    # Check for non-stock keywords
    for keyword in OTHER_EVENT_KEYWORDS:
        if keyword in name_lower:
            logger.info(f"Detected 'Other' event for '{company_name}' (matched: {keyword})")
            return True
    
    return False


def get_cached_ticker(company_name: str) -> Tuple[Optional[str], bool]:
    """
    Check if we have a cached ticker mapping for this company.
    
    Args:
        company_name: The company name to look up
        
    Returns:
        Tuple of (ticker_symbol, is_other_event)
        - If ticker_symbol is None and is_other_event is True: this is an "Other" event
        - If ticker_symbol is a string: use this ticker
        - If both are None/False: not found in cache, need to resolve
    """
    if not company_name:
        return None, True
        
    # Normalize the name for lookup
    normalized_name = company_name.strip()
    
    mapping = CompanyTickerMapping.query.filter_by(company_name=normalized_name).first()
    
    if mapping:
        if mapping.is_other_event:
            logger.debug(f"Cache hit: '{company_name}' is marked as 'Other' event")
            return None, True
        elif mapping.ticker_symbol:
            logger.debug(f"Cache hit: '{company_name}' -> {mapping.ticker_symbol}")
            return mapping.ticker_symbol, False
        else:
            # Has entry but no ticker and not marked as Other - treat as unresolved
            logger.debug(f"Cache hit: '{company_name}' has no ticker (unresolved)")
            return None, False
    
    return None, False


def set_cached_ticker(company_name: str, ticker_symbol: Optional[str], 
                      is_other: bool = False, source: str = 'auto') -> None:
    """
    Store a ticker mapping in the cache.
    
    Args:
        company_name: The company name
        ticker_symbol: The ticker symbol (None if not a stock/Other)
        is_other: Whether this is a non-stock "Other" event
        source: Source of the mapping ('manual', 'deepseek', 'brave', 'yahoo', 'admin')
    """
    if not company_name:
        return
        
    normalized_name = company_name.strip()
    
    mapping = CompanyTickerMapping.query.filter_by(company_name=normalized_name).first()
    
    if mapping:
        # Update existing
        mapping.ticker_symbol = ticker_symbol
        mapping.is_other_event = is_other
        mapping.source = source
        mapping.last_updated = datetime.utcnow()
    else:
        # Create new
        mapping = CompanyTickerMapping(
            company_name=normalized_name,
            ticker_symbol=ticker_symbol,
            is_other_event=is_other,
            source=source
        )
        db.session.add(mapping)
    
    db.session.commit()
    
    if is_other:
        logger.info(f"Cached '{company_name}' as 'Other' event (source: {source})")
    elif ticker_symbol:
        logger.info(f"Cached '{company_name}' -> {ticker_symbol} (source: {source})")
    else:
        logger.info(f"Cached '{company_name}' as unresolved (source: {source})")


def resolve_ticker(company_name: str, hint: Optional[str] = None, 
                   force_refresh: bool = False) -> Tuple[Optional[str], bool, str]:
    """
    Resolve a company name to a ticker symbol with caching.
    
    This is the main entry point for ticker resolution. It:
    1. Checks cache first (unless force_refresh=True)
    2. Detects "Other" events automatically
    3. Tries multiple resolution strategies
    4. Validates tickers have price data
    5. Caches results for future use
    
    Args:
        company_name: The company name from CSV/analysis
        hint: Optional hint (sector, notes, etc.)
        force_refresh: If True, ignore cache and re-resolve
        
    Returns:
        Tuple of (ticker_symbol, is_other_event, source)
        - ticker_symbol: The ticker (None if Other or not found)
        - is_other_event: True if this is a non-stock event
        - source: How the ticker was resolved ('cached', 'other_auto', 'deepseek', 
                  'brave', 'yahoo', 'manual', 'not_found')
    """
    if not company_name or company_name.strip() in ['', '-', 'N/A', 'n/a']:
        return None, True, 'other_auto'
    
    # Step 1: Check cache (unless forcing refresh)
    if not force_refresh:
        cached_ticker, is_other = get_cached_ticker(company_name)
        if is_other:
            return None, True, 'cached'
        elif cached_ticker:
            return cached_ticker, False, 'cached'
    
    # Step 2: Auto-detect "Other" events
    if is_other_event(company_name):
        set_cached_ticker(company_name, None, is_other=True, source='other_auto')
        return None, True, 'other_auto'
    
    # Step 3: Try to resolve using multiple sources
    ticker = _resolve_with_fallback(company_name, hint)
    
    if ticker:
        # Validate the ticker has price data
        if _validate_ticker(ticker):
            set_cached_ticker(company_name, ticker, is_other=False, source='yahoo')
            return ticker, False, 'yahoo'
        else:
            logger.warning(f"Resolved ticker {ticker} but no price data available")
    
    # Step 4: Could not resolve - store as unresolved (not Other, just unknown)
    # Don't cache unresolved to allow future retries with better data
    logger.warning(f"Could not resolve ticker for '{company_name}'")
    return None, False, 'not_found'


def _resolve_with_fallback(company_name: str, hint: Optional[str] = None) -> Optional[str]:
    """
    Try multiple strategies to resolve a ticker.
    
    Order of attempts:
    1. DeepSeek AI extraction (if API key available)
    2. Yahoo Finance search
    3. Brave web search
    4. Pattern matching for common formats
    """
    # Try 1: DeepSeek AI extraction
    try:
        from .brave_search import extract_ticker_with_fallback
        ticker, source = extract_ticker_with_fallback(company_name, hint)
        if ticker:
            logger.info(f"Resolved via {source}: '{company_name}' -> {ticker}")
            return ticker
    except Exception as e:
        logger.warning(f"DeepSeek/Brave extraction failed: {e}")
    
    # Try 2: Yahoo Finance direct search
    try:
        from yahooquery import search
        results = search(company_name)
        if results and 'quotes' in results and results['quotes']:
            # Take the first equity result
            for quote in results['quotes']:
                if quote.get('quoteType') == 'EQUITY':
                    ticker = quote.get('symbol')
                    logger.info(f"Resolved via Yahoo search: '{company_name}' -> {ticker}")
                    return ticker
    except Exception as e:
        logger.warning(f"Yahoo search failed: {e}")
    
    # Try 3: Brave web search
    try:
        from .brave_search import search_ticker_via_brave
        ticker = search_ticker_via_brave(company_name, hint)
        if ticker:
            logger.info(f"Resolved via Brave search: '{company_name}' -> {ticker}")
            return ticker
    except Exception as e:
        logger.warning(f"Brave search failed: {e}")
    
    # Try 4: Pattern matching for "Name (TICKER)" format
    pattern_match = re.search(r'\(([A-Z]{1,5})\)$', company_name.strip())
    if pattern_match:
        ticker = pattern_match.group(1)
        logger.info(f"Resolved via pattern: '{company_name}' -> {ticker}")
        return ticker
    
    return None


def _validate_ticker(ticker: str) -> bool:
    """Validate that a ticker has recent price data."""
    from datetime import date, timedelta
    from .yahooquery_helper import fetch_prices
    
    try:
        end_date = date.today()
        start_date = end_date - timedelta(days=7)
        df = fetch_prices(ticker, start_date, end_date)
        return not df.empty
    except Exception as e:
        logger.warning(f"Ticker validation failed for {ticker}: {e}")
        return False


def get_or_create_ticker_mapping(company_name: str) -> CompanyTickerMapping:
    """
    Get existing mapping or create a blank one for admin editing.
    
    This is used by the admin interface to manage ticker mappings.
    """
    mapping = CompanyTickerMapping.query.filter_by(company_name=company_name.strip()).first()
    if not mapping:
        mapping = CompanyTickerMapping(
            company_name=company_name.strip(),
            ticker_symbol=None,
            is_other_event=False,
            source='pending'
        )
        db.session.add(mapping)
        db.session.commit()
    return mapping


def bulk_resolve_tickers(company_names: list, progress_callback=None) -> dict:
    """
    Resolve tickers for multiple companies efficiently.
    
    Args:
        company_names: List of company names to resolve
        progress_callback: Optional function(current, total, name) to report progress
        
    Returns:
        Dict mapping company_name -> {'ticker': str|None, 'is_other': bool, 'source': str}
    """
    results = {}
    total = len(company_names)
    
    for i, name in enumerate(company_names, 1):
        if progress_callback:
            progress_callback(i, total, name)
        
        ticker, is_other, source = resolve_ticker(name)
        results[name] = {
            'ticker': ticker,
            'is_other': is_other,
            'source': source
        }
    
    return results
