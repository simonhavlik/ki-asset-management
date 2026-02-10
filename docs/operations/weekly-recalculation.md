# Weekly Recalculation System

## Overview

KI Asset Management automatically recalculates all performance data on a weekly basis to ensure accuracy and cache freshness. The system also supports manual recalculation by administrators.

## Automatic Weekly Recalculation

### Schedule
- **When**: Every Sunday at 3:00 AM UTC
- **What it does**:
  1. Recalculates performance for all approved analyses
  2. Clears all public caches (main page, blog, wall, board)
  3. Warms all caches with fresh data
  4. Updates the last recalculation timestamp

### Setup (Cron)

Add this line to your crontab (`crontab -e`):

```bash
# Weekly recalculation - Sundays at 3:00 AM UTC
0 3 * * 0 cd /home/simon/py/nmy/analyst_website 2.0 && python weekly_recalculation.py >> logs/weekly_recalculation.log 2>&1
```

Or use the system-wide cron:

```bash
sudo nano /etc/cron.d/ki-am-weekly
```

Add:
```
# KI Asset Management Weekly Recalculation
0 3 * * 0 root cd /home/simon/py/nmy/analyst_website 2.0 && /usr/bin/python3 weekly_recalculation.py >> /var/log/ki-am/weekly_recalculation.log 2>&1
```

### Manual Testing

You can test the recalculation without setting up cron:

```bash
# Check if recalculation is due
python weekly_recalculation.py --check-only

# Force recalculation (even if not due)
python weekly_recalculation.py --force

# Normal run (only if due)
python weekly_recalculation.py
```

## Manual Recalculation (Admin)

Administrators can trigger recalculation from the Board page:

1. Go to **Admin → Board**
2. Click the **"Recalculate Now"** button in the info alert
3. Confirm the action
4. Wait for completion (takes 10-60 seconds depending on data size)

### What Happens During Manual Recalculation

1. **Performance Calculation**: All approved analyses get their returns recalculated from analysis date to current date
2. **Cache Clearing**: All public-facing caches are cleared:
   - Main page stats and charts
   - Blog index and posts
   - Ideas wall
   - Board portfolio calculations
   - Overview page data
3. **Cache Warming**: Fresh data is pre-populated into caches for fast page loads
4. **Timestamp Update**: The last recalculation time is recorded

### Why Manual Recalculation?

Use manual recalculation when:
- You've added significant new data and want immediate updates
- You suspect cached data is stale or incorrect
- Testing the system after code changes
- Preparing for a presentation or demo

## Performance Optimization

### Caching Strategy

The platform uses aggressive caching to minimize database queries:

- **Main Page Data**: 1 hour cache
- **Portfolio Charts**: 1 hour cache  
- **Blog Posts**: 1 hour cache
- **Board Calculations**: 1 hour cache
- **Static Data** (sectors, categories): 24 hours

### Cache Invalidation

Caches are automatically invalidated:
- **On recalculation**: All caches cleared and warmed
- **On data changes**: Selective invalidation (e.g., new blog post invalidates blog cache)

### Performance Metrics

With caching enabled:
- Main page load: < 100ms (vs 2-5 seconds without cache)
- Board page load: < 200ms (vs 5-10 seconds without cache)
- Overview page load: < 300ms (vs 5-15 seconds without cache)

## Troubleshooting

### Recalculation Taking Too Long

If recalculation takes more than 5 minutes:

1. Check the logs:
   ```bash
   tail -f logs/weekly_recalculation.log
   ```

2. Look for database connection issues

3. Check if Yahoo Finance API is rate-limiting (if using live price fetching)

### Stale Data After Recalculation

If data appears stale after recalculation:

1. Clear browser cache (Ctrl+Shift+R)
2. Check server cache is being cleared:
   ```python
   from app.utils.neon_cache import invalidate_all_public_cache
   invalidate_all_public_cache()
   ```

3. Verify cache warming completed successfully

### Weekly Job Not Running

If the weekly job isn't running:

1. Check cron is installed and running:
   ```bash
   sudo systemctl status cron
   ```

2. Verify the cron entry:
   ```bash
   crontab -l
   ```

3. Check the log file for errors:
   ```bash
   tail logs/weekly_recalculation.log
   ```

4. Test the script manually:
   ```bash
   python weekly_recalculation.py --force
   ```

## Environment Variables

Control caching behavior with these environment variables:

```bash
# Enable/disable aggressive caching (default: true)
NEON_OPTIMIZE=true

# Cache timeouts (in seconds)
CACHE_DEFAULT_TIMEOUT=300
PUBLIC_DATA_CACHE_TIMEOUT=3600
STATIC_DATA_CACHE_TIMEOUT=86400
```

## Monitoring

Monitor recalculation status via:

1. **Board Page**: Shows last recalculation time
2. **Logs**: `logs/weekly_recalculation.log`
3. **Admin Dashboard**: Cache statistics (if implemented)

## Best Practices

1. **Don't recalculate during peak usage** - Schedule manual recalculation during low-traffic hours
2. **Monitor after recalculation** - Check that pages load correctly after cache refresh
3. **Keep logs** - Review weekly recalculation logs for errors
4. **Test periodically** - Run manual recalculation monthly to verify the system works
5. **Backup before major changes** - If making significant data changes, recalculate afterward
