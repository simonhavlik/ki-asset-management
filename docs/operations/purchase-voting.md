# Purchase voting

The authenticated `/voting/` tab is available to all active members. It is
separate from the admin Board and actual portfolio purchases. Creating a proposal
or voting never changes an existing Board vote, Notion entry, trade, price or
calculated portfolio result.

Default eligibility is On Watchlist/Portfolio, non-future and not Other, with
more YES than NO rows in the existing Board Vote table. This does not infer
Board approval from the imported analysis-meeting tally. Admins can explicitly
switch eligibility to the approved-status condition (On Watchlist/Portfolio,
without the Board vote requirement) from the page. Changes apply to new or
renewed proposals; active windows retain their original eligibility snapshot.
Only an analyst associated with the analysis in the `analyst` role can propose
it. Opponent membership and admin status alone do not grant authorship.

An author can promote any number of different companies. A unique author/company
recommendation persists across research updates and expiry. The initial window
is 7–30 days, measured from the current UTC time, displayed in Europe/Prague.
One active-member ballot per recommendation can be changed or removed. The
author can vote too. Active proposals sort by YES count descending, then expiry
and ID. Each page contains 25 proposals; there is no active-proposal limit.

Authors can extend an active window to a later deadline 7–30 days from now.
Expired/withdrawn windows appear in History automatically by date, without a
background job or GET writes. Authors can renew them, subject to current
eligibility. The recommendation ID and its YES/NO votes are retained, including
when a new analysis of the same company becomes the basis. Every renewal records
the prior dates, rationale, eligibility and carried YES/NO counts as an event;
the current recommendation returns to the active list. Details retain this
history. Withdrawal is reversible through renewal; nothing is deleted.

Three additive tables hold recommendations, unique ballots and append-only
events. PostgreSQL row locks serialize votes/window edits; a company lock plus
unique author/company constraint prevents parallel duplicate proposals.
Form validation, CSRF, login, active-account and ownership checks run server-side.
The eligibility setting save also writes an activity record.

Counts refresh every 30 seconds while the tab is visible (and on returning to
it), without pricing calls or analytics jobs. Polls avoid replacing a focused
form and use `no-store`. A failed poll displays a message instead of hiding the
last successful counts. All mutating forms work without JavaScript.
