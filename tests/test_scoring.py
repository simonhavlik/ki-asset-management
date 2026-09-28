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
        from app.models import Vote, analysis_analysts
        db.session.execute(analysis_analysts.delete())
        Vote.query.delete()          # orphans would attach to reused analysis ids
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


# --------------------------------------------------------------------------- #
# Distinct-company rankings and arbitrary date ranges
# --------------------------------------------------------------------------- #
def _seed_companies(app):
    """ana covers one company three times; bob covers two companies once each."""
    from app.models import (Analysis, Company, PerformanceCalculation, User,
                            analysis_analysts)

    with app.app_context():
        from app.models import PortfolioPurchase, Vote
        db.session.execute(analysis_analysts.delete())
        Vote.query.delete()
        PortfolioPurchase.query.delete()
        for model in (PerformanceCalculation, Analysis, Company, User):
            model.query.delete()
        db.session.commit()

        companies = {}
        for name in ('Alpha', 'Beta', 'Gamma'):
            c = Company(name=name, ticker_symbol=name[:3].upper())
            db.session.add(c)
            companies[name] = c
        db.session.commit()

        users = {}
        for key in ('ana', 'bob'):
            u = User(email=f'{key}@klubinvestoru.com', full_name=key, is_active=True)
            u.set_password('irrelevant-password')
            db.session.add(u)
            users[key] = u
        db.session.commit()

        plan = [
            ('ana', 'Alpha', date(2026, 3, 5), 'On Watchlist', True),
            ('ana', 'Alpha', date(2026, 4, 5), 'On Watchlist', False),
            ('ana', 'Alpha', date(2026, 5, 5), 'Refused', False),
            ('bob', 'Beta', date(2026, 3, 6), 'On Watchlist', True),
            ('bob', 'Gamma', date(2026, 4, 6), 'On Watchlist', True),
        ]
        for who, company, when, status, in_portfolio in plan:
            a = Analysis(company_id=companies[company].id, analysis_date=when,
                         status=status, is_in_portfolio=in_portfolio)
            db.session.add(a)
            db.session.commit()
            db.session.execute(analysis_analysts.insert().values(
                analysis_id=a.id, user_id=users[who].id, role='analyst'))
        db.session.commit()
        return {k: v.id for k, v in users.items()}


def test_company_rankings_count_companies_not_analyses(app):
    _seed_companies(app)
    with app.app_context():
        boards = scoring.leaderboards(*scoring.term_bounds(date(2026, 2, 1)))

    # ana filed three analyses but they are all the same company
    approved = {r['name']: r['value'] for r in boards['approved_companies']}
    assert approved == {'ana': 1, 'bob': 2}
    portfolio = {r['name']: r['value'] for r in boards['portfolio_companies']}
    assert portfolio == {'ana': 1, 'bob': 2}
    # while the analysis counts stay as filed
    counts = {r['name']: r['value'] for r in boards['most_analyses']}
    assert counts == {'ana': 3, 'bob': 2}


def test_term_list_stops_at_the_first_data(app):
    """No empty periods from years before the club had any analyses."""
    _seed(app)                      # earliest analysis: 2026-03-10
    with app.app_context():
        choices = scoring.term_choices(ref=date(2026, 9, 28))
    keys = [c['key'] for c in choices]
    assert keys[0] == 'all'
    assert keys[1] == '2026-08', 'the current term comes first'
    assert '2026-02' in keys, 'the term holding the first analysis is offered'
    assert '2025-08' not in keys and '2024-02' not in keys, 'empty periods offered'


def test_a_custom_range_is_honoured(app):
    _seed(app)
    with app.app_context():
        data = scoring.term_overview('custom', date_from='2026-03-01', date_to='2026-06-30')
    assert data['start'] == '2026-03-01' and data['end'] == '2026-06-30'
    assert {r['name']: r['value'] for r in data['most_analyses']} == {'ana': 3, 'bob': 2}
    # the September analysis is outside the window
    assert all(r['name'] != 'sep' for r in data['most_analyses'])


def test_a_reversed_custom_range_still_works(app):
    _seed(app)
    with app.app_context():
        flipped = scoring.term_overview('custom', date_from='2026-06-30', date_to='2026-03-01')
    assert flipped['start'] == '2026-03-01' and flipped['end'] == '2026-06-30'


def test_a_broken_custom_range_does_not_crash(app):
    _seed(app)
    with app.app_context():
        data = scoring.term_overview('custom', date_from='not-a-date', date_to='')
    assert data['start'] is None and data['end'] is None


def test_a_recorded_purchase_counts_as_being_in_the_portfolio(app):
    """Purchases live in portfolio_purchases; the admin flag is not always kept
    in sync, so counting the flag alone showed an empty table."""
    from app.models import Analysis, PortfolioPurchase

    ids = _seed_companies(app)
    with app.app_context():
        beta = Analysis.query.filter_by(company_id=Company.query.filter_by(name='Beta').first().id).first()
        db.session.add(PortfolioPurchase(analysis_id=beta.id, purchase_date=date(2026, 3, 20),
                                         added_by=ids['bob']))
        db.session.commit()
        boards = scoring.leaderboards(*scoring.term_bounds(date(2026, 2, 1)))
    portfolio = {r['name']: r['value'] for r in boards['portfolio_companies']}
    assert portfolio == {'ana': 1, 'bob': 2}, 'the purchase must count for its analyst'


from app.models import Company  # noqa: E402  (used by the test above)


def test_board_approval_is_the_board_vote_not_the_analyst_flag(app):
    """The two approvals are different things.

    Analyst approval is the analysts' own 'On Watchlist' mark. Board approval is
    the board's vote in the Board menu: yes votes must outnumber no votes. An
    analysis the analysts approved but the board rejected must not appear in the
    board-approved table (and vice versa).
    """
    from app.models import Analysis, User, Vote

    _seed_companies(app)
    with app.app_context():
        # Alpha (ana) is analyst-approved but the board votes it down
        alpha = Analysis.query.filter_by(status='On Watchlist').first()
        # Beta (bob) is analyst-approved and the board approves it 2:1
        beta = Analysis.query.join(Company).filter(Company.name == 'Beta').first()

        voters = User.query.limit(3).all()
        for i, voter in enumerate(voters):
            db.session.add(Vote(analysis_id=beta.id, user_id=voter.id, vote=(i < 2)))   # 2 yes, 1 no
            db.session.add(Vote(analysis_id=alpha.id, user_id=voter.id, vote=(i == 2)))  # 1 yes, 2 no
        db.session.commit()

        boards = scoring.leaderboards(*scoring.term_bounds(date(2026, 2, 1)))

    board_counts = {r['name']: r['value'] for r in boards['board_approved']}
    assert board_counts == {'bob': 1}, 'only the analysis the board voted for counts'

    analyst_counts = {r['name']: r['value'] for r in boards['most_approved']}
    assert analyst_counts == {'ana': 2, 'bob': 2}, 'analyst approval is unchanged'

    company_counts = {r['name']: r['value'] for r in boards['board_approved_companies']}
    assert company_counts == {'bob': 1}


def test_a_tied_board_vote_is_not_approval(app):
    from app.models import Analysis, User, Vote

    _seed_companies(app)
    with app.app_context():
        gamma = Analysis.query.join(Company).filter(Company.name == 'Gamma').first()
        voters = User.query.limit(2).all()
        for i, voter in enumerate(voters):
            db.session.add(Vote(analysis_id=gamma.id, user_id=voter.id, vote=(i == 0)))  # 1 yes, 1 no
        db.session.commit()
        boards = scoring.leaderboards(*scoring.term_bounds(date(2026, 2, 1)))
    assert boards['board_approved'] == [], 'a tie is not approval'
