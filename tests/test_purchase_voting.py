"""Purchase proposals have their own eligibility, time windows and ballot history."""
from datetime import date, datetime, timedelta
from uuid import uuid4
import pytest
from flask import g
from app import create_app
from app.extensions import db
from app.models import (Analysis, Company, CompanyTickerMapping, User, Vote, PortfolioPurchase, SystemSettings,
    PurchaseRecommendation as Proposal, PurchaseRecommendationVote as Ballot, PurchaseRecommendationEvent as Event,
    analysis_analysts)


@pytest.fixture()
def voting_case():
    app=create_app();app.config.update(TESTING=True,WTF_CSRF_ENABLED=False)
    @app.before_request
    def clear_test_login():
        g.pop('_login_user',None)
    with app.app_context():
        tag=uuid4().hex
        people=[User(email=f'{role}-{tag}@example.com',full_name=role,is_admin=role=='Admin',is_active=True)
                for role in ['Author','Voter','Admin']]
        db.session.add_all(people);db.session.flush()
        author,voter,admin=people
        companies=[];analyses=[]
        def add(name,status='On Watchlist',owner=author,role='analyst',yes=True,future=False,other=False):
            c=Company(name=f'{name} {tag}',ticker_symbol=name.upper());db.session.add(c);db.session.flush();companies.append(c)
            a=Analysis(company_id=c.id,status=status,analysis_date=date.today()+timedelta(days=10) if future else date.today()-timedelta(days=10))
            db.session.add(a);db.session.flush();analyses.append(a)
            db.session.execute(analysis_analysts.insert().values(analysis_id=a.id,user_id=owner.id,role=role))
            if yes is not None:db.session.add(Vote(analysis_id=a.id,user_id=admin.id,vote=yes))
            if other:db.session.add(CompanyTickerMapping(company_name=c.name,is_other_event=True))
            return a
        approved=add('approved');second=add('second');other_author=add('another',owner=voter)
        portfolio=add('portfolio',status='Portfolio',yes=None)
        tie=add('tie');db.session.add(Vote(analysis_id=tie.id,user_id=voter.id,vote=False))
        rejected=add('rejected',yes=False);future=add('future',future=True);event=add('event',other=True)
        opponent=add('opponent',role='opponent');neutral=add('neutral',status='Neutral')
        db.session.commit()
        old_setting=SystemSettings.query.filter_by(key='purchase_voting_eligibility').first()
        old_value=old_setting.value if old_setting else None
        if old_setting:db.session.delete(old_setting);db.session.commit()
        yield app,author,voter,admin,dict(approved=approved,second=second,other_author=other_author,portfolio=portfolio,tie=tie,rejected=rejected,future=future,event=event,opponent=opponent,neutral=neutral)
        aids=[a.id for a in analyses]
        pids=[p.id for p in Proposal.query.filter(Proposal.analysis_id.in_(aids)).all()]
        Event.query.filter(Event.recommendation_id.in_(pids)).delete(synchronize_session=False)
        Ballot.query.filter(Ballot.recommendation_id.in_(pids)).delete(synchronize_session=False)
        Proposal.query.filter(Proposal.id.in_(pids)).delete(synchronize_session=False)
        from app.models import ActivityLog
        ActivityLog.query.filter(ActivityLog.user_id.in_([u.id for u in people])).delete(synchronize_session=False)
        Vote.query.filter(Vote.analysis_id.in_(aids)).delete(synchronize_session=False)
        db.session.execute(analysis_analysts.delete().where(analysis_analysts.c.analysis_id.in_(aids)))
        Analysis.query.filter(Analysis.id.in_(aids)).delete(synchronize_session=False)
        CompanyTickerMapping.query.filter(CompanyTickerMapping.company_name.in_([c.name for c in companies])).delete(synchronize_session=False)
        Company.query.filter(Company.id.in_([c.id for c in companies])).delete(synchronize_session=False)
        User.query.filter(User.id.in_([u.id for u in people])).delete(synchronize_session=False)
        setting=SystemSettings.query.filter_by(key='purchase_voting_eligibility').first()
        if setting:db.session.delete(setting)
        if old_value is not None:db.session.add(SystemSettings(key='purchase_voting_eligibility',value=old_value,value_type='string'))
        db.session.commit()


def client_for(app,user=None):
    client=app.test_client()
    if user:
        with client.session_transaction() as s:s['_user_id']=str(user.id);s['_fresh']=True
    g.pop('_login_user',None)
    return client


def create(client,analysis,days=14):
    response=client.post('/voting/propose',data=dict(analysis_id=analysis.id,days=days,rationale='Why buy now <script>never run</script>'))
    assert response.status_code==303,response.get_data(as_text=True)
    return Proposal.query.filter_by(analysis_id=analysis.id).order_by(Proposal.id.desc()).first()


def test_visibility_eligibility_and_no_price_calls(voting_case,monkeypatch):
    from app.voting.service import eligible_analyses
    app,author,voter,admin,a=voting_case
    monkeypatch.setattr('yahooquery.Ticker',lambda *a,**k:pytest.fail('Voting must not call Yahoo'))
    assert client_for(app).get('/voting/').status_code in (302,401)
    client=client_for(app,author)
    for path in ['/voting/','/voting/approved','/voting/history','/voting/live']:
        assert client.get(path).status_code==200
    owned={row[0].id for row in eligible_analyses(author_id=author.id)}
    assert owned=={a['approved'].id,a['second'].id}
    # Opponent-only participation is never ownership; the generic query above
    # must omit it (keep this explicit to catch association-role regressions).
    assert a['opponent'].id not in owned
    assert '/voting/' in client.get('/analyst/').get_data(as_text=True)
    author.is_active=False;db.session.commit()
    assert client.get('/voting/').status_code in (401,403)
    author.is_active=True;db.session.commit()


def test_unlimited_distinct_proposals_duplicates_and_ownership(voting_case):
    app,author,voter,admin,a=voting_case;client=client_for(app,author)
    first=create(client,a['approved'],7);second=create(client,a['second'],30)
    assert first.id!=second.id and (second.expires_at-second.created_at).days==30
    assert first.eligibility_mode=='board' and first.board_yes==1 and first.board_no==0
    assert client.post('/voting/propose',data=dict(analysis_id=a['approved'].id,days=14)).status_code==409
    for key in ['other_author','portfolio','tie','rejected','future','event','opponent','neutral']:
        assert client.post('/voting/propose',data=dict(analysis_id=a[key].id,days=14)).status_code==403,key
    assert '<script>never run</script>' not in client.get('/voting/').get_data(as_text=True)
    assert Event.query.filter_by(recommendation_id=first.id,kind='created').count()==1


@pytest.mark.parametrize('days',[6,31,0,-1,'bad',''])
def test_proposal_window_validation(voting_case,days):
    app,author,voter,admin,a=voting_case
    assert client_for(app,author).post('/voting/propose',data=dict(analysis_id=a['approved'].id,days=days)).status_code==400
    assert Proposal.query.filter_by(author_id=author.id).count()==0


def test_vote_change_remove_and_no_financial_side_effects(voting_case):
    app,author,voter,admin,a=voting_case
    p=create(client_for(app,author),a['approved'])
    client=client_for(app,voter)
    before_votes=Vote.query.count();before_purchases=PortfolioPurchase.query.count()
    for value in ['yes','yes','no']:
        assert client.post(f'/voting/{p.id}/vote',data={'vote':value}).status_code==303
        assert Ballot.query.filter_by(recommendation_id=p.id,user_id=voter.id).count()==1
    assert Ballot.query.filter_by(recommendation_id=p.id).one().vote is False
    assert Event.query.filter_by(recommendation_id=p.id,kind='ballot').count()==2
    assert client.post(f'/voting/{p.id}/vote',data={'vote':'bogus'}).status_code==400
    assert client.post(f'/voting/{p.id}/vote',data={'vote':'remove'}).status_code==303
    assert Ballot.query.filter_by(recommendation_id=p.id).count()==0
    assert Vote.query.count()==before_votes and PortfolioPurchase.query.count()==before_purchases


def test_expiry_boundary_history_and_new_round(voting_case):
    app,author,voter,admin,a=voting_case
    p=create(client_for(app,author),a['approved'])
    client=client_for(app,voter);client.post(f'/voting/{p.id}/vote',data={'vote':'yes'})
    from app.voting.service import active,proposal_rows
    exact=datetime.utcnow();p.expires_at=exact;db.session.commit()
    assert not active(p,exact)
    assert client.post(f'/voting/{p.id}/vote',data={'vote':'no'}).status_code==409
    owner=client_for(app,author)
    assert owner.post(f'/voting/{p.id}/extend',data={'days':30}).status_code==409
    assert p.id not in [r['proposal'].id for r in proposal_rows(author.id)[0]]
    assert p.id in [r['proposal'].id for r in proposal_rows(author.id,True)[0]]
    assert Ballot.query.filter_by(recommendation_id=p.id).one().vote is True
    fresh=create(owner,a['approved'])
    assert fresh.id==p.id and Ballot.query.filter_by(recommendation_id=fresh.id).count()==1
    assert Event.query.filter_by(recommendation_id=p.id,kind='renewed').one().details['carried_yes']==1
    assert owner.get(f'/voting/{p.id}').status_code==200


def test_extend_owner_only_retains_votes_and_audit(voting_case):
    app,author,voter,admin,a=voting_case
    p=create(client_for(app,author),a['approved']);old=p.expires_at
    voter_client=client_for(app,voter);voter_client.post(f'/voting/{p.id}/vote',data={'vote':'yes'})
    assert voter_client.post(f'/voting/{p.id}/extend',data={'days':30}).status_code==403
    assert client_for(app,admin).post(f'/voting/{p.id}/extend',data={'days':30}).status_code==403
    owner=client_for(app,author)
    assert owner.post(f'/voting/{p.id}/extend',data={'days':7}).status_code==400
    assert owner.post(f'/voting/{p.id}/extend',data={'days':31}).status_code==400
    assert owner.post(f'/voting/{p.id}/extend',data={'days':30}).status_code==303
    assert p.expires_at>old and Ballot.query.filter_by(recommendation_id=p.id).count()==1
    assert Event.query.filter_by(recommendation_id=p.id,kind='extended').one().details['previous']==old.isoformat()
    assert voter_client.post(f'/voting/{p.id}/withdraw').status_code==403
    assert owner.post(f'/voting/{p.id}/withdraw').status_code==303
    assert p.withdrawn_at is not None
    assert owner.post(f'/voting/{p.id}/vote',data={'vote':'yes'}).status_code==409


def test_rank_live_and_admin_condition(voting_case):
    from app.voting.service import proposal_rows,eligibility_mode
    app,author,voter,admin,a=voting_case
    owner=client_for(app,author);p=create(owner,a['approved']);q=create(owner,a['second'])
    client=client_for(app,voter);client.post(f'/voting/{q.id}/vote',data={'vote':'yes'})
    assert proposal_rows(voter.id)[0][0]['proposal'].id==q.id
    live=client.get('/voting/live');assert live.status_code==200 and live.json['total']==2
    assert live.headers['Cache-Control']=='no-store'
    assert client.post('/voting/settings',data={'mode':'approved'}).status_code==403
    admin_client=client_for(app,admin)
    assert admin_client.post('/voting/settings',data={'mode':'anything'}).status_code==400
    assert admin_client.post('/voting/settings',data={'mode':'approved'}).status_code==303
    assert eligibility_mode()=='approved'
    owner=client_for(app,author);new=create(owner,a['portfolio'])
    assert new.eligibility_mode=='approved'
    assert p.eligibility_mode=='board' and p.withdrawn_at is None
    admin_client=client_for(app,admin);admin_client.post('/voting/settings',data={'mode':'board'})
    assert new.id in [r['proposal'].id for r in proposal_rows(author.id)[0]]


def test_csrf_required_on_all_mutations(voting_case):
    app,author,voter,admin,a=voting_case
    p=create(client_for(app,author),a['approved'])
    app.config['WTF_CSRF_ENABLED']=True
    client=client_for(app,admin)
    for path,data in [('/voting/settings',{'mode':'approved'}),('/voting/propose',{'analysis_id':a['approved'].id,'days':14}),
                      (f'/voting/{p.id}/vote',{'vote':'yes'}),(f'/voting/{p.id}/extend',{'days':30}),
                      (f'/voting/{p.id}/withdraw',{})]:
        assert client.post(path,data=data).status_code==400


def test_direct_renew_retains_votes_and_rechecks_eligibility(voting_case):
    app,author,voter,admin,a=voting_case
    owner=client_for(app,author);p=create(owner,a['approved'])
    client_for(app,voter).post(f'/voting/{p.id}/vote',data={'vote':'no'})
    p.expires_at=datetime.utcnow()-timedelta(seconds=1);db.session.commit()
    assert client_for(app,voter).post(f'/voting/{p.id}/renew',data={'days':14}).status_code==403
    owner=client_for(app,author)
    assert owner.post(f'/voting/{p.id}/renew',data={'days':31}).status_code==400
    Vote.query.filter_by(analysis_id=a['approved'].id).update({'vote':False});db.session.commit()
    assert owner.post(f'/voting/{p.id}/renew',data={'days':14}).status_code==403
    Vote.query.filter_by(analysis_id=a['approved'].id).update({'vote':True});db.session.commit()
    assert owner.post(f'/voting/{p.id}/renew',data={'days':14}).status_code==303
    assert Ballot.query.filter_by(recommendation_id=p.id).one().vote is False
    assert p.expires_at>datetime.utcnow()
    assert owner.post(f'/voting/{p.id}/renew',data={'days':14}).status_code==409


def test_reanalysis_of_same_company_reuses_recommendation(voting_case):
    app,author,voter,admin,a=voting_case
    owner=client_for(app,author);p=create(owner,a['approved'])
    client_for(app,voter).post(f'/voting/{p.id}/vote',data={'vote':'yes'})
    newer=Analysis(company_id=a['approved'].company_id,status='On Watchlist',analysis_date=date.today())
    db.session.add(newer);db.session.flush()
    db.session.execute(analysis_analysts.insert().values(analysis_id=newer.id,user_id=author.id,role='analyst'))
    db.session.add(Vote(analysis_id=newer.id,user_id=admin.id,vote=True));db.session.commit()
    try:
        owner=client_for(app,author)
        assert owner.post('/voting/propose',data={'analysis_id':newer.id,'days':14}).status_code==409
        p.expires_at=datetime.utcnow()-timedelta(seconds=1);db.session.commit()
        assert owner.post('/voting/propose',data={'analysis_id':newer.id,'days':14}).status_code==303
        assert p.analysis_id==newer.id and Ballot.query.filter_by(recommendation_id=p.id).one().vote is True
        assert Proposal.query.filter_by(author_id=author.id,company_id=p.company_id).count()==1
    finally:
        p.analysis_id=a['approved'].id;db.session.flush()
        Vote.query.filter_by(analysis_id=newer.id).delete()
        db.session.execute(analysis_analysts.delete().where(analysis_analysts.c.analysis_id==newer.id))
        db.session.delete(newer);db.session.commit()
