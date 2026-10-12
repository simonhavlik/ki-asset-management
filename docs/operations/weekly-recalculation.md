# Weekly Recalculation System

## Overview

KI Asset Management automatically recalculates all performance data on a weekly basis to ensure accuracy and cache freshness. The system also supports manual recalculation by administrators.

## Automatic Background Jobs

Both jobs are scheduled **in-process** by the running app (APScheduler — see
`app/scheduler.py`), in **Europe/Prague** local time. Production is a Render free
instance that sleeps when idle, so it is kept awake by an uptime monitor pinging
`/health`; that keep-alive is what lets the 04:00 jobs fire.

### Schedule

| Job | When | What it does |
|---|---|---|
| **Notion import** (`daily_notion_import`) | every day, **04:00** | Pulls the Notion "Analysis Schedule" database into the analyses table (read-only against Notion). Drops the public page caches when rows changed. |
| **Full recalculation** (`automated_recalc`) | **Monday, 04:00** | Refreshes stock + benchmark prices, recalculates performance, rebuilds and re-warms the overview / board / dashboard caches, and refreshes the presentation exports. |

They share a lock, so they never touch the database at the same time (they share
the 04:00 slot on Monday).

### Changing the recalculation schedule

Admins set the day / hour / minute from **Admin → Unified Update → Automated
Recalculation Settings** (`SystemSettings`). The change takes effect when the app
next starts or when the settings are saved. The daily Notion import is
deliberately *not* gated on that toggle — keeping the site in step with Notion is
the point of the job.

### Watching the jobs

Both jobs log to the application log, which Render captures. Read it back with:

```bash
python scripts/render_logs.py --text "Notion import"
python scripts/render_logs.py --text "refresh completed"
```

### Manual Testing

You can run the recalculation by hand without waiting for the schedule:

```bash
# Check if recalculation is due
python weekly_recalculation.py --check-only

# Force recalculation (even if not due)
python weekly_recalculation.py --force

# Normal run (only if due)
python weekly_recalculation.py
```

`weekly_recalculation.py` is a standalone entry point for a self-hosted box that
has cron instead of the in-process scheduler; production does not use it.


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
