"""
Overview page caching system for fast filter switching.

Uses database-backed cache (persistent on Render) with file cache as fallback.
Caches all 5 filter categories for 7 days to avoid recalculating on every request.
Admin can force refresh with a button.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Any

from ..extensions import db

logger = logging.getLogger(__name__)

# File cache fallback (for compatibility)
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'instance', 'overview_cache')
CACHE_EXPIRY_DAYS = 7

# Disable database cache temporarily until schema is migrated
USE_DATABASE_CACHE = True

FILTER_CATEGORIES = [
    'purchased',
    'board_approved', 
    'all_approved',
    'approved_neutral',
    'all'
]


def ensure_cache_dir():
    """Ensure cache directory exists."""
    os.makedirs(CACHE_DIR, exist_ok=True)


def get_cache_path(filter_type: str) -> str:
    """Get cache file path for a filter type."""
    ensure_cache_dir()
    return os.path.join(CACHE_DIR, f'{filter_type}_cache.json')


def get_cached_overview_data(filter_type: str) -> Optional[Dict[str, Any]]:
    """
    Get cached overview data for a filter type if valid.
    Tries database cache first (persistent), falls back to file cache.
    
    Returns:
        Dict with data or None if no valid cache
    """
    # Ensure clean transaction state
    try:
        db.session.rollback()
    except:
        pass
    
    # Try database cache first (persistent across deployments) - if enabled
    if USE_DATABASE_CACHE:
        try:
            from ..models import OverviewDataCache
            db_cache = OverviewDataCache.query.filter_by(filter_type=filter_type).first()
            if db_cache and db_cache.is_fresh(CACHE_EXPIRY_DAYS):
                age_days = (datetime.utcnow() - db_cache.cached_at).days
                logger.info(f"Using DATABASE cache for {filter_type} ({age_days} days old)")
                return db_cache.to_dict()
        except Exception as e:
            logger.warning(f"Error reading database cache for {filter_type}: {e}")
            # Rollback to clear failed transaction
            try:
                db.session.rollback()
            except:
                pass
    
    # Fallback to file cache
    cache_path = get_cache_path(filter_type)
    
    if not os.path.exists(cache_path):
        return None
    
    try:
        with open(cache_path, 'r') as f:
            cache_data = json.load(f)
        
        # Check age
        cached_at = datetime.fromisoformat(cache_data.get('cached_at', '2000-01-01'))
        age_days = (datetime.utcnow() - cached_at).days
        
        if age_days >= CACHE_EXPIRY_DAYS:
            logger.info(f"File cache for {filter_type} expired ({age_days} days)")
            return None
        
        logger.info(f"Using FILE cache for {filter_type} ({age_days} days old)")
        return cache_data.get('data')
        
    except Exception as e:
        logger.warning(f"Error reading file cache for {filter_type}: {e}")
        return None


def _serialize_for_json(obj):
    """Recursively convert datetime objects to ISO format strings."""
    if isinstance(obj, dict):
        return {k: _serialize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_serialize_for_json(item) for item in obj]
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif hasattr(obj, 'isoformat'):  # date objects
        return obj.isoformat()
    else:
        return obj


def save_overview_cache(filter_type: str, data: Dict):
    """
    Save overview data to cache.
    Saves to both database (primary) and file (backup).
    """
    # Ensure clean transaction state
    try:
        db.session.rollback()
    except:
        pass
    
    # Serialize data to handle datetime objects
    serialized_data = _serialize_for_json(data)
    
    # Save to database (persistent on Render) - if enabled
    db_success = False
    if USE_DATABASE_CACHE:
        try:
            from ..models import OverviewDataCache
            db_cache = OverviewDataCache.query.filter_by(filter_type=filter_type).first()
            
            if not db_cache:
                db_cache = OverviewDataCache(filter_type=filter_type)
                db.session.add(db_cache)
            
            db_cache.portfolio_performance = serialized_data.get('portfolio_performance', {})
            db_cache.series_all = serialized_data.get('series_all', [])
            db_cache.series_1y = serialized_data.get('series_1y', [])
            db_cache.sector_stats = serialized_data.get('sector_stats', [])
            db_cache.analyst_rankings = serialized_data.get('analyst_rankings', [])
            db_cache.positive_ratio = serialized_data.get('positive_ratio', 0)
            db_cache.total_positions = serialized_data.get('total_positions', 0)
            db_cache.cached_at = datetime.utcnow()
            db_cache.expires_at = datetime.utcnow() + timedelta(days=CACHE_EXPIRY_DAYS)
            
            db.session.commit()
            db_success = True
            logger.info(f"Saved to DATABASE cache for {filter_type}")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error saving database cache for {filter_type}: {e}")
    
    # Always save to file (backup or primary if DB fails)
    cache_path = get_cache_path(filter_type)
    
    cache_data = {
        'cached_at': datetime.utcnow().isoformat(),
        'filter_type': filter_type,
        'data': data
    }
    
    try:
        with open(cache_path, 'w') as f:
            json.dump(cache_data, f, default=str)
        logger.info(f"Saved to FILE cache for {filter_type}")
    except Exception as e:
        logger.error(f"Error saving file cache for {filter_type}: {e}")


def invalidate_cache(filter_type: str = None):
    """
    Invalidate cache for a specific filter or all filters.
    Clears both database and file cache.
    
    Args:
        filter_type: Specific filter to invalidate, or None for all
    """
    # Invalidate database cache - if enabled
    if USE_DATABASE_CACHE:
        try:
            from ..models import OverviewDataCache
            if filter_type:
                db_cache = OverviewDataCache.query.filter_by(filter_type=filter_type).first()
                if db_cache:
                    db.session.delete(db_cache)
                    logger.info(f"Invalidated DATABASE cache for {filter_type}")
            else:
                OverviewDataCache.query.delete()
                logger.info("Invalidated all DATABASE caches")
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error invalidating database cache: {e}")
    
    # Invalidate file cache
    if filter_type:
        cache_path = get_cache_path(filter_type)
        if os.path.exists(cache_path):
            os.remove(cache_path)
            logger.info(f"Invalidated FILE cache for {filter_type}")
    else:
        for ft in FILTER_CATEGORIES:
            cache_path = get_cache_path(ft)
            if os.path.exists(cache_path):
                os.remove(cache_path)
        logger.info("Invalidated all FILE caches")


def get_cache_status() -> Dict[str, Any]:
    """Get status of all caches (database + file)."""
    status = {
        'categories': {},
        'all_fresh': True,
        'oldest_cache_days': 0,
        'source': 'database' if USE_DATABASE_CACHE else 'file'
    }
    
    ages = []
    
    for ft in FILTER_CATEGORIES:
        # Check database cache first - if enabled
        db_found = False
        if USE_DATABASE_CACHE:
            try:
                from ..models import OverviewDataCache
                db_cache = OverviewDataCache.query.filter_by(filter_type=ft).first()
                if db_cache and db_cache.cached_at:
                    age_days = (datetime.utcnow() - db_cache.cached_at).days
                    is_fresh = db_cache.is_fresh(CACHE_EXPIRY_DAYS)
                    
                    status['categories'][ft] = {
                        'cached_at': db_cache.cached_at.isoformat(),
                        'age_days': age_days,
                        'is_fresh': is_fresh,
                        'source': 'database'
                    }
                    ages.append(age_days)
                    
                    if not is_fresh:
                        status['all_fresh'] = False
                    db_found = True
            except Exception as e:
                logger.warning(f"Error checking database cache status for {ft}: {e}")
        
        if db_found:
            continue
        
        # Fallback to file cache status
        cache_path = get_cache_path(ft)
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r') as f:
                    cache_data = json.load(f)
                cached_at = datetime.fromisoformat(cache_data.get('cached_at', '2000-01-01'))
                age_days = (datetime.utcnow() - cached_at).days
                is_fresh = age_days < CACHE_EXPIRY_DAYS
                
                status['categories'][ft] = {
                    'cached_at': cache_data.get('cached_at'),
                    'age_days': age_days,
                    'is_fresh': is_fresh,
                    'source': 'file'
                }
                ages.append(age_days)
                
                if not is_fresh:
                    status['all_fresh'] = False
            except Exception:
                status['categories'][ft] = {'error': True}
                status['all_fresh'] = False
        else:
            status['categories'][ft] = {'exists': False}
            status['all_fresh'] = False
    
    if ages:
        status['oldest_cache_days'] = max(ages)
    
    return status


def should_use_cache(filter_type: str, force_refresh: bool = False) -> bool:
    """
    Determine if we should use cached data.
    
    Args:
        filter_type: The filter category
        force_refresh: If True, never use cache
        
    Returns:
        True if cache should be used
    """
    if force_refresh:
        return False
    
    cache_data = get_cached_overview_data(filter_type)
    return cache_data is not None


def get_cache_age_days(filter_type: str) -> Optional[int]:
    """
    Get the age of the cache in days for a filter type.
    
    Args:
        filter_type: The filter category
        
    Returns:
        Age in days, or None if no cache exists
    """
    # Try database cache first
    if USE_DATABASE_CACHE:
        try:
            from ..models import OverviewDataCache
            db_cache = OverviewDataCache.query.filter_by(filter_type=filter_type).first()
            if db_cache and db_cache.cached_at:
                return (datetime.utcnow() - db_cache.cached_at).days
        except Exception:
            pass
    
    # Fallback to file cache
    cache_path = get_cache_path(filter_type)
    if not os.path.exists(cache_path):
        return None
    
    try:
        with open(cache_path, 'r') as f:
            cache_data = json.load(f)
        cached_at = datetime.fromisoformat(cache_data.get('cached_at', '2000-01-01'))
        return (datetime.utcnow() - cached_at).days
    except Exception:
        return None
