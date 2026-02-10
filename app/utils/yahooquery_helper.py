"""
Yahoo Finance data helper using yahooquery library.

This module provides stock price data fetching using yahooquery, which is
more reliable than yfinance for server/cloud deployments like Render.

Features:
- Direct Yahoo Finance API access (not scraping)
- Better error handling and rate limit management
- Works reliably on Render and other cloud platforms
- Supports all Yahoo Finance markets (US, Europe, Asia, etc.)
- Historical data going back 2+ years

For ticker resolution (company name -> ticker), use ticker_resolver.py instead.
"""

import pandas as pd
from datetime import date, timedelta
import logging
import time
from typing import Optional, Tuple, List, Dict
from ..extensions import db
from ..models import Company, StockPrice, Analysis

logger = logging.getLogger(__name__)


# Backward compatibility - delegate to ticker_resolver
# These functions are kept for compatibility but new code should use ticker_resolver directly

def get_validated_ticker_for_company(company_name: str, hint: Optional[str] = None, 
                                     max_attempts: int = 2) -> Optional[str]:
    """
    Get ticker with caching and validation.
    
    DEPRECATED: Use ticker_resolver.resolve_ticker() instead for new code.
    This function is kept for backward compatibility.
    """
    from .ticker_resolver import resolve_ticker
    ticker, is_other, source = resolve_ticker(company_name, hint)
    return ticker if not is_other else None


def _ticker_has_price_data(ticker: str) -> bool:
    """Check if ticker returns any price data for the last 7 days."""
    from datetime import date, timedelta
    end_date = date.today()
    start_date = end_date - timedelta(days=7)
    df = fetch_prices(ticker, start_date, end_date)
    return not df.empty


def fetch_prices(ticker: str, start_date: date, end_date: date) -> pd.DataFrame:
    """
    Fetch historical prices from Yahoo Finance using yahooquery.
    
    Args:
        ticker: Stock ticker symbol (e.g., 'AAPL', 'MSFT', 'SAP.DE')
        start_date: Start date for historical data
        end_date: End date for historical data
    
    Returns:
        DataFrame with columns: Date, close_price, volume
    """
    from yahooquery import Ticker
    
    max_retries = 3
    base_delay = 1  # seconds - yahooquery is more reliable, shorter delays needed
    
    for attempt in range(max_retries):
        try:
            # yahooquery uses the ticker directly
            t = Ticker(ticker)
            
            # Fetch historical data
            # period='max' gets all available data, we filter by date after
            data = t.history(start=start_date.strftime('%Y-%m-%d'), 
                           end=end_date.strftime('%Y-%m-%d'))
            
            # Check if data is empty or has errors
            if data is None or (isinstance(data, pd.DataFrame) and data.empty):
                logger.warning(f"No data for {ticker} between {start_date} and {end_date}")
                return pd.DataFrame()
            
            # Handle different return types
            if not isinstance(data, pd.DataFrame):
                logger.warning(f"Unexpected data type for {ticker}: {type(data)}")
                return pd.DataFrame()
            
            # Reset index to have Date as column
            # yahooquery returns multi-index with symbol and date
            if isinstance(data.index, pd.MultiIndex):
                data = data.reset_index()
            else:
                data = data.reset_index()
            
            # Ensure we have the required columns
            # yahooquery uses 'close' (lowercase), not 'Close'
            required_cols = ['date', 'close']
            for col in required_cols:
                if col not in data.columns:
                    logger.error(f"Missing column '{col}' in data for {ticker}. Available: {list(data.columns)}")
                    return pd.DataFrame()
            
            # Rename columns to match expected format
            column_map = {
                'date': 'Date',
                'close': 'close_price',
                'volume': 'volume'
            }
            data = data.rename(columns=column_map)
            
            # Select only required columns (volume is optional)
            result_cols = ['Date', 'close_price']
            if 'volume' in data.columns:
                result_cols.append('volume')
            
            data = data[result_cols].copy()
            
            logger.info(f"Fetched {len(data)} price records for {ticker}")
            return data
            
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1}/{max_retries} failed for {ticker}: {e}")
            if attempt == max_retries - 1:
                logger.error(f"All retries exhausted for {ticker}: {e}")
                return pd.DataFrame()
            delay = base_delay * (2 ** attempt)  # exponential backoff
            time.sleep(delay)
    
    return pd.DataFrame()


def fetch_prices_batch(tickers: List[str], start_date: date, end_date: date) -> Dict[str, pd.DataFrame]:
    """
    Fetch historical prices for multiple tickers in ONE API call.
    This is YahooQuery's intended usage and is much faster than sequential calls.
    
    Args:
        tickers: List of stock ticker symbols (e.g., ['AAPL', 'MSFT', 'GOOGL'])
        start_date: Start date for historical data
        end_date: End date for historical data
    
    Returns:
        Dict mapping ticker -> DataFrame with columns: Date, close_price, volume
    """
    from yahooquery import Ticker
    
    if not tickers:
        return {}
    
    # Create space-separated ticker string for YahooQuery
    ticker_str = ' '.join(tickers)
    logger.info(f"Fetching batch prices for {len(tickers)} tickers in one API call")
    
    max_retries = 3
    base_delay = 1
    
    for attempt in range(max_retries):
        try:
            # Fetch all tickers in ONE API call
            t = Ticker(ticker_str)
            data = t.history(start=start_date.strftime('%Y-%m-%d'), 
                           end=end_date.strftime('%Y-%m-%d'))
            
            # Check if data is empty
            if data is None or (isinstance(data, pd.DataFrame) and data.empty):
                logger.warning(f"No data returned for batch of {len(tickers)} tickers")
                return {}
            
            # Process the multi-index DataFrame
            result = {}
            
            if isinstance(data.index, pd.MultiIndex):
                # Multi-ticker response - group by ticker symbol
                data = data.reset_index()
                
                # Group by symbol (ticker)
                if 'symbol' in data.columns:
                    for ticker in tickers:
                        ticker_data = data[data['symbol'] == ticker].copy()
                        if not ticker_data.empty:
                            # Rename columns
                            column_map = {'date': 'Date', 'close': 'close_price', 'volume': 'volume'}
                            ticker_data = ticker_data.rename(columns=column_map)
                            # Select columns
                            cols = ['Date', 'close_price']
                            if 'volume' in ticker_data.columns:
                                cols.append('volume')
                            result[ticker] = ticker_data[cols].copy()
                            logger.info(f"Batch fetch: Got {len(ticker_data)} records for {ticker}")
            else:
                # Single ticker response
                data = data.reset_index()
                if len(tickers) == 1:
                    ticker = tickers[0]
                    column_map = {'date': 'Date', 'close': 'close_price', 'volume': 'volume'}
                    data = data.rename(columns=column_map)
                    cols = ['Date', 'close_price']
                    if 'volume' in data.columns:
                        cols.append('volume')
                    result[ticker] = data[cols].copy()
            
            logger.info(f"Successfully fetched prices for {len(result)} tickers in batch")
            return result
            
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1}/{max_retries} failed for batch fetch: {e}")
            if attempt == max_retries - 1:
                logger.error(f"All retries exhausted for batch fetch: {e}")
                return {}
            delay = base_delay * (2 ** attempt)
            time.sleep(delay)
    
    return {}


def fetch_benchmark_prices(ticker: str, start_date: date, end_date: date) -> pd.DataFrame:
    """Fetch historical prices for a benchmark ticker."""
    return fetch_prices(ticker, start_date, end_date)


def update_prices_for_company(company: Company, force: bool = False) -> int:
    """
    Ensure we have price data for a company from its earliest analysis date to today.
    Returns number of new price records inserted.
    """
    if not company.ticker_symbol:
        logger.info(f"No ticker for company {company.name}, skipping price update")
        return 0
    
    # Determine date range
    earliest = db.session.query(db.func.min(Analysis.analysis_date)).filter_by(company_id=company.id).scalar()
    if not earliest:
        logger.info(f"No analyses for company {company.name}, skipping price update")
        return 0
    
    start_date = earliest - timedelta(days=7)  # a week before to capture price on exact date
    end_date = date.today()
    # Ensure start_date <= end_date
    if start_date > end_date:
        logger.warning(f"Start date {start_date} after end date {end_date} for company {company.name}, adjusting.")
        start_date = end_date - timedelta(days=7)
    
    # Check which dates are already stored
    existing_dates = {sp.date for sp in StockPrice.query.filter_by(company_id=company.id).all()}
    
    # Fetch prices
    df = fetch_prices(company.ticker_symbol, start_date, end_date)
    
    # Small delay to be nice to the API
    time.sleep(0.5)
    
    if df.empty:
        logger.warning(f"No price data fetched for {company.name} ({company.ticker_symbol})")
        return 0
    
    new_records = 0
    for _, row in df.iterrows():
        price_date = row['Date'].date() if hasattr(row['Date'], 'date') else row['Date']
        if price_date in existing_dates and not force:
            continue
        sp = StockPrice(
            company_id=company.id,
            date=price_date,
            close_price=row['close_price'],
            volume=row.get('volume')
        )
        db.session.add(sp)
        new_records += 1
    
    if new_records:
        db.session.commit()
        logger.info(f"Added {new_records} price records for {company.name}")
    else:
        logger.info(f"No new price records needed for {company.name}")
    
    return new_records


def get_price_on_date(company_id: int, target_date: date) -> Optional[float]:
    """
    Return closing price on or before target_date for the given company.
    """
    # Query for the most recent price on or before target_date
    sp = StockPrice.query.filter(
        StockPrice.company_id == company_id,
        StockPrice.date <= target_date
    ).order_by(StockPrice.date.desc()).first()
    return sp.close_price if sp else None


def get_latest_price(company_id: int) -> Optional[float]:
    """Return the most recent available price for the company."""
    sp = StockPrice.query.filter_by(company_id=company_id).order_by(StockPrice.date.desc()).first()
    return sp.close_price if sp else None


def get_company_info(ticker: str) -> Dict:
    """
    Get company information from Yahoo Finance.
    
    Args:
        ticker: Stock ticker symbol
    
    Returns:
        Dictionary with company info (name, sector, industry, etc.)
    """
    from yahooquery import Ticker
    
    try:
        t = Ticker(ticker)
        info = t.asset_profile
        
        if info and ticker in info:
            return info[ticker]
        return {}
    except Exception as e:
        logger.error(f"Error fetching company info for {ticker}: {e}")
        return {}


def search_tickers(query: str) -> List[Dict]:
    """
    Search for tickers by company name or symbol.
    
    Args:
        query: Search query (e.g., 'Apple', 'Microsoft')
    
    Returns:
        List of dictionaries with ticker info
    """
    from yahooquery import search
    
    try:
        results = search(query)
        if 'quotes' in results:
            return [
                {
                    'symbol': q.get('symbol'),
                    'name': q.get('longname') or q.get('shortname'),
                    'exchange': q.get('exchange'),
                    'type': q.get('quoteType')
                }
                for q in results['quotes']
                if q.get('quoteType') in ['EQUITY', 'ETF']
            ]
        return []
    except Exception as e:
        logger.error(f"Error searching tickers for '{query}': {e}")
        return []
