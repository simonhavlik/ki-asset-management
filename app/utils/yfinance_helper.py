import yfinance as yf
import pandas as pd
from datetime import date, timedelta
import logging
import time
from typing import Optional, Tuple, List, Dict
from ..extensions import db
from ..models import Company, StockPrice, Analysis

logger = logging.getLogger(__name__)

def get_ticker_for_company(company_name: str, hint: Optional[str] = None) -> Optional[str]:
    """
    Search for a ticker symbol given a company name using DeepSeek API and Brave Search.
    Returns the ticker symbol if found, otherwise None.
    """
    from .brave_search import extract_ticker_with_fallback
    ticker, source = extract_ticker_with_fallback(company_name, hint)
    if ticker:
        logger.info(f"Extracted ticker {ticker} for {company_name} (source: {source})")
        return ticker
    logger.warning(f"No ticker found for {company_name}")
    return None


def get_validated_ticker_for_company(company_name: str, hint: Optional[str] = None, max_attempts: int = 2) -> Optional[str]:
    """
    Get ticker and validate it has price data on Yahoo Finance.
    If validation fails, try alternative tickers via Brave Search.
    Returns validated ticker or None.
    """
    from .brave_search import search_ticker_via_brave
    
    for attempt in range(max_attempts):
        # Get candidate ticker (first attempt uses normal flow, later attempts use fresh Brave search)
        if attempt == 0:
            ticker = get_ticker_for_company(company_name, hint)
        else:
            # Subsequent attempts: search with a query that includes 'yahoo finance exchange'
            query_hint = f"{hint} yahoo finance exchange" if hint else "yahoo finance exchange"
            ticker = search_ticker_via_brave(company_name, hint=query_hint)
        
        if not ticker:
            continue
        
        # Validate ticker by trying to fetch recent price data
        if _ticker_has_price_data(ticker):
            logger.info(f"Validated ticker {ticker} for {company_name}")
            return ticker
        else:
            logger.warning(f"Ticker {ticker} has no price data, trying alternative")
    
    logger.warning(f"No validated ticker found for {company_name} after {max_attempts} attempts")
    return None


def _ticker_has_price_data(ticker: str) -> bool:
    """Check if ticker returns any price data for the last 7 days."""
    from datetime import date, timedelta
    end_date = date.today()
    start_date = end_date - timedelta(days=7)
    df = fetch_prices(ticker, start_date, end_date)
    return not df.empty

def fetch_prices(ticker: str, start_date: date, end_date: date) -> pd.DataFrame:
    """Fetch historical prices from Yahoo Finance with retry logic."""
    max_retries = 3
    base_delay = 2  # seconds
    
    for attempt in range(max_retries):
        try:
            data = yf.download(ticker, start=start_date, end=end_date, progress=False)
            if data.empty:
                logger.warning(f"No data for {ticker} between {start_date} and {end_date}")
                return pd.DataFrame()
            # Reset index to have Date as column
            data = data.reset_index()
            # If columns are MultiIndex (yfinance 1.1.0+), flatten them
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = [col[0] for col in data.columns]
            # Select required columns and rename
            data = data[['Date', 'Close', 'Volume']].rename(columns={'Close': 'close_price', 'Volume': 'volume'})
            return data
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1}/{max_retries} failed for {ticker}: {e}")
            if attempt == max_retries - 1:
                logger.error(f"All retries exhausted for {ticker}")
                return pd.DataFrame()
            delay = base_delay * (2 ** attempt)  # exponential backoff
            time.sleep(delay)
    return pd.DataFrame()

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
    # Small delay to avoid rate limiting
    time.sleep(1)
    if df.empty:
        return 0
    
    new_records = 0
    for _, row in df.iterrows():
        price_date = row['Date'].date()
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