# Update controls and ticker maintenance

The admin Updates page is the control surface for Notion imports and the complete
central refresh. Both schedules are stored in SystemSettings. Notion defaults to
daily at 04:00 Europe/Prague (so it runs at least weekly); full recalculation keeps
its existing enabled state and Monday 04:00 default. Admins can enable/disable each
and select daily or weekly, a weekday and local hour/minute. Saving is validated,
CSRF-protected and atomic. The scheduler owner synchronizes settings every minute;
the saving web worker updates its own schedule too. No deploy is needed.

Notion's hourly catch-up respects its enabled state and scheduled slot, accepts a
successful manual import as satisfying that slot, and retries failed work after
an hour. The overnight central-refresh catch-up supports daily and weekly slots.
Both use the existing Prague timezone. Market quotes and email retries retain
their separate 15-minute schedules and are identified on the Updates page.

A new MaintenanceRun table records every manual/scheduled Notion attempt, including
unchanged data, failure details and counts. It is additive and created through the
existing schema initialization. Prior CsvUpload records remain visible and
paginated; do not infer a trigger type or fabricate missing historical output.
RecalculationLog remains the authority for recalculation history. Both histories
are merged chronologically with source/status filters and pagination, and each
run has a protected output page. All datetimes in the table display in Prague.

The full-refresh action uses the existing shared refresh modal and worker, never
the former long-lived SSE stream. Opening reports state; Start is an explicit
POST. If the latest attempt began within 24 hours, the administrator must check
an acknowledgement, and the admin POST enforces it too. A running job is joined,
not duplicated. The job retains the existing Flask application rather than
booting another instance. Progress is written from an isolated session every three
seconds and on exit: other web workers can show it, and complete logs remain
available later. State polls return a bounded log tail. Refreshing still computes
centrally and publishes snapshots; page loads never calculate.

Scheduler ownership remains protected by the existing application advisory lock.
A replacement instance waits while the former owner is alive, then its watchdog
acquires ownership and resumes jobs. A failed ownership query no longer grants
ownership. Scheduled and manual Notion imports also share an advisory lock, and
the complete publisher keeps its existing lock. Lock sessions are committed after
acquisition to avoid leaving a transaction open during network work. Last-job
bookkeeping now persists inside an app context even after the job context exits.

Ticker maintenance is a single list ordered by latest analysis date, with search,
entry-type filters and oldest/newest ordering. Entries with multiple analyses
expose all their dates. Analysis/Other buttons and symbol editing are explicit,
CSRF-protected admin POSTs. Manual symbol saves are fast and make no external
requests; explicit automatic lookup uses the existing resolver/validation. Bulk
lookup processes visible unresolved/automatic-update entries sequentially with
per-row feedback. On phones the rows become cards.

Names containing a hyphen/en dash/em dash followed by `update` are classified as
Other before sector hints or old automatic ticker mappings. Manual choices are
preserved. Importing an existing update entry revisits its automatic type too.
The explicit `classify_update_entries()` maintenance helper can repair previously
misclassified automatic entries without deleting analyses, votes or purchases;
it preserves a previous symbol in the mapping so a manual switch back can
restore it. Classification changes affect stored portfolio results at the next
central refresh, not by calculating during a page request.
