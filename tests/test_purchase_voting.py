"""Purchase proposals have their own eligibility, time windows and ballot history."""
from datetime import date, datetime, timedelta
from uuid import uuid4
import pytest
from flask import g
from app import create_app
from app.extensions import db
from app.models import (Analysis, Company, CompanyTickerMapping, User, Vote, PortfolioPurchase, SystemSettings,
    PurchaseRecommendationAttachment as Attachment, PurchaseRecommendation as Proposal, PurchaseRecommendationVote as Ballot, PurchaseRecommendationEvent as Event,
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
        Attachment.query.filter(Attachment.recommendation_id.in_(pids)).delete(synchronize_session=False)
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


@pytest.fixture()
def fake_attachment_storage(monkeypatch):
    from app.voting import storage
    class Fake:
        def __init__(self):self.objects={};self.puts=0;self.signed=0
        def put_object(self,**kwargs):self.objects[kwargs['Key']]=kwargs['Body'].read();self.puts+=1
        def delete_object(self,**kwargs):self.objects.pop(kwargs['Key'],None)
        def generate_presigned_url(self,operation,Params,ExpiresIn):
            assert operation=='get_object' and ExpiresIn==60
            assert Params['ResponseContentDisposition'].startswith('attachment;')
            self.signed+=1
            return 'https://storage.example.invalid/private-download?temporary=1'
    fake=Fake();monkeypatch.setattr(storage,'configured',lambda:True)
    monkeypatch.setattr(storage,'client',lambda:fake);monkeypatch.setattr(storage,'setting',lambda name:'private-test-bucket')
    return fake


def test_attachments_owner_upload_private_download_and_renewal(voting_case,fake_attachment_storage):
    import io
    app,author,voter,admin,a=voting_case
    owner=client_for(app,author);p=create(owner,a['approved'])
    payload=b'%PDF-1.4\nExample attachment\n%%EOF'
    def data():return {'file':(io.BytesIO(payload),'../Příloha.pdf')}
    assert client_for(app,voter).post(f'/voting/{p.id}/attachments',data=data()).status_code==403
    owner=client_for(app,author)
    assert owner.post(f'/voting/{p.id}/attachments',data=data()).status_code==303
    row=Attachment.query.filter_by(recommendation_id=p.id).one()
    assert row.filename=='Příloha.pdf' and row.size_bytes==len(payload)
    assert row.content_type=='application/pdf' and row.object_key.startswith(f'purchase-recommendations/{p.id}/')
    assert len(fake_attachment_storage.objects)==1
    assert 'Příloha.pdf' in owner.get(f'/voting/{p.id}').get_data(as_text=True)
    assert owner.post(f'/voting/{p.id}/attachments',data=data()).status_code==409
    assert fake_attachment_storage.puts==1
    assert client_for(app).get(f'/voting/attachments/{row.id}/download').status_code in (302,401)
    # An authenticated voter can download; signing does not proxy the file via Flask.
    member=client_for(app,voter)
    response=member.get(f'/voting/attachments/{row.id}/download')
    assert response.status_code==302 and response.location.startswith('https://storage.example.invalid/')
    assert fake_attachment_storage.signed==1 and response.headers['Cache-Control']=='no-store'
    p.expires_at=datetime.utcnow()-timedelta(seconds=1);db.session.commit()
    owner=client_for(app,author)
    assert owner.post(f'/voting/{p.id}/renew',data={'days':14}).status_code==303
    assert Attachment.query.filter_by(recommendation_id=p.id).count()==1
    assert Event.query.filter_by(recommendation_id=p.id,kind='attachment_added').count()==1
    from app.voting.service import proposal_rows
    assert next(r for r in proposal_rows(author.id)[0] if r['proposal'].id==p.id)['attachment_count']==1


@pytest.mark.parametrize('name,payload',[
    ('bad.pdf',b'<html>not a PDF</html>'),('bad.svg',b'<svg/>'),('bad.png',b'not an image'),
    ('bad.csv',b'\x00binary'),('bad.docx',b'not a zip'),('bad.exe',b'MZ'),('empty.txt',b'')])
def test_attachment_types_rejected_before_storage(voting_case,fake_attachment_storage,name,payload):
    import io
    app,author,voter,admin,a=voting_case
    owner=client_for(app,author);p=create(owner,a['approved'])
    assert owner.post(f'/voting/{p.id}/attachments',data={'file':(io.BytesIO(payload),name)}).status_code==400
    assert not fake_attachment_storage.objects and Attachment.query.filter_by(recommendation_id=p.id).count()==0


def test_attachment_limits_outage_and_csrf(voting_case,fake_attachment_storage,monkeypatch):
    import io
    from app.voting import storage
    app,author,voter,admin,a=voting_case
    owner=client_for(app,author);p=create(owner,a['approved'])
    monkeypatch.setattr(storage,'MAX_FILE_BYTES',32)
    assert owner.post(f'/voting/{p.id}/attachments',data={'file':(io.BytesIO(b'%PDF-'+b'a'*40),'large.pdf')}).status_code==400
    monkeypatch.setattr(storage,'MAX_FILE_BYTES',1024)
    def data(value=b'one'):return {'file':(io.BytesIO(value),'note.txt')}
    assert owner.post(f'/voting/{p.id}/attachments',data=data()).status_code==303
    monkeypatch.setattr(storage,'MAX_FILES',1)
    assert owner.post(f'/voting/{p.id}/attachments',data=data(b'two')).status_code==409
    assert fake_attachment_storage.puts==1
    monkeypatch.setattr(storage,'MAX_FILES',20);monkeypatch.setattr(storage,'MAX_PROPOSAL_BYTES',4)
    assert owner.post(f'/voting/{p.id}/attachments',data=data(b'two')).status_code==409
    app.config['WTF_CSRF_ENABLED']=True
    assert owner.post(f'/voting/{p.id}/attachments',data=data()).status_code==400
    app.config['WTF_CSRF_ENABLED']=False
    monkeypatch.setattr(storage,'configured',lambda:False)
    assert owner.post(f'/voting/{p.id}/attachments',data=data()).status_code==503


def test_failed_upload_or_db_commit_does_not_create_attachment(voting_case,fake_attachment_storage,monkeypatch):
    import io
    from app.voting import storage
    app,author,voter,admin,a=voting_case
    owner=client_for(app,author);p=create(owner,a['approved'])
    def data():return {'file':(io.BytesIO(b'proof'),'proof.txt')}
    def fail(*args,**kwargs):raise RuntimeError('Storage unavailable')
    monkeypatch.setattr(fake_attachment_storage,'put_object',fail)
    assert owner.post(f'/voting/{p.id}/attachments',data=data()).status_code==503
    assert Attachment.query.filter_by(recommendation_id=p.id).count()==0


@pytest.mark.parametrize('name,payload',[
    ('screenshot.png',b'\x89PNG\r\n\x1a\nimage'),('photo.jpg',b'\xff\xd8\xffimage'),
    ('animation.gif',b'GIF89aimage'),('image.webp',b'RIFFabcdWEBPimage'),
    ('note.txt','Český komentář'.encode()),('table.csv',b'name,value\nA,1')])
def test_valid_attachment_formats(name,payload):
    import io
    from werkzeug.datastructures import FileStorage
    from app.voting.storage import validate_upload
    result=validate_upload(FileStorage(stream=io.BytesIO(payload),filename=name))
    assert result['size_bytes']==len(payload) and result['filename']==name


def test_office_attachment_container_validation():
    import io,zipfile
    from werkzeug.datastructures import FileStorage
    from app.voting.storage import validate_upload
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as package:
        package.writestr('[Content_Types].xml','<Types/>');package.writestr('xl/workbook.xml','<workbook/>')
    stream.seek(0)
    assert validate_upload(FileStorage(stream=stream,filename='valuation.xlsx'))['extension']=='.xlsx'


def test_failed_db_commit_cleans_up_new_r2_object(voting_case,fake_attachment_storage,monkeypatch):
    import io
    app,author,voter,admin,a=voting_case
    owner=client_for(app,author);p=create(owner,a['approved'])
    original=db.session.commit;calls=[]
    def commit():
        calls.append(True)
        if len(calls)==2:raise RuntimeError('Example DB save failure')
        return original()
    monkeypatch.setattr(db.session,'commit',commit)
    response=owner.post(f'/voting/{p.id}/attachments',data={'file':(io.BytesIO(b'proof'),'proof.txt')})
    assert response.status_code==503 and fake_attachment_storage.puts==1
    assert fake_attachment_storage.objects=={}
    assert Attachment.query.filter_by(recommendation_id=p.id).count()==0


def test_admin_settings_not_rendered_for_members(voting_case):
    app,author,voter,admin,a=voting_case
    for user in [author,voter]:
        member=client_for(app,user)
        for path in ['/voting/','/voting/approved','/voting/history']:
            html=member.get(path).get_data(as_text=True)
            assert 'class="voting-settings"' not in html
            assert 'action="/voting/settings"' not in html
        assert member.post('/voting/settings',data={'mode':'approved'}).status_code==403
    admin_client=client_for(app,admin)
    assert 'class="voting-settings"' in admin_client.get('/voting/').get_data(as_text=True)


def test_proposal_composer_uploads_attachment_and_renewal_keeps_votes(voting_case,fake_attachment_storage):
    import io
    app,author,voter,admin,a=voting_case
    owner=client_for(app,author)
    html=owner.get('/voting/').get_data(as_text=True)
    assert 'enctype="multipart/form-data"' in html and 'name="file"' in html
    response=owner.post('/voting/propose',data={'analysis_id':a['approved'].id,'days':14,
        'rationale':'Updated valuation','file':(io.BytesIO(b'%PDF-1.4\nOriginal thesis'),'thesis.pdf')})
    assert response.status_code==303 and 'notice=attachment_added' in response.location
    p=Proposal.query.filter_by(author_id=author.id,company_id=a['approved'].company_id).one()
    assert Attachment.query.filter_by(recommendation_id=p.id).one().filename=='thesis.pdf'
    assert Event.query.filter_by(recommendation_id=p.id,kind='attachment_added').count()==1
    client_for(app,voter).post(f'/voting/{p.id}/vote',data={'vote':'yes'})
    p.expires_at=datetime.utcnow()-timedelta(seconds=1);db.session.commit()
    owner=client_for(app,author)
    response=owner.post('/voting/propose',data={'analysis_id':a['approved'].id,'days':21,
        'file':(io.BytesIO('Nové výsledky'.encode()),'update.txt')})
    assert response.status_code==303 and 'notice=attachment_added' in response.location
    assert Proposal.query.filter_by(author_id=author.id).count()==1
    assert Attachment.query.filter_by(recommendation_id=p.id).count()==2
    assert Ballot.query.filter_by(recommendation_id=p.id,vote=True).count()==1
    assert fake_attachment_storage.puts==2


def test_invalid_composer_attachment_does_not_publish_or_renew(voting_case,fake_attachment_storage,monkeypatch):
    import io
    from app.voting import storage
    app,author,voter,admin,a=voting_case
    owner=client_for(app,author)
    def data(payload=b'invalid',name='bad.pdf'):
        return {'analysis_id':a['approved'].id,'days':14,'file':(io.BytesIO(payload),name)}
    assert owner.post('/voting/propose',data=data()).status_code==400
    assert Proposal.query.filter_by(author_id=author.id).count()==0
    monkeypatch.setattr(storage,'configured',lambda:False)
    assert owner.post('/voting/propose',data=data(b'note','note.txt')).status_code==503
    assert Proposal.query.filter_by(author_id=author.id).count()==0
    # No attachment remains optional even if storage is unavailable.
    p=create(owner,a['approved']);p.expires_at=datetime.utcnow()-timedelta(days=1);db.session.commit()
    old_expiry=p.expires_at
    monkeypatch.setattr(storage,'configured',lambda:True)
    assert owner.post('/voting/propose',data=data()).status_code==400
    assert db.session.get(Proposal,p.id).expires_at==old_expiry
    assert not fake_attachment_storage.objects


def test_composer_upload_failure_saves_proposal_and_explains_retry(voting_case,fake_attachment_storage,monkeypatch):
    import io
    app,author,voter,admin,a=voting_case
    owner=client_for(app,author)
    def fail(**kwargs):raise RuntimeError('Example temporary upload failure')
    monkeypatch.setattr(fake_attachment_storage,'put_object',fail)
    response=owner.post('/voting/propose',data={'analysis_id':a['approved'].id,'days':14,
        'file':(io.BytesIO(b'note'),'note.txt')})
    assert response.status_code==303 and 'notice=proposal_attachment_failed' in response.location
    assert response.location.endswith('#attachments')
    p=Proposal.query.filter_by(author_id=author.id,company_id=a['approved'].company_id).one()
    assert Attachment.query.filter_by(recommendation_id=p.id).count()==0
    html=owner.get(response.location).get_data(as_text=True)
    assert 'role="alert" data-i18n="voting.proposal_attachment_failed"' in html
    assert '<details open>' in html
    assert f'action="/voting/{p.id}/attachments"' in html


def test_composer_duplicate_file_does_not_renew_window(voting_case,fake_attachment_storage):
    import io
    app,author,voter,admin,a=voting_case
    owner=client_for(app,author)
    def data():return {'analysis_id':a['approved'].id,'days':14,'file':(io.BytesIO(b'note'),'note.txt')}
    assert owner.post('/voting/propose',data=data()).status_code==303
    p=Proposal.query.filter_by(author_id=author.id).one()
    p.expires_at=datetime.utcnow()-timedelta(days=1);db.session.commit();old=p.expires_at
    assert owner.post('/voting/propose',data=data()).status_code==409
    assert db.session.get(Proposal,p.id).expires_at==old
    assert fake_attachment_storage.puts==1


def test_admin_can_propose_eligible_foreign_analysis_in_own_name(voting_case):
    app, author, voter, admin, analyses = voting_case
    target = analyses['other_author']
    admin_client = client_for(app, admin)
    assert f'data-select-analysis="{target.id}"' in admin_client.get('/voting/approved').text
    proposal = create(admin_client, target)
    assert proposal.author_id == admin.id
    assert admin_client.post('/voting/propose', data={
        'analysis_id': analyses['rejected'].id, 'days': 14,
    }).status_code == 403
    with admin_client.session_transaction() as state:
        state['admin_view_as_user'] = True
    assert 'class="voting-settings"' not in admin_client.get('/voting/').text
    assert admin_client.post('/voting/settings', data={'mode': 'approved'}).status_code == 403
    assert admin_client.post('/voting/propose', data={
        'analysis_id': analyses['second'].id, 'days': 14,
    }).status_code == 403


def test_edit_proposal_text_keeps_ballot_and_window(voting_case):
    app, author, voter, admin, analyses = voting_case
    owner = client_for(app, author)
    proposal = create(owner, analyses['approved'])
    expiry, previous_text = proposal.expires_at, proposal.rationale
    voter_client = client_for(app, voter)
    voter_client.post(f'/voting/{proposal.id}/vote', data={'vote': 'yes'})
    url = f'/voting/{proposal.id}/edit'
    assert voter_client.post(url, data={'rationale': 'Cannot edit'}).status_code == 403
    assert owner.post(url, data={'rationale': 'x' * 2001}).status_code == 400
    response = owner.post(url, data={'rationale': 'Revised rationale'})
    assert response.status_code == 303
    assert proposal.rationale == 'Revised rationale'
    assert proposal.expires_at == expiry
    assert Ballot.query.filter_by(recommendation_id=proposal.id, vote=True).count() == 1
    log = Event.query.filter_by(recommendation_id=proposal.id, kind='text_edited').one()
    assert log.details['previous_rationale'] == previous_text
    assert log.actor_id == author.id
    assert 'Revised rationale' in owner.get(response.location).text
    assert client_for(app, admin).post(url, data={'rationale': ''}).status_code == 303
    assert proposal.rationale == ''


def test_eligible_list_shows_notion_tally_separate_from_board(voting_case):
    app, author, voter, admin, analyses = voting_case
    analyses['approved'].comment = '9-3-2-1'
    analyses['second'].comment = '4 pro - 3 neu - 2 proti'
    db.session.commit()
    html = client_for(app, author).get('/voting/approved').text
    assert 'data-i18n="voting.team_tally"' in html
    assert '<strong class="yes">9</strong> / <strong class="no">2</strong>' in html
    assert '<strong class="yes">4</strong> / <strong class="no">2</strong>' in html
    assert '<td>1 / 0</td>' in html


def test_board_costs_are_recorded_per_purchase_without_recalculation(voting_case, monkeypatch):
    from decimal import Decimal
    from app.admin import routes
    from app.models import PortfolioPurchaseCosts

    app, author, voter, admin, analyses = voting_case
    def no_recalculation(*args, **kwargs):
        pytest.fail('Recording or opening purchase costs must not recalculate performance')
    monkeypatch.setattr(routes, 'get_portfolio_performance', no_recalculation)
    monkeypatch.setattr(routes, 'get_portfolio_series', no_recalculation)
    purchase = PortfolioPurchase(analysis_id=analyses['approved'].id,
                                 purchase_date=date(2026, 1, 12), added_by=admin.id)
    db.session.add(purchase)
    db.session.commit()
    purchase_id = purchase.id
    url = f'/admin/board/purchases/{purchase_id}/costs'
    valid = dict(unit_price='123,4567', price_currency='usd',
                 ancillary_costs='0', costs_currency='CZK')
    try:
        assert client_for(app, voter).post(url, data=valid).status_code == 302
        assert db.session.get(PortfolioPurchaseCosts, purchase_id) is None
        board = client_for(app, admin)
        for invalid in [dict(valid, unit_price='NaN'), dict(valid, costs_currency=''),
                        dict(valid, ancillary_costs='-0.01'), dict(valid, unit_price='0')]:
            assert 'costs=invalid' in board.post(url, data=invalid).location
            assert db.session.get(PortfolioPurchaseCosts, purchase_id) is None
        response = board.post(url, data=valid)
        assert response.status_code == 303 and 'costs=saved' in response.location
        costs = db.session.get(PortfolioPurchaseCosts, purchase_id)
        assert (costs.unit_price, costs.price_currency) == (Decimal('123.4567'), 'USD')
        assert (costs.ancillary_costs, costs.costs_currency) == (Decimal('0'), 'CZK')
        assert db.session.get(PortfolioPurchase, purchase_id).purchase_date == date(2026, 1, 12)
        html = board.get(response.location).text
        assert '123.4567 USD' in html and '0 CZK' in html
    finally:
        db.session.delete(db.session.get(PortfolioPurchase, purchase_id))
        db.session.commit()
