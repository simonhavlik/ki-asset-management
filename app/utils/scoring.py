"""Per-term analyst scoring for the overview leaderboards.

Terms are six months long and aligned to the Czech academic year, with the
boundary placed so the summer break is split between the two terms rather than
falling entirely inside one:

    Feb 1 - Jul 31   summer semester plus the first half of the holidays
    Aug 1 - Jan 31   the second half of the holidays plus the winter semester

Everything is derived from TERM_START_MONTH, so moving the split (e.g. to
September/October) is a one-line change.

Past terms are scored as of their own end date, not "today": a leaderboard for a
term that finished in July must not keep changing. All-time scoring uses the
latest calculations and requires a minimum number of analyses before an analyst
can top the win-rate table; the individual terms are short, so they do not.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta

from sqlalchemy import case, func
from sqlalchemy.orm import aliased

from ..extensions import db
from ..models import Analysis, PerformanceCalculation, User, analysis_analysts

# February: terms are Feb-Jul and Aug-Jan. Change to 8 for Aug-Jan/Feb-Jul, etc.
TERM_START_MONTH = 2
TERM_LENGTH_MONTHS = 6

# Win rate is a coin flip on two analyses; only demand the minimum when we are
# scoring everything ever done. Terms are exempt on purpose.
WIN_RATE_MIN_ANALYSES_ALL_TIME = 3

TOP_N = 5
ALL_TIME = 'all'


# --------------------------------------------------------------------------- #
# Term arithmetic
# --------------------------------------------------------------------------- #
def _add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def term_boundary_months() -> tuple[int, int]:
    """The two month numbers a term can start in (e.g. February and August)."""
    second = (TERM_START_MONTH - 1 + TERM_LENGTH_MONTHS) % 12 + 1
    return TERM_START_MONTH, second


def term_start_for(d: date) -> date:
    """Start of the term containing ``d``.

    Picks the latest boundary on or before ``d`` from the surrounding years,
    which stays correct whatever TERM_START_MONTH is set to. (A simple
    "month >= start" check put December into the February term.)
    """
    candidates = [
        date(year, month, 1)
        for year in (d.year - 1, d.year, d.year + 1)
        for month in term_boundary_months()
    ]
    return max(c for c in candidates if c <= d)


def term_bounds(start: date) -> tuple[date, date]:
    """(first day, last day) of the term beginning at ``start``."""
    first = start.replace(day=1)
    end = _add_months(first, TERM_LENGTH_MONTHS) - timedelta(days=1)
    return first, end


def shift_term(start: date, terms: int) -> date:
    return _add_months(start.replace(day=1), terms * TERM_LENGTH_MONTHS)


def term_key(start: date) -> str:
    return f'{start.year:04d}-{start.month:02d}'


def term_label(start: date) -> str:
    first, last = term_bounds(start)
    if first.year == last.year:
        return f'{first.strftime("%b")} – {last.strftime("%b")} {last.year}'
    return f'{first.strftime("%b")} {first.year} – {last.strftime("%b")} {last.year}'


def current_term(ref: date | None = None) -> date:
    return term_start_for(ref or date.today())


def last_term(ref: date | None = None) -> date:
    return shift_term(current_term(ref), -1)


def earliest_analysis_date() -> date | None:
    """Oldest analysis in the database, so the term list does not offer empty
    periods from years before the club had any data."""
    try:
        return db.session.query(func.min(Analysis.analysis_date)).scalar()
    except Exception:
        return None


def term_choices(back: int = 12, ref: date | None = None,
                 earliest: date | None = None) -> list[dict]:
    """All time, then the current term, the previous one, and older ones that
    can actually contain data."""
    this = current_term(ref)
    if earliest is None:
        earliest = earliest_analysis_date()
    oldest = term_start_for(earliest) if earliest else shift_term(this, -back)
    choices = [{'key': ALL_TIME, 'label_key': 'scoring.all_time', 'label': 'All time'}]
    for i in range(back + 1):
        start = shift_term(this, -i)
        if start < oldest:
            break
        first, last = term_bounds(start)
        key = term_key(start)
        choices.append({
            'key': key,
            'label_key': None,
            'label': term_label(start),
            'start': first.isoformat(),
            'end': last.isoformat(),
            'is_current': i == 0,
            'is_last': i == 1,
        })
    return choices


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip())
    except Exception:
        return None


def resolve_term(key: str | None, ref: date | None = None,
                 date_from: str | None = None, date_to: str | None = None
                 ) -> tuple[date | None, date | None]:
    """Map a ``?term=`` key to (start, end); (None, None) means all time.

    ``term=custom`` uses the from/to date inputs, so any window is possible, not
    just the six-month terms.
    """
    if key == 'custom':
        start, end = _parse_date(date_from), _parse_date(date_to)
        if start and end and start > end:
            start, end = end, start
        return start, end
    if not key or key == ALL_TIME:
        return None, None
    if key == 'current':
        return term_bounds(current_term(ref))
    if key == 'last':
        return term_bounds(last_term(ref))
    try:
        year, month = (int(part) for part in key.split('-'))
        return term_bounds(date(year, month, 1))
    except Exception:
        return term_bounds(current_term(ref))


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def _name(full_name: str | None, email: str | None) -> str:
    return (full_name or (email or '').split('@')[0] or '—').strip()


def _latest_calculation_on_or_before(cutoff: date):
    """Latest performance row per analysis, as of ``cutoff``.

    A correlated max() rather than DISTINCT ON, so the same code runs on
    PostgreSQL in production and SQLite in the test suite.
    """
    other = aliased(PerformanceCalculation)
    return (
        db.session.query(func.max(other.calculation_date))
        .filter(other.analysis_id == PerformanceCalculation.analysis_id,
                other.calculation_date <= cutoff)
        .correlate(PerformanceCalculation)
        .scalar_subquery()
    )


def _activity_rows(start: date | None, end: date | None) -> dict[int, dict]:
    q = (
        db.session.query(
            User.id.label('user_id'),
            User.full_name.label('full_name'),
            User.email.label('email'),
            func.count(func.distinct(Analysis.id)).label('total'),
            func.sum(case((Analysis.status == 'On Watchlist', 1), else_=0)).label('approved'),
            # distinct companies, not analyses: one analyst covering the same name
            # three times has still added one company to the portfolio
            func.count(func.distinct(case((Analysis.is_in_portfolio.is_(True),
                                           Analysis.company_id)))).label('portfolio_companies'),
            func.count(func.distinct(case((Analysis.status == 'On Watchlist',
                                           Analysis.company_id)))).label('approved_companies'),
        )
        .select_from(Analysis)
        .join(analysis_analysts, analysis_analysts.c.analysis_id == Analysis.id)
        .join(User, User.id == analysis_analysts.c.user_id)
        .filter(analysis_analysts.c.role == 'analyst')
        .group_by(User.id, User.full_name, User.email)
    )
    if start:
        q = q.filter(Analysis.analysis_date >= start)
    if end:
        q = q.filter(Analysis.analysis_date <= end)

    out: dict[int, dict] = {}
    for row in q.all():
        out[row.user_id] = {
            'user_id': row.user_id,
            'name': _name(row.full_name, row.email),
            'total': int(row.total or 0),
            'approved': int(row.approved or 0),
            'portfolio_companies': int(row.portfolio_companies or 0),
            'approved_companies': int(row.approved_companies or 0),
            'avg_return': None,
            'wins': 0,
            'scored': 0,
        }
    return out


def _performance_rows(start: date | None, end: date | None, cutoff: date) -> dict[int, dict]:
    latest = _latest_calculation_on_or_before(cutoff)
    q = (
        db.session.query(
            User.id.label('user_id'),
            User.full_name.label('full_name'),
            User.email.label('email'),
            func.avg(PerformanceCalculation.return_pct).label('avg_return'),
            func.sum(case((PerformanceCalculation.return_pct > 0, 1), else_=0)).label('wins'),
            func.count(PerformanceCalculation.id).label('scored'),
        )
        .select_from(PerformanceCalculation)
        .join(Analysis, Analysis.id == PerformanceCalculation.analysis_id)
        .join(analysis_analysts, analysis_analysts.c.analysis_id == Analysis.id)
        .join(User, User.id == analysis_analysts.c.user_id)
        .filter(analysis_analysts.c.role == 'analyst')
        .filter(PerformanceCalculation.calculation_date == latest)
        .group_by(User.id, User.full_name, User.email)
    )
    if start:
        q = q.filter(Analysis.analysis_date >= start)
    if end:
        q = q.filter(Analysis.analysis_date <= end)

    out: dict[int, dict] = {}
    for row in q.all():
        out[row.user_id] = {
            'user_id': row.user_id,
            'name': _name(row.full_name, row.email),
            'avg_return': float(row.avg_return) if row.avg_return is not None else None,
            'wins': int(row.wins or 0),
            'scored': int(row.scored or 0),
        }
    return out


def _rank(entries: list[dict], key, *, reverse: bool, fmt, limit: int = TOP_N) -> list[dict]:
    ranked = [e for e in entries if e.get('value') is not None]
    ranked.sort(key=key, reverse=reverse)
    return [
        {'rank': i, 'name': e['name'], 'user_id': e['user_id'], 'value': e['value'],
         'value_display': fmt(e['value']), 'detail': e.get('detail', '')}
        for i, e in enumerate(ranked[:limit], 1)
    ]


def leaderboards(start: date | None = None, end: date | None = None,
                 min_analyses_for_win_rate: int | None = None) -> dict:
    """Four leaderboards for one period (``None`` bounds = all time)."""
    today = date.today()
    # A term that has finished is frozen as of its last day.
    cutoff = min(end, today) if end else today
    if min_analyses_for_win_rate is None:
        min_analyses_for_win_rate = WIN_RATE_MIN_ANALYSES_ALL_TIME if not end else 1

    merged = _activity_rows(start, end)
    for user_id, perf in _performance_rows(start, end, cutoff).items():
        row = merged.setdefault(user_id, {
            'user_id': user_id, 'name': perf['name'], 'total': 0, 'approved': 0,
        })
        row.update({'avg_return': perf['avg_return'], 'wins': perf['wins'],
                    'scored': perf['scored']})
        row['name'] = row.get('name') or perf['name']
    for row in merged.values():
        row.setdefault('avg_return', None)
        row.setdefault('wins', 0)
        row.setdefault('scored', 0)
        row.setdefault('portfolio_companies', 0)
        row.setdefault('approved_companies', 0)

    entries = list(merged.values())

    by_approved = []
    for e in entries:
        if e['approved']:
            by_approved.append({**e, 'value': e['approved'],
                                'detail': f"{e['total']} analyses"})
    by_total = []
    for e in entries:
        if e['total']:
            by_total.append({**e, 'value': e['total'],
                             'detail': f"{e['approved']} board approved"})
    by_portfolio = []
    for e in entries:
        if e['portfolio_companies']:
            by_portfolio.append({**e, 'value': e['portfolio_companies'],
                                 'detail': f"{e['total']} analyses"})
    by_approved_companies = []
    for e in entries:
        if e['approved_companies']:
            by_approved_companies.append({**e, 'value': e['approved_companies'],
                                          'detail': f"{e['approved']} approved analyses"})
    by_return = []
    for e in entries:
        if e['avg_return'] is not None and e['scored']:
            by_return.append({**e, 'value': e['avg_return'],
                              'detail': f"{e['scored']} scored"})
    by_winrate = []
    for e in entries:
        if e['scored'] >= max(1, min_analyses_for_win_rate):
            by_winrate.append({**e, 'value': 100.0 * e['wins'] / e['scored'],
                               'detail': f"{e['wins']}/{e['scored']} up"})

    return {
        'start': start.isoformat() if start else None,
        'end': end.isoformat() if end else None,
        'min_analyses_for_win_rate': min_analyses_for_win_rate,
        'total_analysts': len([e for e in entries if e['total'] or e['scored']]),
        'most_approved': _rank(by_approved, lambda e: (e['value'], e['total'], e['name']),
                               reverse=True, fmt=lambda v: f'{v:g}'),
        'most_analyses': _rank(by_total, lambda e: (e['value'], e['name']),
                               reverse=True, fmt=lambda v: f'{v:g}'),
        'portfolio_companies': _rank(by_portfolio, lambda e: (e['value'], e['name']),
                                     reverse=True, fmt=lambda v: f'{v:g}'),
        'approved_companies': _rank(by_approved_companies, lambda e: (e['value'], e['name']),
                                    reverse=True, fmt=lambda v: f'{v:g}'),
        'top_performance': _rank(by_return, lambda e: (e['value'], e['name']),
                                 reverse=True, fmt=lambda v: f'{v:+.1f}%'),
        'best_win_rate': _rank(by_winrate, lambda e: (e['value'], e['scored'], e['name']),
                               reverse=True, fmt=lambda v: f'{v:.0f}%'),
    }


def term_overview(key: str | None = None, ref: date | None = None,
                  date_from: str | None = None, date_to: str | None = None) -> dict:
    """Everything the template needs for the selected term or custom range."""
    start, end = resolve_term(key, ref, date_from, date_to)
    data = leaderboards(start, end)
    if start is None and end is None:
        label = 'All time'
        label_key = 'scoring.all_time'
    elif key == 'custom':
        label = f'{start.isoformat() if start else "…"} – {end.isoformat() if end else "…"}'
        label_key = None
    else:
        label = term_label(start)
        label_key = None
    data['label'] = label
    data['label_key'] = label_key
    this = current_term(ref)
    if start == this:
        data['label_key'] = 'scoring.current_term'
    elif start == shift_term(this, -1):
        data['label_key'] = 'scoring.last_term'
    return data
