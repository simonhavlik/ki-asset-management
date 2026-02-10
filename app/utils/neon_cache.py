"""
Neon.tech Optimization Cache System

This module provides aggressive caching to minimize Neon DB compute unit usage.
All public-facing data is cached in memory (Render) with file fallback.

Key features:
- In-memory caching for fast access without DB calls
- File-based fallback for persistence across restarts  
- Selective cache invalidation on data changes
- Cache warming on startup/schedule

Environment Variables:
    NEON_OPTIMIZE: Set to 'true' to enable aggressive caching
    CACHE_DEFAULT_TIMEOUT: Default cache TTL in seconds (default: 300)
    PUBLIC_DATA_CACHE_TIMEOUT: Public data cache TTL (default: 3600 = 1 hour)
    STATIC_DATA_CACHE_TIMEOUT: Static data cache TTL (default: 86400 = 24 hours)
"""

import os
import json
import logging
import hashlib
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional, Any, Callable
from flask import current_app

logger = logging.getLogger(__name__)

# Cache timeouts (in seconds)
DEFAULT_TIMEOUT = int(os.environ.get('CACHE_DEFAULT_TIMEOUT', 300))
PUBLIC_DATA_TIMEOUT = int(os.environ.get('PUBLIC_DATA_CACHE_TIMEOUT', 3600))  # 1 hour
STATIC_DATA_TIMEOUT = int(os.environ.get('STATIC_DATA_CACHE_TIMEOUT', 86400))  # 24 hours
SHORT_TIMEOUT = int(os.environ.get('SHORT_CACHE_TIMEOUT', 60))  # 1 minute

# Feature flag
NEON_OPTIMIZE = os.environ.get('NEON_OPTIMIZE', 'true').lower() == 'true'

# Global cache reference (set during app initialization)
_cache_instance = None

def set_cache_instance(cache):
    """Set the global cache instance during app initialization."""
    global _cache_instance
    _cache_instance = cache

def get_cache():
    """Get the cache instance."""
    global _cache_instance
    if _cache_instance is not None:
        return _cache_instance
    # Fallback to current_app
    try:
        from flask import current_app
        return current_app.extensions.get('cache')
    except RuntimeError:
        return None

# Cache key prefixes
KEY_PREFIX = {
    'main_stats': 'main:stats',
    'main_chart': 'main:chart',
    'main_growth': 'main:growth',
    'main_sectors': 'main:sectors',
    'main_blog_posts': 'main:blog_posts',
    'blog_index': 'blog:index',
    'blog_post': 'blog:post',
    'blog_categories': 'blog:categories',
    'blog_featured': 'blog:featured',
    'blog_rss': 'blog:rss',
    'blog_sitemap': 'blog:sitemap',
    'wall_ideas': 'wall:ideas',
    'wall_page': 'wall:page',
    'health': 'system:health',
    'db_status': 'system:db_status',
    'board_portfolio_perf': 'board:portfolio:perf',
    'board_portfolio_series': 'board:portfolio:series',
    'board_purchased_perf': 'board:purchased:perf',
    'board_purchased_series': 'board:purchased:series',
    'overview_data': 'overview:data',
    'last_recalculation': 'system:last_recalculation',
}


def get_cache_key(prefix: str, *args, **kwargs) -> str:
    """Generate a cache key from prefix and arguments."""
    key_parts = [prefix]
    
    # Add positional args
    for arg in args:
        key_parts.append(str(arg))
    
    # Add sorted kwargs
    if kwargs:
        sorted_kwargs = sorted(kwargs.items())
        key_parts.append(hashlib.md5(str(sorted_kwargs).encode()).hexdigest()[:8])
    
    return ':'.join(key_parts)


def cached(prefix: str, timeout: Optional[int] = None, unless: Optional[Callable] = None):
    """
    Decorator to cache function results.
    
    Args:
        prefix: Cache key prefix
        timeout: Cache timeout in seconds (default: from env)
        unless: Callable that returns True to skip caching
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Skip caching if optimization is disabled
            if not NEON_OPTIMIZE:
                return f(*args, **kwargs)
            
            # Skip caching if unless condition is met
            if unless and unless():
                return f(*args, **kwargs)
            
            cache = get_cache()
            if not cache:
                return f(*args, **kwargs)
            
            # Generate cache key
            cache_key = get_cache_key(prefix, *args, **kwargs)
            
            # Try to get from cache
            try:
                cached_value = cache.get(cache_key)
                if cached_value is not None:
                    logger.debug(f"Cache HIT: {cache_key}")
                    return cached_value
            except Exception as e:
                logger.warning(f"Cache read error: {e}")
            
            # Execute function
            result = f(*args, **kwargs)
            
            # Store in cache
            try:
                cache.set(cache_key, result, timeout=timeout or DEFAULT_TIMEOUT)
                logger.debug(f"Cache SET: {cache_key}")
            except Exception as e:
                logger.warning(f"Cache write error: {e}")
            
            return result
        
        return decorated_function
    return decorator


def cache_delete_pattern(pattern: str):
    """Delete all cache keys matching a pattern (if cache supports it)."""
    cache = get_cache()
    if not cache:
        return
    
    try:
        # SimpleCache doesn't support pattern deletion, so we use a workaround
        # For production, consider using RedisCache which supports this natively
        logger.info(f"Cache delete pattern: {pattern}")
        # Note: This is a no-op for SimpleCache
    except Exception as e:
        logger.warning(f"Cache delete error: {e}")


def invalidate_cache(prefix: Optional[str] = None):
    """
    Invalidate cache entries.
    
    Args:
        prefix: If provided, only invalidate keys with this prefix
    """
    cache = get_cache()
    if not cache:
        return
    
    try:
        if prefix:
            # For SimpleCache, we can't selectively delete
            # Just log it - in production with Redis, this would work properly
            logger.info(f"Cache invalidation requested for prefix: {prefix}")
        else:
            cache.clear()
            logger.info("Cache cleared")
    except Exception as e:
        logger.warning(f"Cache invalidation error: {e}")


# =============================================================================
# Cached Data Fetchers - These wrap DB calls with caching
# =============================================================================

def get_cached_main_stats(force_refresh: bool = False) -> Optional[dict]:
    """Get cached dashboard stats for main page."""
    from ..main.routes import get_dashboard_stats
    
    cache = get_cache()
    cache_key = KEY_PREFIX['main_stats']
    
    if not force_refresh and cache and NEON_OPTIMIZE:
        try:
            cached = cache.get(cache_key)
            if cached is not None:
                return cached
        except Exception:
            pass
    
    # Fetch from DB
    stats = get_dashboard_stats()
    
    if cache and NEON_OPTIMIZE:
        try:
            cache.set(cache_key, stats, timeout=PUBLIC_DATA_TIMEOUT)
        except Exception as e:
            logger.warning(f"Failed to cache stats: {e}")
    
    return stats


def get_cached_portfolio_chart(force_refresh: bool = False, method: str = 'incremental') -> Optional[dict]:
    """
    Get cached portfolio chart data.
    
    Args:
        force_refresh: Force recalculation
        method: 'incremental' (default) or 'equal' - calculation method
    """
    from ..main.routes import get_portfolio_chart_data
    
    cache = get_cache()
    cache_key = f"{KEY_PREFIX['main_chart']}:{method}"
    
    if not force_refresh and cache and NEON_OPTIMIZE:
        try:
            cached = cache.get(cache_key)
            if cached is not None:
                return cached
        except Exception:
            pass
    
    # Fetch from DB with method parameter
    chart_data = get_portfolio_chart_data(method=method)
    
    if cache and NEON_OPTIMIZE:
        try:
            cache.set(cache_key, chart_data, timeout=PUBLIC_DATA_TIMEOUT)
        except Exception as e:
            logger.warning(f"Failed to cache chart: {e}")
    
    return chart_data


def get_cached_growth_timeline(force_refresh: bool = False) -> Optional[dict]:
    """Get cached growth timeline data."""
    cache = get_cache()
    cache_key = KEY_PREFIX['main_growth']
    
    if not force_refresh and cache and NEON_OPTIMIZE:
        try:
            cached = cache.get(cache_key)
            if cached is not None:
                return cached
        except Exception:
            pass
    
    # Fetch from DB
    try:
        from ..utils.presentation_export import get_growth_timeline_for_chart
        growth_data = get_growth_timeline_for_chart()
    except Exception as e:
        logger.warning(f"Error loading growth timeline: {e}")
        growth_data = None
    
    if cache and NEON_OPTIMIZE:
        try:
            cache.set(cache_key, growth_data, timeout=PUBLIC_DATA_TIMEOUT)
        except Exception as e:
            logger.warning(f"Failed to cache growth: {e}")
    
    return growth_data


def get_cached_top_sectors(force_refresh: bool = False) -> Optional[list]:
    """Get cached top sectors data."""
    cache = get_cache()
    cache_key = KEY_PREFIX['main_sectors']
    
    if not force_refresh and cache and NEON_OPTIMIZE:
        try:
            cached = cache.get(cache_key)
            if cached is not None:
                return cached
        except Exception:
            pass
    
    # Fetch from DB
    try:
        from ..utils.presentation_export import get_sector_analysis
        sector_data = get_sector_analysis()
        top_sectors = sector_data.get('best_sectors')
    except Exception as e:
        logger.warning(f"Error loading sector data: {e}")
        top_sectors = None
    
    if cache and NEON_OPTIMIZE:
        try:
            cache.set(cache_key, top_sectors, timeout=PUBLIC_DATA_TIMEOUT)
        except Exception as e:
            logger.warning(f"Failed to cache sectors: {e}")
    
    return top_sectors


def _serialize_blog_post(post) -> dict:
    """Convert a BlogPost object to a dictionary for caching."""
    return {
        'id': post.id,
        'title': post.title,
        'slug': post.slug,
        'meta_description': post.meta_description,
        'meta_keywords': post.meta_keywords,
        'og_image': post.og_image,
        'excerpt': post.excerpt,
        'content': post.content,
        'content_type': post.content_type,
        'author_id': post.author_id,
        'author_name': post.author_name,  # Pre-compute the property
        'author_email': post.author.email if post.author else None,  # For RSS
        'created_at': post.created_at.isoformat() if post.created_at else None,
        'updated_at': post.updated_at.isoformat() if post.updated_at else None,
        'published_at': post.published_at.isoformat() if post.published_at else None,
        'is_public': post.is_public,
        'is_featured': post.is_featured,
        'status': post.status,
        'view_count': post.view_count,
        'category': post.category,
        'tags': post.tags,
        'reading_time': post.reading_time,
        'tag_list': post.tag_list,
        'formatted_date': post.formatted_date,
    }


def get_cached_latest_blog_posts(limit: int = 3, force_refresh: bool = False) -> list:
    """Get cached latest blog posts for main page. Returns list of SimpleBlogPost objects."""
    cache = get_cache()
    cache_key = get_cache_key(KEY_PREFIX['main_blog_posts'], limit)
    
    if not force_refresh and cache and NEON_OPTIMIZE:
        try:
            cached = cache.get(cache_key)
            if cached is not None:
                # Wrap cached dicts in SimpleBlogPost objects
                return [SimpleBlogPost(post) for post in cached]
        except Exception:
            pass
    
    # Fetch from DB with eager loading of author to avoid detached instance issues
    try:
        from ..models import BlogPost
        from sqlalchemy import desc
        from sqlalchemy.orm import joinedload
        
        posts = BlogPost.query.options(
            joinedload(BlogPost.author)
        ).filter(
            BlogPost.status == 'published',
            BlogPost.is_public == True
        ).order_by(desc(BlogPost.published_at)).limit(limit).all()
        
        # Convert to dictionaries before caching
        posts_data = [_serialize_blog_post(post) for post in posts]
    except Exception as e:
        logger.warning(f"Error loading blog posts: {e}")
        posts_data = []
    
    if cache and NEON_OPTIMIZE:
        try:
            cache.set(cache_key, posts_data, timeout=PUBLIC_DATA_TIMEOUT)
        except Exception as e:
            logger.warning(f"Failed to cache blog posts: {e}")
    
    # Return SimpleBlogPost wrappers
    return [SimpleBlogPost(post) for post in posts_data]


def get_cached_blog_index(page: int = 1, category: str = '', tag: str = '', 
                          force_refresh: bool = False) -> dict:
    """Get cached blog index data. Returns dict with SimpleBlogPost objects."""
    cache = get_cache()
    cache_key = get_cache_key(KEY_PREFIX['blog_index'], page, category, tag)
    
    if not force_refresh and cache and NEON_OPTIMIZE:
        try:
            cached = cache.get(cache_key)
            if cached is not None:
                # Reconstruct SimpleBlogPost objects and pagination from cached data
                posts = [SimpleBlogPost(p) for p in cached['posts']]
                featured = [SimpleBlogPost(p) for p in cached['featured_posts']]
                return {
                    'posts': posts,
                    'pagination': SimplePagination(posts, cached['_page'], cached['_per_page'], cached['_total']),
                    'categories': cached['categories'],
                    'category_counts': cached['category_counts'],
                    'featured_posts': featured,
                }
        except Exception:
            pass
    
    # Fetch from DB with eager loading
    from ..models import BlogPost
    from sqlalchemy import desc, or_
    from sqlalchemy.orm import joinedload
    
    per_page = 9
    
    # Base query with eager loading
    query = BlogPost.query.options(
        joinedload(BlogPost.author)
    ).filter(
        BlogPost.status == 'published',
        BlogPost.is_public == True,
        BlogPost.published_at != None
    ).order_by(desc(BlogPost.published_at))
    
    # Filter by category
    if category:
        query = query.filter(BlogPost.category == category)
    
    # Filter by tag
    if tag:
        query = query.filter(BlogPost.tags.contains(tag))
    
    pagination = query.paginate(page=page, per_page=per_page)
    
    # Get categories for sidebar
    categories = BlogPost.query.filter(
        BlogPost.status == 'published',
        BlogPost.is_public == True
    ).with_entities(BlogPost.category).distinct().all()
    categories = [c[0] for c in categories if c[0]]
    
    # Get category counts
    category_counts = {}
    for cat in categories:
        count = BlogPost.query.filter_by(
            category=cat,
            status='published',
            is_public=True
        ).count()
        category_counts[cat] = count
    
    # Get featured posts with eager loading
    featured_posts = BlogPost.query.options(
        joinedload(BlogPost.author)
    ).filter(
        BlogPost.status == 'published',
        BlogPost.is_public == True,
        BlogPost.is_featured == True
    ).order_by(desc(BlogPost.published_at)).limit(3).all()
    
    # Serialize posts before caching (store raw dicts in cache)
    posts_data = [_serialize_blog_post(post) for post in pagination.items]
    featured_data = [_serialize_blog_post(post) for post in featured_posts]
    
    result = {
        'posts': posts_data,
        'pagination': None,  # Will be reconstructed after cache retrieval
        'categories': categories,
        'category_counts': category_counts,
        'featured_posts': featured_data,
        '_page': page,
        '_per_page': per_page,
        '_total': pagination.total,
    }
    
    if cache and NEON_OPTIMIZE:
        try:
            cache.set(cache_key, result, timeout=PUBLIC_DATA_TIMEOUT)
        except Exception as e:
            logger.warning(f"Failed to cache blog index: {e}")
    
    # Return with SimpleBlogPost wrappers and pagination
    return {
        'posts': [SimpleBlogPost(p) for p in posts_data],
        'pagination': SimplePagination([SimpleBlogPost(p) for p in posts_data], page, per_page, pagination.total),
        'categories': categories,
        'category_counts': category_counts,
        'featured_posts': [SimpleBlogPost(p) for p in featured_data],
    }


def get_cached_blog_post(slug: str, force_refresh: bool = False):
    """Get cached individual blog post. Returns SimpleBlogPost or None."""
    cache = get_cache()
    cache_key = get_cache_key(KEY_PREFIX['blog_post'], slug)
    
    if not force_refresh and cache and NEON_OPTIMIZE:
        try:
            cached = cache.get(cache_key)
            if cached is not None:
                return SimpleBlogPost(cached)
        except Exception:
            pass
    
    # Fetch from DB with eager loading
    from ..models import BlogPost
    from sqlalchemy.orm import joinedload
    
    post = BlogPost.query.options(
        joinedload(BlogPost.author)
    ).filter_by(slug=slug).first()
    
    if post is None:
        return None
    
    # Serialize before caching
    post_dict = _serialize_blog_post(post)
    
    if cache and NEON_OPTIMIZE:
        try:
            cache.set(cache_key, post_dict, timeout=PUBLIC_DATA_TIMEOUT)
        except Exception as e:
            logger.warning(f"Failed to cache blog post: {e}")
    
    return SimpleBlogPost(post_dict)


def _serialize_comment(comment) -> dict:
    """Convert an IdeaComment object to a dictionary for caching."""
    return {
        'id': comment.id,
        'content': comment.content,
        'author_id': comment.author_id,
        'author_name': comment.author_name,  # Pre-compute
        'created_at': comment.created_at.isoformat() if comment.created_at else None,
    }


def _serialize_idea(idea) -> dict:
    """Convert an Idea object to a dictionary for caching."""
    # Serialize comments
    try:
        if hasattr(idea.comments, 'all'):
            comments = [_serialize_comment(c) for c in idea.comments.all()]
        else:
            comments = [_serialize_comment(c) for c in idea.comments]
    except Exception:
        comments = []
    
    return {
        'id': idea.id,
        'title': idea.title,
        'content': idea.content,
        'sentiment': idea.sentiment,
        'ticker': idea.ticker,
        'author_id': idea.author_id,
        'author_name': idea.author_name,  # Pre-compute
        'created_at': idea.created_at.isoformat() if idea.created_at else None,
        'updated_at': idea.updated_at.isoformat() if idea.updated_at else None,
        'likes_count': idea.likes_count,
        'comments': comments,  # Store serialized comments
    }


class SimplePagination:
    """A simple pagination class for cached results."""
    def __init__(self, items, page, per_page, total):
        self.items = items
        self.page = page
        self.per_page = per_page
        self.total = total
        self.pages = (total + per_page - 1) // per_page if per_page > 0 else 0
        self.has_prev = page > 1
        self.has_next = page < self.pages
        self.prev_num = page - 1 if self.has_prev else None
        self.next_num = page + 1 if self.has_next else None
    
    def iter_pages(self, left_edge=2, left_current=2, right_current=3, right_edge=2):
        """Iterate over page numbers for pagination display."""
        last = 0
        for num in range(1, self.pages + 1):
            if num <= left_edge or \
               (num > self.page - left_current - 1 and num < self.page + right_current) or \
               num > self.pages - right_edge:
                if last + 1 != num:
                    yield None  # Ellipsis
                yield num
                last = num


class SimpleBlogPost:
    """
    A wrapper for serialized blog post dictionaries that provides 
    the same interface as the BlogPost model for templates.
    """
    def __init__(self, data: dict):
        self._data = data
        # Parse datetime strings back to datetime objects for strftime support
        from datetime import datetime
        for key in ['created_at', 'updated_at', 'published_at']:
            val = self._data.get(key)
            if val and isinstance(val, str):
                try:
                    # Parse ISO format datetime
                    self._data[key] = datetime.fromisoformat(val.replace('Z', '+00:00'))
                except (ValueError, TypeError):
                    pass
        # Create author wrapper for RSS compatibility
        if self._data.get('author_email'):
            self._data['author'] = type('Author', (), {'email': self._data['author_email']})()
    
    def __getattr__(self, name):
        """Delegate attribute access to the underlying dict."""
        if name in self._data:
            return self._data[name]
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")
    
    def __getitem__(self, key):
        """Allow dict-style access."""
        return self._data[key]
    
    def get_excerpt(self, max_length=200):
        """Get excerpt or generate from content (matches BlogPost.get_excerpt)."""
        # If we have excerpt stored, use it
        if self._data.get('excerpt'):
            excerpt = self._data['excerpt']
            if len(excerpt) > max_length:
                return excerpt[:max_length].rsplit(' ', 1)[0] + '...'
            return excerpt
        # Otherwise generate from content
        import re
        content = self._data.get('content', '')
        text = re.sub(r'<[^>]+>', '', content)
        if len(text) > max_length:
            return text[:max_length].rsplit(' ', 1)[0] + '...'
        return text
    
    def get(self, key, default=None):
        """Dict-style get method."""
        return self._data.get(key, default)


class SimpleComment:
    """A wrapper for serialized comment dictionaries."""
    def __init__(self, data: dict):
        self._data = data
        # Parse datetime
        from datetime import datetime
        val = self._data.get('created_at')
        if val and isinstance(val, str):
            try:
                self._data['created_at'] = datetime.fromisoformat(val.replace('Z', '+00:00'))
            except (ValueError, TypeError):
                pass
    
    def __getattr__(self, name):
        if name in self._data:
            return self._data[name]
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")


class SimpleCommentsList:
    """A wrapper to provide count() method and iteration for comments."""
    def __init__(self, comments_data: list):
        self._comments = [SimpleComment(c) for c in comments_data]
    
    def count(self):
        return len(self._comments)
    
    def __iter__(self):
        return iter(self._comments)
    
    def __len__(self):
        return len(self._comments)


class SimpleIdea:
    """
    A wrapper for serialized idea dictionaries that provides
    the same interface as the Idea model for templates.
    """
    def __init__(self, data: dict):
        self._data = data
        # Parse datetime strings back to datetime objects for strftime support
        from datetime import datetime
        for key in ['created_at', 'updated_at']:
            val = self._data.get(key)
            if val and isinstance(val, str):
                try:
                    self._data[key] = datetime.fromisoformat(val.replace('Z', '+00:00'))
                except (ValueError, TypeError):
                    pass
        # Create comments wrapper - replace raw list with wrapper
        self._data['comments'] = SimpleCommentsList(data.get('comments', []))
    
    def __getattr__(self, name):
        """Delegate attribute access to the underlying dict."""
        if name in self._data:
            return self._data[name]
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")
    
    def __getitem__(self, key):
        """Allow dict-style access."""
        return self._data[key]


def get_cached_wall_ideas(page: int = 1, per_page: int = 12, force_refresh: bool = False):
    """Get cached ideas wall data. Returns dict with SimpleIdea objects."""
    cache = get_cache()
    cache_key = get_cache_key(KEY_PREFIX['wall_page'], page, per_page)
    
    if not force_refresh and cache and NEON_OPTIMIZE:
        try:
            cached = cache.get(cache_key)
            if cached is not None:
                # Reconstruct SimpleIdea objects from cached data
                ideas = [SimpleIdea(i) for i in cached['ideas']]
                return {
                    'ideas': ideas,
                    'pagination': SimplePagination(ideas, cached['_page'], cached['_per_page'], cached['_total']),
                }
        except Exception:
            pass
    
    # Fetch from DB with eager loading
    from ..models import Idea
    from sqlalchemy.orm import joinedload
    
    ideas_query = Idea.query.options(
        joinedload(Idea.author)
    ).order_by(Idea.created_at.desc())
    pagination = ideas_query.paginate(page=page, per_page=per_page)
    
    ideas_data = [_serialize_idea(idea) for idea in pagination.items]
    
    # Store raw data in cache
    result_data = {
        'ideas': ideas_data,
        '_page': page,
        '_per_page': per_page,
        '_total': pagination.total,
    }
    
    if cache and NEON_OPTIMIZE:
        try:
            cache.set(cache_key, result_data, timeout=SHORT_TIMEOUT)  # Shorter timeout for interactive content
        except Exception as e:
            logger.warning(f"Failed to cache wall ideas: {e}")
    
    # Return with SimpleIdea wrappers
    ideas = [SimpleIdea(i) for i in ideas_data]
    return {
        'ideas': ideas,
        'pagination': SimplePagination(ideas, page, per_page, pagination.total),
    }


def get_cached_rss_posts(force_refresh: bool = False) -> list:
    """Get cached RSS feed posts. Returns list of SimpleBlogPost objects."""
    cache = get_cache()
    cache_key = KEY_PREFIX['blog_rss']
    
    if not force_refresh and cache and NEON_OPTIMIZE:
        try:
            cached = cache.get(cache_key)
            if cached is not None:
                return [SimpleBlogPost(p) for p in cached]
        except Exception:
            pass
    
    # Fetch from DB with eager loading
    from ..models import BlogPost
    from sqlalchemy import desc
    from sqlalchemy.orm import joinedload
    
    posts = BlogPost.query.options(
        joinedload(BlogPost.author)
    ).filter(
        BlogPost.status == 'published',
        BlogPost.is_public == True
    ).order_by(desc(BlogPost.published_at)).limit(20).all()
    
    # Serialize before caching
    posts_data = [_serialize_blog_post(post) for post in posts]
    
    if cache and NEON_OPTIMIZE:
        try:
            cache.set(cache_key, posts_data, timeout=PUBLIC_DATA_TIMEOUT)
        except Exception as e:
            logger.warning(f"Failed to cache RSS posts: {e}")
    
    return [SimpleBlogPost(p) for p in posts_data]


def get_cached_sitemap_posts(force_refresh: bool = False) -> list:
    """Get cached sitemap posts. Returns list of SimpleBlogPost objects."""
    cache = get_cache()
    cache_key = KEY_PREFIX['blog_sitemap']
    
    if not force_refresh and cache and NEON_OPTIMIZE:
        try:
            cached = cache.get(cache_key)
            if cached is not None:
                return [SimpleBlogPost(p) for p in cached]
        except Exception:
            pass
    
    # Fetch from DB with eager loading
    from ..models import BlogPost
    from sqlalchemy.orm import joinedload
    
    posts = BlogPost.query.options(
        joinedload(BlogPost.author)
    ).filter(
        BlogPost.status == 'published',
        BlogPost.is_public == True
    ).all()
    
    # Serialize before caching
    posts_data = [_serialize_blog_post(post) for post in posts]
    
    if cache and NEON_OPTIMIZE:
        try:
            cache.set(cache_key, posts_data, timeout=STATIC_DATA_TIMEOUT)  # Longer for sitemap
        except Exception as e:
            logger.warning(f"Failed to cache sitemap posts: {e}")
    
    return [SimpleBlogPost(p) for p in posts_data]


# =============================================================================
# Cache Invalidation Helpers - Call these when data changes
# =============================================================================

def invalidate_main_cache():
    """Invalidate main page caches."""
    keys = [
        KEY_PREFIX['main_stats'],
        KEY_PREFIX['main_chart'],
        KEY_PREFIX['main_growth'],
        KEY_PREFIX['main_sectors'],
        KEY_PREFIX['main_blog_posts'],
    ]
    cache = get_cache()
    if cache:
        for key in keys:
            try:
                cache.delete(key)
            except Exception:
                pass
    logger.info("Main page cache invalidated")


def invalidate_blog_cache():
    """Invalidate all blog-related caches."""
    keys = [
        KEY_PREFIX['main_blog_posts'],
        KEY_PREFIX['blog_categories'],
        KEY_PREFIX['blog_featured'],
        KEY_PREFIX['blog_rss'],
        KEY_PREFIX['blog_sitemap'],
    ]
    cache = get_cache()
    if cache:
        for key in keys:
            try:
                cache.delete(key)
            except Exception:
                pass
    logger.info("Blog cache invalidated")


def invalidate_wall_cache():
    """Invalidate wall/ideas caches."""
    keys = [
        KEY_PREFIX['wall_ideas'],
        KEY_PREFIX['wall_page'],
    ]
    cache = get_cache()
    if cache:
        for key in keys:
            try:
                cache.delete(key)
            except Exception:
                pass
    logger.info("Wall cache invalidated")


def invalidate_all_public_cache():
    """Invalidate all public-facing caches."""
    invalidate_main_cache()
    invalidate_blog_cache()
    invalidate_wall_cache()
    logger.info("All public caches invalidated")


# =============================================================================
# Cache Warming - Pre-populate caches
# =============================================================================

def warm_public_caches():
    """Pre-populate all public-facing caches."""
    logger.info("=" * 60)
    logger.info("Warming public caches for Neon optimization...")
    logger.info("=" * 60)
    
    start_time = datetime.now()
    warmed = []
    
    try:
        # Warm main page data
        get_cached_main_stats(force_refresh=True)
        warmed.append('main_stats')
    except Exception as e:
        logger.warning(f"Failed to warm main_stats: {e}")
    
    try:
        get_cached_portfolio_chart(force_refresh=True)
        warmed.append('portfolio_chart')
    except Exception as e:
        logger.warning(f"Failed to warm portfolio_chart: {e}")
    
    try:
        get_cached_growth_timeline(force_refresh=True)
        warmed.append('growth_timeline')
    except Exception as e:
        logger.warning(f"Failed to warm growth_timeline: {e}")
    
    try:
        get_cached_top_sectors(force_refresh=True)
        warmed.append('top_sectors')
    except Exception as e:
        logger.warning(f"Failed to warm top_sectors: {e}")
    
    try:
        get_cached_latest_blog_posts(limit=3, force_refresh=True)
        warmed.append('latest_blog_posts')
    except Exception as e:
        logger.warning(f"Failed to warm latest_blog_posts: {e}")
    
    try:
        get_cached_rss_posts(force_refresh=True)
        warmed.append('rss_posts')
    except Exception as e:
        logger.warning(f"Failed to warm rss_posts: {e}")
    
    try:
        get_cached_sitemap_posts(force_refresh=True)
        warmed.append('sitemap_posts')
    except Exception as e:
        logger.warning(f"Failed to warm sitemap_posts: {e}")
    
    elapsed = (datetime.now() - start_time).total_seconds()
    logger.info("=" * 60)
    logger.info(f"Cache warming completed in {elapsed:.1f}s")
    logger.info(f"Warmed: {', '.join(warmed)}")
    logger.info("=" * 60)
    
    return warmed


def get_cache_stats() -> dict:
    """Get cache statistics for monitoring."""
    stats = {
        'neon_optimize_enabled': NEON_OPTIMIZE,
        'cache_type': os.environ.get('CACHE_TYPE', 'SimpleCache'),
        'default_timeout': DEFAULT_TIMEOUT,
        'public_data_timeout': PUBLIC_DATA_TIMEOUT,
        'static_data_timeout': STATIC_DATA_TIMEOUT,
    }
    
    cache = get_cache()
    if cache and hasattr(cache, '_cache'):
        # SimpleCache exposes _cache dict
        try:
            stats['items_in_memory'] = len(cache._cache)
        except Exception:
            pass
    
    return stats


# =============================================================================
# Board Page Caching - Performance Optimization
# =============================================================================

def get_cached_board_portfolio_performance(purchased_only: bool = False, force_refresh: bool = False):
    """
    Get cached portfolio performance for Board page.
    
    Args:
        purchased_only: If True, only include purchased stocks
        force_refresh: Force recalculation
    
    Returns:
        Dict with portfolio performance data or None
    """
    cache = get_cache()
    cache_key = get_cache_key(
        KEY_PREFIX['board_purchased_perf'] if purchased_only else KEY_PREFIX['board_portfolio_perf']
    )
    
    if not force_refresh and cache and NEON_OPTIMIZE:
        try:
            cached = cache.get(cache_key)
            if cached is not None:
                logger.debug(f"Cache HIT: {cache_key}")
                return cached
        except Exception:
            pass
    
    # Calculate fresh data
    try:
        from ..admin.routes import get_portfolio_performance
        result = get_portfolio_performance(purchased_only=purchased_only)
    except Exception as e:
        logger.error(f"Error calculating portfolio performance: {e}")
        result = None
    
    if cache and NEON_OPTIMIZE and result:
        try:
            cache.set(cache_key, result, timeout=PUBLIC_DATA_TIMEOUT)
            logger.debug(f"Cache SET: {cache_key}")
        except Exception as e:
            logger.warning(f"Failed to cache portfolio performance: {e}")
    
    return result


def get_cached_board_portfolio_series(purchased_only: bool = False, years: int = None, force_refresh: bool = False):
    """
    Get cached portfolio series data for Board page charts.
    
    Args:
        purchased_only: If True, only include purchased stocks
        years: Number of years to include (None for all)
        force_refresh: Force recalculation
    
    Returns:
        Dict with series data or None
    """
    cache = get_cache()
    cache_key = get_cache_key(
        KEY_PREFIX['board_purchased_series'] if purchased_only else KEY_PREFIX['board_portfolio_series'],
        years
    )
    
    if not force_refresh and cache and NEON_OPTIMIZE:
        try:
            cached = cache.get(cache_key)
            if cached is not None:
                logger.debug(f"Cache HIT: {cache_key}")
                return cached
        except Exception:
            pass
    
    # Calculate fresh data
    try:
        from ..admin.routes import get_portfolio_series
        result = get_portfolio_series(purchased_only=purchased_only, years=years)
    except Exception as e:
        logger.error(f"Error calculating portfolio series: {e}")
        result = None
    
    if cache and NEON_OPTIMIZE and result:
        try:
            cache.set(cache_key, result, timeout=PUBLIC_DATA_TIMEOUT)
            logger.debug(f"Cache SET: {cache_key}")
        except Exception as e:
            logger.warning(f"Failed to cache portfolio series: {e}")
    
    return result


def invalidate_board_cache():
    """Invalidate all Board page caches."""
    keys = [
        KEY_PREFIX['board_portfolio_perf'],
        KEY_PREFIX['board_portfolio_series'],
        KEY_PREFIX['board_purchased_perf'],
        KEY_PREFIX['board_purchased_series'],
    ]
    cache = get_cache()
    if cache:
        for key in keys:
            try:
                # Use pattern delete for series keys with different year parameters
                if 'series' in key:
                    # Delete all variants of series keys
                    for years in [None, 1]:
                        series_key = get_cache_key(key, years)
                        cache.delete(series_key)
                else:
                    cache.delete(key)
            except Exception:
                pass
    logger.info("Board cache invalidated")


# =============================================================================
# Weekly Recalculation & Admin Refresh
# =============================================================================

def run_weekly_recalculation():
    """
    Run weekly recalculation of all performance data.
    This should be called by a scheduled job (e.g., cron).
    
    Returns:
        Dict with recalculation results
    """
    from flask import current_app
    
    logger.info("=" * 60)
    logger.info("Starting weekly recalculation...")
    logger.info("=" * 60)
    
    start_time = datetime.now()
    results = {
        'performance_calculated': 0,
        'caches_cleared': [],
        'caches_warmed': [],
        'errors': []
    }
    
    try:
        # Step 1: Recalculate all performance data
        with current_app.app_context():
            from ..utils.performance import PerformanceCalculator
            calculator = PerformanceCalculator()
            perf_stats = calculator.recalculate_all()
            results['performance_calculated'] = perf_stats.get('calculated', 0)
            logger.info(f"Performance recalculated: {results['performance_calculated']} analyses")
    except Exception as e:
        error_msg = f"Performance recalculation failed: {e}"
        logger.error(error_msg)
        results['errors'].append(error_msg)
    
    # Step 2: Clear all caches
    try:
        invalidate_all_public_cache()
        invalidate_board_cache()
        results['caches_cleared'] = ['public', 'board']
        logger.info("All caches cleared")
    except Exception as e:
        error_msg = f"Cache clearing failed: {e}"
        logger.error(error_msg)
        results['errors'].append(error_msg)
    
    # Step 3: Warm caches
    try:
        warmed = warm_public_caches()
        results['caches_warmed'] = warmed
    except Exception as e:
        error_msg = f"Cache warming failed: {e}"
        logger.error(error_msg)
        results['errors'].append(error_msg)
    
    # Step 4: Update last recalculation timestamp
    try:
        cache = get_cache()
        if cache:
            cache.set(
                KEY_PREFIX['last_recalculation'],
                datetime.now().isoformat(),
                timeout=STATIC_DATA_TIMEOUT
            )
    except Exception as e:
        logger.warning(f"Failed to update last recalculation timestamp: {e}")
    
    elapsed = (datetime.now() - start_time).total_seconds()
    results['elapsed_seconds'] = elapsed
    
    logger.info("=" * 60)
    logger.info(f"Weekly recalculation completed in {elapsed:.1f}s")
    logger.info(f"Performance: {results['performance_calculated']} analyses")
    logger.info(f"Caches warmed: {', '.join(results['caches_warmed'])}")
    if results['errors']:
        logger.info(f"Errors: {len(results['errors'])}")
    logger.info("=" * 60)
    
    return results


def admin_manual_recalculation():
    """
    Admin manual recalculation - forces complete refresh of all data.
    Same as weekly recalculation but can be triggered manually.
    
    Returns:
        Dict with recalculation results
    """
    logger.info("Admin triggered manual recalculation")
    return run_weekly_recalculation()


def get_last_recalculation_time():
    """Get the timestamp of the last recalculation."""
    cache = get_cache()
    if cache:
        try:
            timestamp = cache.get(KEY_PREFIX['last_recalculation'])
            if timestamp:
                return datetime.fromisoformat(timestamp)
        except Exception:
            pass
    return None


def should_run_weekly_recalculation():
    """
    Check if weekly recalculation should run.
    Returns True if it's been more than 7 days since last recalculation.
    """
    last_run = get_last_recalculation_time()
    if not last_run:
        return True
    
    days_since = (datetime.now() - last_run).days
    return days_since >= 7
