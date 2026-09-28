"""Term scoring: the maths, the boundaries, and the leaderboard rules.

Terms are Feb 1 - Jul 31 and Aug 1 - Jan 31, chosen so the summer break is split
between them. Past terms are frozen as of their own end, all-time requires 3+
scored analyses for win rate, and individual terms do not.
"""

from datetime import date

import pytest

from app import create_app
from app.extensions import db
from app.utils import scoring


# --------------------------------------------------------------------------- #
# Term arithmetic
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize('day,expected_start', [
    ('2025-01-31', '2024-08-01'),
    ('2025-02-01', '2025-02-01'),
    ('2025-07-31', '2025-02-01'),
    ('2025-08-01', '2025-08-01'),
    ('2025-12-31', '2025-08-01'),
    ('2026-01-31', '2025-08-01'),
    ('2026-02-01', '2026-02-01'),
    ('2026-08-01', '2026-08-01'),
])
def test_every_day_belongs_to_the_term_that_contains_it(day, expected_start):
    d = date.fromisoformat(day)
    start = scoring.term_start_for(d)
    first, last = scoring.term_bounds(start)
    assert start == date.fromisoformat(expected_start)
    assert first <= d <= last, f'{day} is not inside {first}..{last}'


def test_terms_split_the_summer_break():
    """July ends one term, August starts the next - the break is not in one term."""
    july = scoring.term_bounds(scoring.term_start_for(date(2026, 7, 15)))
    august = scoring.term_bounds(scoring.term_start_for(date(2026, 8, 15)))
    assert july[1].month == 7 and august[0].month == 8
    assert july != august


def test_terms_are_six_months_and_contiguous():
    start = scoring.current_term(date(2026, 9, 28))
    for i in range(4):
        first, last = scoring.term_bounds(scoring.shift_term(start, -i - 1))
        nxt_first, _ = scoring.term_bounds(scoring.shift_term(start, -i))
        assert (nxt_first - last).days == 1, 'a gap or overlap between terms'


def test_current_and_last_term_labels():
    ref = date(2026, 9, 28)
    assert scoring.term_label(scoring.current_term(ref)) == 'Aug 2026 – Jan 2027'
    assert scoring.term_label(scoring.last_term(ref)) == 'Feb – Jul 2026'


def test_choices_start_with_all_time_then_the_current_term():
    choices = scoring.term_choices(back=2, ref=date(2026, 9, 28))
    assert choices[0]['key'] == 'all'
    assert choices[1]['key'] == '2026-08' and choices[1]['is_current']
    assert choices[2]['is_last']
    assert len(choices) == 4


def test_unknown_term_key_falls_back_to_the_current_term():
    ref = date(2026, 9, 28)
    assert scoring.resolve_term('nonsense', ref) == scoring.resolve_term('current', ref)


# --------------------------------------------------------------------------- #
# Leaderboards
# --------------------------------------------------------------------------- #
@pytest.fixture()
def app():
    application = create_app()
    with application.app_context():
        db.create_all()
        yield application


def _seed(app):
    """Two analysts with known analyses and returns in the Jul-2026 term."""
    from app.models import (Analysis, Company, PerformanceCalculation, User,
                            analysis_analysts)

    with app.app_context():
        from app.models import analysis_analysts
        db.session.execute(analysis_analysts.delete())
        for model in (PerformanceCalculation, Analysis, Company, User):
            model.query.delete()
        db.session.commit()

        company = Company(name='Test Co', ticker_symbol='TEST')
        db.session.add(company)
        db.session.commit()

        users = {}
        for email in ('ana@klubinvestoru.com', 'bob@klubinvestoru.com'):
            u = User(email=email, full_name=email.split('@')[0], is_active=True)
            u.set_password('irrelevant-password')
            db.session.add(u)
            users[email.split('@')[0]] = u
        db.session.commit()

        # ana: 3 analyses in Feb-Jul 2026 (2 approved), 1 in the current term
        # bob: 2 analyses in Feb-Jul 2026 (1 approved)
        plan = [
            ('ana', date(2026, 3, 10), 'On Watchlist', [10.0]),
            ('ana', date(2026, 4, 10), 'On Watchlist', [-5.0]),
            ('ana', date(2026, 6, 10), 'Refused', [20.0, 50.0]),   # second calc after the term
            ('ana', date(2026, 9, 10), 'On Watchlist', [3.0]),
            ('bob', date(2026, 5, 10), 'On Watchlist', [-3.0]),
            ('bob', date(2026, 6, 15), 'Refused', [-7.0]),
        ]
        for who, when, status, returns in plan:
            a = Analysis(company_id=company.id, analysis_date=when, status=status)
            db.session.add(a)
            db.session.commit()
            db.session.execute(analysis_analysts.insert().values(
                analysis_id=a.id, user_id=users[who].id, role='analyst'))
            for i, r in enumerate(returns):
                calc_date = when if i == 0 else date(2026, 8, 15)   # after the term
                db.session.add(PerformanceCalculation(
                    analysis_id=a.id, calculation_date=calc_date,
                    price_at_analysis=100, price_current=100 + r, return_pct=r))
        db.session.commit()
        return {k: v.id for k, v in users.items()}


def test_last_term_counts_only_that_term(app):
    ids = _seed(app)
    with app.app_context():
        boards = scoring.leaderboards(*scoring.term_bounds(date(2026, 2, 1)))

    by_total = {r['name']: r['value'] for r in boards['most_analyses']}
    assert by_total == {'ana': 3, 'bob': 2}, 'the September analysis must not count'

    by_approved = {r['name']: r['value'] for r in boards['most_approved']}
    assert by_approved == {'ana': 2, 'bob': 1}


def test_past_terms_are_frozen_as_of_their_end(app):
    """A calculation after the term ended must not change that term's table."""
    _seed(app)
    with app.app_context():
        term = scoring.leaderboards(*scoring.term_bounds(date(2026, 2, 1)))
        all_time = scoring.leaderboards()
    # In the term, ana's three analyses last read 10, -5 and 20 -> 8.33%.
    # The 50% recalculation (dated after the term ended) and the September
    # analysis must not leak into that table.
    ana_term = next(r for r in term['top_performance'] if r['name'] == 'ana')
    assert ana_term['value'] == pytest.approx((10 - 5 + 20) / 3)
    # All time uses the newest numbers: 10, -5, 50 and 3 -> 14.5%.
    ana_all = next(r for r in all_time['top_performance'] if r['name'] == 'ana')
    assert ana_all['value'] == pytest.approx((10 - 5 + 50 + 3) / 4)


def test_win_rate_uses_latest_calculation_per_analysis(app):
    _seed(app)
    with app.app_context():
        term = scoring.leaderboards(*scoring.term_bounds(date(2026, 2, 1)))
    rates = {r['name']: r['value'] for r in term['best_win_rate']}
    assert rates['ana'] == pytest.approx(200 / 3)   # +10 and +20 of three
    assert rates['bob'] == pytest.approx(0.0)       # both down


def test_all_time_win_rate_needs_three_analyses_but_terms_do_not(app):
    _seed(app)
    with app.app_context():
        all_time = scoring.leaderboards()
        term = scoring.leaderboards(*scoring.term_bounds(date(2026, 2, 1)))
    assert all_time['min_analyses_for_win_rate'] == 3
    assert 'bob' not in {r['name'] for r in all_time['best_win_rate']}, \
        'two scored analyses is not enough all-time'
    assert 'bob' in {r['name'] for r in term['best_win_rate']}, \
        'a term is short, so any scored analysis counts'


def test_empty_period_returns_empty_tables(app):
    _seed(app)
    with app.app_context():
        boards = scoring.leaderboards(date(2001, 1, 1), date(2001, 6, 30))
    assert boards['most_analyses'] == []
    assert boards['best_win_rate'] == []
    assert boards['top_performance'] == []


def test_term_overview_marks_all_time_and_current(app):
    _seed(app)
    with app.app_context():
        all_time = scoring.term_overview('all')
        current = scoring.term_overview('current')
    assert all_time['start'] is None and all_time['label_key'] == 'scoring.all_time'
    assert current['start'] is not None and current['label_key'] == 'scoring.current_term'
