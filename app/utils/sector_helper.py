"""
Sector information helper for fetching and caching company sector data.

This module provides utilities to fetch sector information from yahooquery
and cache it locally to avoid repeated API calls.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List

from ..extensions import db
from ..models import Company, CompanySectorCache

logger = logging.getLogger(__name__)

# Cache expiry in days
CACHE_EXPIRY_DAYS = 3  # 3 days for Overview page


def get_sector_info(ticker_symbol: str) -> Optional[Dict[str, str]]:
    """
    Fetch sector information from yahooquery for a given ticker.
    
    Args:
        ticker_symbol: The stock ticker symbol
        
    Returns:
        Dict with 'sector' and 'industry' keys, or None if fetch fails
    """
    try:
        from yahooquery import Ticker
        
        ticker = Ticker(ticker_symbol)
        info = ticker.asset_profile
        
        if info and ticker_symbol in info:
            profile = info[ticker_symbol]
            if isinstance(profile, dict):
                return {
                    'sector': profile.get('sector'),
                    'industry': profile.get('industry')
                }
        return None
    except Exception as e:
        logger.warning(f"Error fetching sector info for {ticker_symbol}: {e}")
        return None


def get_cached_sector(company_id: int) -> Optional[CompanySectorCache]:
    """
    Get cached sector data for a company if it exists and is not expired.
    
    Args:
        company_id: The company ID
        
    Returns:
        CompanySectorCache object or None if not cached or expired
    """
    cache = CompanySectorCache.query.filter_by(company_id=company_id).first()
    
    if cache is None:
        return None
    
    # Check if cache is expired
    expiry_date = datetime.utcnow() - timedelta(days=CACHE_EXPIRY_DAYS)
    if cache.fetched_at < expiry_date:
        return None
    
    return cache


def fetch_and_cache_sector(company: Company) -> Optional[CompanySectorCache]:
    """
    Fetch sector info from yahooquery and cache it.
    
    Args:
        company: Company model instance
        
    Returns:
        CompanySectorCache object or None if fetch fails
    """
    if not company.ticker_symbol:
        return None
    
    sector_info = get_sector_info(company.ticker_symbol)
    
    if sector_info is None:
        return None
    
    # Check if cache exists
    cache = CompanySectorCache.query.filter_by(company_id=company.id).first()
    
    if cache:
        # Update existing cache
        cache.sector = sector_info.get('sector')
        cache.industry = sector_info.get('industry')
        cache.fetched_at = datetime.utcnow()
    else:
        # Create new cache
        cache = CompanySectorCache(
            company_id=company.id,
            sector=sector_info.get('sector'),
            industry=sector_info.get('industry')
        )
        db.session.add(cache)
    
    db.session.commit()
    return cache


def get_company_sector(company: Company, force_refresh: bool = False, 
                       allow_expired: bool = True) -> Optional[str]:
    """
    Get sector for a company, using cache if available.
    
    Args:
        company: Company model instance
        force_refresh: If True, always fetch fresh data
        allow_expired: If True, return expired cache instead of fetching new
        
    Returns:
        Sector string or None
    """
    if force_refresh:
        cache = fetch_and_cache_sector(company)
        return cache.sector if cache else None
    
    cache = get_cached_sector(company.id)
    if cache is None:
        # Check if we have any cache (even expired)
        if allow_expired:
            cache = CompanySectorCache.query.filter_by(company_id=company.id).first()
            if cache:
                return cache.sector
        # Fetch new data
        cache = fetch_and_cache_sector(company)
    
    return cache.sector if cache else None


def get_company_sector_async(company: Company) -> Optional[str]:
    """
    Get sector asynchronously - returns cached value immediately,
    triggers background refresh if cache is expired.
    For use in Overview page to avoid blocking.
    """
    # First check if we have any cache
    cache = CompanySectorCache.query.filter_by(company_id=company.id).first()
    
    if cache:
        # Check if expired
        expiry_date = datetime.utcnow() - timedelta(days=CACHE_EXPIRY_DAYS)
        if cache.fetched_at < expiry_date:
            # Cache is expired, but return it anyway
            # In production, you might want to trigger a background job here
            pass
        return cache.sector
    
    # No cache, try to fetch
    cache = fetch_and_cache_sector(company)
    return cache.sector if cache else None


def get_sector_stats_cache_info() -> dict:
    """Get information about sector cache status."""
    total_companies = Company.query.filter(Company.ticker_symbol.isnot(None)).count()
    cached_companies = CompanySectorCache.query.count()
    
    latest_cache = CompanySectorCache.query.order_by(
        CompanySectorCache.fetched_at.desc()
    ).first()
    
    if latest_cache:
        age_days = (datetime.utcnow() - latest_cache.fetched_at).days
        is_fresh = age_days <= CACHE_EXPIRY_DAYS
    else:
        age_days = None
        is_fresh = False
    
    return {
        'total_companies': total_companies,
        'cached_companies': cached_companies,
        'coverage_percent': round((cached_companies / total_companies * 100), 1) if total_companies > 0 else 0,
        'last_updated': latest_cache.fetched_at if latest_cache else None,
        'age_days': age_days,
        'is_fresh': is_fresh
    }


def get_sector_distribution(analysis_ids: List[int]) -> Dict[str, int]:
    """
    Get sector distribution for a list of analyses.
    
    Args:
        analysis_ids: List of analysis IDs
        
    Returns:
        Dict mapping sector names to counts
    """
    from ..models import Analysis
    
    distribution = {}
    
    analyses = Analysis.query.filter(Analysis.id.in_(analysis_ids)).all()
    
    for analysis in analyses:
        company = Company.query.get(analysis.company_id)
        if not company:
            continue
        
        sector = get_company_sector(company)
        
        if sector:
            distribution[sector] = distribution.get(sector, 0) + 1
        else:
            distribution['Unknown'] = distribution.get('Unknown', 0) + 1
    
    return distribution


def refresh_all_sectors():
    """
    Refresh sector cache for all companies with tickers.
    
    Returns:
        Dict with statistics
    """
    companies = Company.query.filter(Company.ticker_symbol.isnot(None)).all()
    
    stats = {
        'total': len(companies),
        'updated': 0,
        'failed': 0
    }
    
    for company in companies:
        try:
            cache = fetch_and_cache_sector(company)
            if cache:
                stats['updated'] += 1
            else:
                stats['failed'] += 1
        except Exception as e:
            logger.warning(f"Error refreshing sector for {company.name}: {e}")
            stats['failed'] += 1
    
    return stats
