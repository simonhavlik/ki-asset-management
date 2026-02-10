import logging
import requests
import re
from typing import Optional, Dict, Any, Tuple
from flask import current_app

logger = logging.getLogger(__name__)

def search_ticker_via_brave(company_name: str, hint: Optional[str] = None) -> Optional[str]:
    """
    Search for a ticker symbol using Brave Search API.
    Returns the ticker symbol if found, otherwise None.
    """
    api_key = current_app.config.get('BRAVE_SEARCH_API_KEY')
    if not api_key:
        logger.debug("Brave Search API key not configured, skipping ticker search")
        return None

    # Prepare query
    query = f'yahoo finance {company_name} stock ticker'
    if hint:
        query = f'{company_name} {hint} stock ticker yahoo finance'
    url = 'https://api.search.brave.com/res/v1/web/search'
    headers = {
        'Accept': 'application/json',
        'X-Subscription-Token': api_key
    }
    params = {
        'q': query,
        'count': 10,
        'search_lang': 'en'
    }

    try:
        logger.debug(f"Calling Brave Search API for '{company_name}'")
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        # Parse results
        ticker_candidates = []
        # Look in web results snippets
        web_results = data.get('web', {}).get('results', [])
        for result in web_results:
            title = result.get('title', '')
            description = result.get('description', '')
            combined = f"{title} {description}".lower()
            # Try to extract a ticker symbol pattern (uppercase letters, maybe with numbers, dots, 1-9 chars)
            # Common pattern: ticker in parentheses e.g., (AAPL) or (FRACTL.ST)
            matches = re.findall(r'\(([A-Z][A-Z0-9.]{1,8})\)', combined.upper())
            ticker_candidates.extend(matches)
            # Also look for patterns like "NASDAQ: AAPL" or "NYSE: AAPL"
            matches2 = re.findall(r'(?:NASDAQ|NYSE|OTC|NYSEAMERICAN|NYSEARCA):\s*([A-Z][A-Z0-9.]{0,8})', combined.upper())
            ticker_candidates.extend(matches2)
            # Look for "Symbol: TICKER" or "Ticker: TICKER"
            matches3 = re.findall(r'(?:Symbol|Ticker)\s*[:=]\s*([A-Z][A-Z0-9.]{1,8})', combined.upper())
            ticker_candidates.extend(matches3)

        # Deduplicate and pick the most frequent candidate
        if ticker_candidates:
            # Count frequencies
            from collections import Counter
            freq = Counter(ticker_candidates)
            most_common = freq.most_common(1)[0][0]
            logger.info(f"Brave Search extracted ticker {most_common} for {company_name}")
            return most_common

        logger.info(f"No ticker candidate found in Brave Search results for {company_name}")
        return None

    except requests.exceptions.RequestException as e:
        logger.error(f"Brave Search API request error: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in Brave Search: {e}")
        return None


def extract_ticker_with_fallback(company_name: str, hint: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """
    Try to extract ticker using DeepSeek first, then Brave Search.
    Returns (ticker, source) where source is 'deepseek', 'brave', or None.
    """
    # First try DeepSeek
    from .deepseek_client import extract_ticker as deepseek_extract
    ticker = deepseek_extract(company_name)
    if ticker:
        return ticker, 'deepseek'

    # Fallback to Brave Search
    ticker = search_ticker_via_brave(company_name, hint)
    if ticker:
        return ticker, 'brave'
    return None, None