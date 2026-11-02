# Analyst results and company statistics

Results summaries, per-analysis bars, analysis lists and cumulative-chart input
use `PerformanceCalculator.get_analyst_analysis_performance`. Filters include
`Portfolio` as well as `On Watchlist` (and optionally Neutral/Refused). Only past
or present stock analyses with a latest stored return and the analyst role enter
results. Multiple historical calculation rows do not multiply counts. Opponents,
Other events and future analyses are excluded. Same-company analyses on different
dates remain separate analyses; company fundamentals are deduplicated by company.
The leaderboard's total is analyst participations, not unique research reports.
Detail links retain both filter and annualization.

The cumulative chart calculation, monthly point generation, benchmark data and
1-year window rules are unchanged. Only the selection now agrees with its label.
Annualization affects individual returns and summary metrics; cumulative charts
retain raw returns. Zero returns are displayed, and names are JSON-escaped.

`company_fundamentals.refresh_fundamentals` is called by the shared full refresh
(scheduled and explicit). It uses the existing yahooquery library, not a second
market-data dependency. A combined quoteSummary request fetches price,
summaryDetail, defaultKeyStatistics, financialData and assetProfile together for
each ticker; batches contain up to ten symbols, with two concurrent requests.
It is one combined request **per company**, not one HTTP request for every ticker.
A same-day repeat skips already fresh snapshots. Failures retain previous saved
data. New central snapshots use `company-fundamentals:<symbol>` keys; there is no
schema migration or new service. No Notion data is changed.

Ordinary Results and detail GETs only read snapshots. The initial comparison
contains compact categories; clicking a company loads all 62 named metrics and
additional scalar Yahoo fields from a protected, cache-only route. This avoids
embedding every provider field for every company in the initial page. A cold
cache shows unavailable, never blocks on Yahoo or triggers a refresh.

Fields retain quote/financial currency. Fractional margins/yields are multiplied
by 100; Yahoo's debtToEquity and fiveYearAvgDividendYield are already percentage
points. Net debt is debt minus cash; debt/EBITDA requires positive EBITDA; FCF
yield requires matching quote and financial currencies. No missing value is
invented, and original provider ratios remain provider values. Some ratios are
unsuitable for banks/other sectors. Snapshot time is retrieval time, not the
financial period end; raw source fields include fiscal dates. These are current
statistics, not historical valuations at the date of the original analysis.
