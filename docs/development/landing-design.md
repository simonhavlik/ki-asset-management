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
- The two additional team cards are visibly unfilled comment placeholders.
  Add identities, photos and quotations only after the comments are approved.

The hero retains the existing portfolio metrics. The separate chart is labelled
as an incremental model simulation so it is not mistaken for the headline metric.
Research selection, inline PDF viewing, phone open/download actions, charts,
section navigation and authenticated navigation retain their existing behavior.
Opening a page must never start a calculation; see calculation-snapshots.md in
`docs/operations`.

The market strip reads `site_market_tape` from SystemSettings. A separate 15-minute
scheduler job fetches quotes with the existing Yahoo Finance provider; page loads
never fetch quotes. Values are labelled delayed and stamped with the retrieval
time in Europe/Prague. A failed refresh retains the preceding snapshot. The
personal-site reference uses illustrative fixed numbers; do not copy those values.

The club-partners block defaults to the five logos on klubinvestoru.com, without
claiming sponsorship of KI AM capital. Admins see a link to `/admin/site-partners`.
The CSRF-protected form stores only `site_partners` in SystemSettings; empty lists
are respected, and admin-supplied URLs never cause server-side requests.
