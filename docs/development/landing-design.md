# Public landing page

The public homepage uses `landing.css`, scoped under `body.index-page`. Other
application pages retain their layout. The white/mint palette keeps #1a9c5e as the
primary green, with fine rules, compact data labels and a portfolio-led opening.
The decorative atmosphere is CSS only, can be paused, respects reduced motion,
and stays static on phones. It makes no data requests.

The homepage defaults to Czech; a saved language choice takes precedence. English
fallbacks and the existing language switch remain available. New copy belongs in
both dictionaries in `i18n.js`. Version the public asset URLs when updating them.

The September 2026 pitch deck is the editorial reference:

- Page 10: long-term target allocation is 40% SMID caps, 50% emerging markets,
  10% equity stories, at cost. These are targets, not live holdings weights.
- Page 15: position sizing and Committee voting changes are explicitly proposals.
  Do not present them as approved rules without confirmation of adoption.
- Historical portfolio values/returns from the deck must not replace the live
  centrally stored performance snapshot.
- Pages 9, 11 and 14 supply the visible strategy tools, universe criteria and
  four-stage investment process, including the decision gates. Preserve those
  details when editing copy; do not replace them with generic summaries.
- Page 8 supplies a separate potential-cooperation section, explicitly dated
  September 2026 and described as a proposal, not an agreed sponsorship.
- Keep Adam and Šimon's complete comments. Czech wording may be improved without
  discarding their meaning. The requested profile order is Adam Kolomazník,
  Tomáš Cverna, Šimon Havlík. Keep these three profiles until more are supplied.
  Tomáš's comment is based on the wording provided by the site owner.

The native cursor is used throughout the application. The former cursor overlay,
animation loop, hover listeners and CSS hiding the native cursor were removed.

The homepage defaults to Board-approved positions. Administrators choose approved
or purchased positions in the Board's public-homepage control. The setting selects
all return/risk/benchmark figures and both charts together. Both metric variants
are published centrally; changing the setting never calculates. The purchased
metric snapshot must exist before that source can be selected. An invalid setting
uses approved positions. Each series keeps the Board's existing date semantics.
Research selection, inline PDF viewing, phone open/download actions, charts,
section navigation and authenticated navigation retain their existing behavior.
Opening a page must never start a calculation; see calculation-snapshots.md in
`docs/operations`.

The opening viewport uses the measured fixed-header height, keeping the market
tape at its lower edge. Its three right-hand views are portfolio, team and the
investment process. The process repeats the complete existing process text; it
must not be reduced to two screening ratios or replaced by a publication list.
The default server-rendered view remains the portfolio. Optional motion starts
after first paint, stops offscreen/when hidden, respects reduced motion and has
manual pause and keyboard controls. The responsive team photograph is fetched
only when its view is selected. Particle density is reduced on phones; no
animation library or additional data endpoint is used.
The opening return also contains the same selected portfolio history shown in
the mission section. Both plots reuse the existing cached payload and one shared
deferred Chart.js load; the opening plot does not animate its initial draw.
All return, risk and benchmark figures remain visible.

The market strip reads `site_market_tape` from SystemSettings. A separate 15-minute
scheduler job fetches quotes with the existing Yahoo Finance provider; page loads
never fetch quotes. Values are labelled delayed and stamped with the retrieval
time in Europe/Prague. A failed refresh retains the preceding snapshot. The
personal-site reference uses illustrative fixed numbers; do not copy those values.

The club-partners block defaults to the five logos on klubinvestoru.com, without
claiming sponsorship of KI AM capital. Admins see a link to `/admin/site-partners`.
The CSRF-protected form stores only `site_partners` in SystemSettings; empty lists
are respected, and admin-supplied URLs never cause server-side requests.

The mission pairs full context on the left with history and three principles on
the right. The team context uses the same responsive WebP as the hero, loaded
lazily, above the three complete profiles. Phone density uses smaller gutters,
compact cards and two-column process/rule grids; no quotes or process details are
truncated. Tomáš's MSc studies at UGent are supplied by the site owner.
