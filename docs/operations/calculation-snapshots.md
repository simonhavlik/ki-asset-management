# Central calculated results

Normal GETs for `/`, `/analyst/`, `/admin/board` and `/analyst/overview`
never launch portfolio calculations. Overview's old `?refresh=true` link no
longer runs work. Explicit POST refresh buttons and the authenticated refresh API
still work. The detailed analyst performance page reuses the dashboard charts.

The weekly job (currently Monday 04:00 Europe/Prague) and explicit refreshes use
`full_recalc._run_full_recalculation`: update benchmarks and stock prices,
calculate all overview views, persist them, publish homepage and Board snapshots,
then publish dashboards for every active user. Team rankings are computed once
for that dashboard publishing pass. A PostgreSQL advisory lock covers the entire
pipeline across workers. A failed computation retains its previous snapshot.

`calculation_snapshots` contains the homepage/Board payloads; the existing
`analyst_dashboard_cache` and `overview_data_cache` hold the other views. Reads
serve the last stored result regardless of age. Expired process caches, restarts,
and deploys cannot force visitors to run calculations. A genuinely missing
snapshot renders an empty state until the next central publication.

Startup creates missing tables but never warms calculations. Bootstrap existing
deployments with `flask warm-cache` plus the dashboard publishing pass before
serving the new version; or trigger the full authenticated `/api/recalculate`.

A scheduler-only catch-up check runs at :15 between midnight and 05:15 Prague
time. It checks the latest successful full job against the configured weekly
slot and runs only if overdue. This is never called by a page view. Render free
still needs the existing uptime monitor for in-process scheduling and can still
cold-start when asleep; a paid always-on instance or external scheduler is needed
for a hard scheduling guarantee. HTML caching alone cannot repair this pipeline.

Diagnose with the authenticated `/api/jobs`, `/api/recalculate/status`, and cache
row timestamps. Never put API keys, database URLs, or env files in Git: the repo
is public. Local tests must use SQLite.
