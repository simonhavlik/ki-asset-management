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

## Private attachments

Authors and admins can attach files from the recommendation detail, including
archived recommendations. All active signed-in members can download them.
Attachments stay with the author/company recommendation when it is renewed.
The compact list shows only a count/link; it never fetches object bytes or signs
URLs while listing recommendations.

The dedicated private R2 bucket is `kiam-private-attachments`, with public r2.dev
access disabled and no custom domain. A dedicated object read/write token is
scoped only to that bucket. Its S3 credentials are stored in Render's
`KIAM_R2_ENDPOINT`, `KIAM_R2_ACCESS_KEY_ID`, `KIAM_R2_SECRET_ACCESS_KEY` and
`KIAM_R2_BUCKET` variables. The Cloudflare administrative credential is not used
by the app. Never commit real values or put them in logs or Honcho progress.

The DB stores only metadata: filename, key, byte size, content type, checksum,
uploader, recommendation and upload time. Binaries go directly from the request
stream to R2, not into PostgreSQL. The DB connection is released before network
upload; a second locked quota/digest check precedes the metadata commit. Failed
metadata saves clean up the newly uploaded object. Duplicate content is rejected.
A fourth additive metadata table is initialized by the existing schema setup.

Limits: 20 MiB per file, 20 files and 100 MiB per recommendation. Supported files
are PDF, PNG/JPEG/WebP/GIF, DOCX/XLSX/PPTX, UTF-8 CSV and TXT. Extensions and file
signatures/containers are checked; Office archive entry/uncompressed size limits
and macro checks apply. The app's existing 32 MiB request limit remains in place.

Downloads first require app authentication and then redirect to an attachment-
disposition signed URL valid for 60 seconds. File bytes bypass Render's response
workers. Request files may use Flask's temporary spool during upload, but no
persistent attachment depends on Render's ephemeral disk. Storage failures affect
only the explicit file action; voting and cached financial views keep working.
