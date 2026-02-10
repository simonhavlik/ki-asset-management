# Neon.tech Optimization Guide

This guide explains how the KI Asset Management website is optimized for [Neon.tech](https://neon.tech) serverless PostgreSQL to minimize compute unit (CU) usage and costs.

## Overview

Neon.tech is a serverless PostgreSQL database that charges based on "compute units" (CU-hours). Every database query, connection, and transaction consumes CUs. By implementing aggressive caching, we can serve public-facing pages without hitting the database at all.

## How It Works

### 1. In-Memory Caching (SimpleCache)

The application uses Flask-Caching with `SimpleCache` (in-memory dictionary) to store frequently accessed data:

- **Public page data**: Homepage stats, portfolio charts, blog posts
- **Blog content**: Blog index, individual posts, RSS feed, sitemap
- **Ideas wall**: Stock ideas list

### 2. Cache Timeout Strategy

Different data types have different cache timeouts:

| Data Type | Timeout | Reason |
|-----------|---------|--------|
| Homepage stats | 1 hour | Changes infrequently |
| Portfolio charts | 1 hour | Updated by scheduler |
| Blog posts | 1 hour | Published content is static |
| RSS/Sitemap | 24 hours | Very static content |
| Ideas wall | 1 minute | Interactive, changes often |
| Health check | No DB hit | Returns static response |

### 3. Cache Invalidation

Caches are automatically invalidated when data changes:

- **Blog operations**: Publishing, unpublishing, deleting posts
- **Ideas wall**: Creating, editing, deleting ideas
- **CSV import**: All caches cleared after data import
- **Weekly refresh**: Full cache refresh every Friday at 11 PM

### 4. Health Check Endpoint

The `/health` endpoint returns a 200 OK response without querying the database:

```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T12:00:00",
  "neon_optimize": true
}
```

Use this for UptimeRobot or other monitoring services.

## Configuration

### Environment Variables

Add these to your `.env` file or Render environment:

```bash
# Enable Neon optimization (default: true)
NEON_OPTIMIZE=true

# Cache configuration
CACHE_TYPE=SimpleCache        # In-memory cache (best for Render)
CACHE_DEFAULT_TIMEOUT=300     # 5 minutes default
PUBLIC_DATA_CACHE_TIMEOUT=3600    # 1 hour for public data
STATIC_DATA_CACHE_TIMEOUT=86400   # 24 hours for static data
SHORT_CACHE_TIMEOUT=60            # 1 minute for interactive content
```

### Cache Types

#### SimpleCache (Recommended for Render)
- **Pros**: No external dependencies, works on Render free tier
- **Cons**: Cache is lost on app restart
- **Best for**: Single-instance deployments

#### FileSystemCache
```bash
CACHE_TYPE=FileSystemCache
CACHE_DIR=/tmp/flask_cache
```
- **Pros**: Persists across restarts
- **Cons**: Slower than memory, needs disk space

#### RedisCache (For high-traffic sites)
```bash
CACHE_TYPE=RedisCache
CACHE_REDIS_URL=redis://username:password@host:port/0
```
- **Pros**: Shared across instances, very fast
- **Cons**: Requires Redis service (additional cost)

## Monitoring

### View Cache Statistics

Add a simple route to check cache status:

```python
@app.route('/admin/cache-stats')
@login_required
def cache_stats():
    from app.utils.neon_cache import get_cache_stats
    return jsonify(get_cache_stats())
```

### Expected Behavior

With NEON_OPTIMIZE enabled:

1. **First request**: Hits database, stores in cache
2. **Subsequent requests**: Served from memory (no DB call)
3. **After data change**: Cache invalidated, next request hits DB
4. **Health checks**: No database queries

### Log Messages

Watch for these log messages:

```
# Cache hit (no DB call)
Cache HIT: main:stats

# Cache miss (DB call required)
Cache SET: main:stats

# Cache warming on startup
Warming public caches for Neon optimization...
Warmed: main_stats, portfolio_chart, growth_timeline, ...
```

## Performance Impact

### Before Optimization

Every page load generates multiple database queries:

```
Homepage: ~8-12 queries
Blog index: ~5-8 queries  
Blog post: ~3-5 queries
Ideas wall: ~2-4 queries
Health check: ~1 query (if checking DB)
```

### After Optimization

Cached pages serve from memory:

```
Homepage: 0 queries (after first load)
Blog index: 0 queries (after first load)
Blog post: 0 queries (after first load)
Ideas wall: 0 queries (after first load, 1 min TTL)
Health check: 0 queries (always)
```

### CU-Hours Savings

For a site with:
- 1000 page views/day
- 90% are public pages
- 10% are admin actions

**Estimated savings**: ~80-90% reduction in database queries

## Troubleshooting

### Cache Not Working

Check logs for:
```
NEON_OPTIMIZE is not enabled
```

Solution: Set `NEON_OPTIMIZE=true` in environment

### Stale Data

If you see old data after making changes:

1. Wait for automatic invalidation (immediate for most actions)
2. Or restart the app (clears in-memory cache)
3. Or trigger a manual cache clear (admin only)

### Memory Usage

SimpleCache stores data in Python memory. For sites with:
- < 1000 blog posts: ~50-100 MB
- < 10,000 ideas: ~20-50 MB

If memory is a concern, use FileSystemCache instead.

## Best Practices

1. **Always enable NEON_OPTIMIZE in production**
2. **Use /health for monitoring** (not a page that hits the DB)
3. **Keep cache timeouts reasonable** (balance freshness vs. performance)
4. **Monitor Render memory usage** (SimpleCache uses RAM)
5. **Invalidate caches on data changes** (automatic for most operations)

## Advanced: Manual Cache Control

### Clear All Caches

```python
from app.utils.neon_cache import invalidate_all_public_cache
invalidate_all_public_cache()
```

### Warm Caches Manually

```python
from app.utils.neon_cache import warm_public_caches
warmed = warm_public_caches()
print(f"Warmed: {warmed}")
```

### Check Cache Status

```python
from app.utils.neon_cache import get_cache_stats
stats = get_cache_stats()
print(stats)
# {
#   'neon_optimize_enabled': True,
#   'cache_type': 'SimpleCache',
#   'items_in_memory': 15
# }
```

## Migration Guide

### Existing Deployments

1. Add Flask-Caching to requirements:
   ```bash
   pip install Flask-Caching==2.3.0
   ```

2. Add environment variables to Render dashboard:
   ```
   NEON_OPTIMIZE=true
   ```

3. Deploy - caches will warm automatically on startup

4. Verify in logs:
   ```
   Warming public caches for Neon optimization...
   ```

### New Deployments

The optimization is enabled by default (`NEON_OPTIMIZE=true`). No action needed.

## Support

For issues or questions:

1. Check application logs for cache-related messages
2. Verify `NEON_OPTIMIZE=true` is set
3. Ensure Flask-Caching is installed: `pip show Flask-Caching`
4. Review Render memory usage if using SimpleCache

## Related Files

- `app/utils/neon_cache.py` - Core caching utilities
- `app/extensions.py` - Cache initialization
- `app/scheduler.py` - Weekly cache refresh
- `app/main/routes.py` - Cached public routes
- `app/blog/routes.py` - Cached blog routes