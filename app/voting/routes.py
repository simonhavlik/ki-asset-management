from datetime import datetime, timedelta
from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload
from ..extensions import db
from ..models import (Analysis, SystemSettings, PurchaseRecommendation as Proposal,
                      PurchaseRecommendationVote as Ballot, PurchaseRecommendationEvent as Event)
from .forms import RecommendationForm, ExtendForm, BallotForm, EligibilityForm, WithdrawForm
from .service import active, eligibility_mode, eligible_analyses, local_time, proposal_rows

voting_bp = Blueprint('voting', __name__)


@voting_bp.before_request
@login_required
def require_member():
    if not current_user.is_active:
        abort(403)


@voting_bp.after_request
def live_responses(response):
    response.headers['Cache-Control'] = 'no-store'
    return response


def event(proposal, kind, **details):
    db.session.add(Event(recommendation_id=proposal.id, actor_id=current_user.id, kind=kind, details=details))


def outcome(key, status=303, history=False):
    if status != 303:
        return render_template('voting/error.html', message_key='voting.'+key), status
    return redirect(url_for('voting.history' if history else 'voting.index', notice=key), code=303)


def locked_proposal(proposal_id):
    # Serializes duplicate votes, expiry checks and concurrent author extensions.
    row = db.session.query(Proposal).filter_by(id=proposal_id).with_for_update().first()
    if row is None:
        abort(404)
    return row


def page_context(history=False):
    page = max(1, request.args.get('page', 1, type=int))
    rows, total = proposal_rows(current_user.id, history, page)
    mode = eligibility_mode()
    approved = eligible_analyses(mode)
    owned = {a.id for a, yes, no in eligible_analyses(mode, current_user.id)}
    active_companies = {cid for cid, in db.session.query(Proposal.company_id).filter(
        Proposal.author_id == current_user.id, Proposal.withdrawn_at.is_(None), Proposal.expires_at > datetime.utcnow()).all()}
    active_owned = {a.id for a, yes, no in approved if a.company_id in active_companies}
    return dict(rows=rows, total=total, page=page, has_more=page*25<total, history=history,
                mode=mode, approved=approved, owned=owned, active_owned=active_owned,
                can_propose=bool(owned-active_owned),
                csrf_form=WithdrawForm(), create_form=RecommendationForm(),
                notice=request.args.get('notice') if request.args.get('notice') in ('created','voted','removed','extended','renewed','withdrawn','settings_saved') else None)


@voting_bp.get('/')
def index():
    return render_template('voting/index.html', **page_context())


@voting_bp.get('/history')
def history():
    return render_template('voting/index.html', **page_context(True))


@voting_bp.get('/approved')
def approved():
    return render_template('voting/index.html', approved_view=True, **page_context())


@voting_bp.get('/live')
def live():
    history = request.args.get('history') == '1'
    page = max(1, request.args.get('page',1,type=int))
    rows, total = proposal_rows(current_user.id, history, page)
    response = jsonify(html=render_template('voting/_proposals.html', rows=rows, history=history, csrf_form=WithdrawForm()), total=total)
    response.headers['Cache-Control'] = 'no-store'
    return response


@voting_bp.post('/propose')
def propose():
    form = RecommendationForm()
    if not form.validate_on_submit():
        return outcome('invalid', 400)
    # Company-level lock also covers two analyses of the same stock.
    from ..models import Company
    company_id = db.session.query(Analysis.company_id).filter_by(id=form.analysis_id.data).scalar()
    if company_id is None: return outcome('not_eligible',403)
    db.session.query(Company).filter_by(id=company_id).with_for_update().first()
    mode = eligibility_mode()
    match = next(((a, yes, no) for a, yes, no in eligible_analyses(mode, current_user.id) if a.id == form.analysis_id.data), None)
    if match is None:
        return outcome('not_eligible', 403)
    now = datetime.utcnow()
    previous = Proposal.query.filter_by(company_id=company_id, author_id=current_user.id).with_for_update().first()
    if previous and active(previous, now):
        return outcome('duplicate', 409)
    analysis, yes, no = match
    if previous:
        renew_proposal(previous, form.days.data, mode, yes, no, now, form.rationale.data, analysis.id)
        db.session.commit()
        return outcome('renewed')
    p = Proposal(analysis_id=analysis.id, company_id=analysis.company_id, author_id=current_user.id, created_at=now,
                 window_started_at=now,
                 expires_at=now+timedelta(days=form.days.data), rationale=(form.rationale.data or '').strip(),
                 eligibility_mode=mode, board_yes=yes, board_no=no)
    db.session.add(p); db.session.flush()
    event(p, 'created', days=form.days.data, expires_at=p.expires_at.isoformat(), eligibility_mode=mode, board_yes=yes, board_no=no)
    db.session.commit()
    return outcome('created')


def renew_proposal(p, days, mode, yes, no, now, rationale=None, analysis_id=None):
    ballots = Ballot.query.filter_by(recommendation_id=p.id).all()
    event(p, 'renewed', previous_start=p.window_started_at.isoformat(),
          previous_expiry=p.expires_at.isoformat(), previous_rationale=p.rationale,
          previous_mode=p.eligibility_mode, previous_analysis_id=p.analysis_id, previous_board_yes=p.board_yes,
          previous_board_no=p.board_no, carried_yes=sum(v.vote for v in ballots),
          carried_no=sum(not v.vote for v in ballots), expires_at=(now+timedelta(days=days)).isoformat())
    p.window_started_at=now; p.expires_at=now+timedelta(days=days); p.withdrawn_at=None
    p.eligibility_mode=mode; p.board_yes=yes; p.board_no=no
    if analysis_id is not None: p.analysis_id=analysis_id
    if rationale and rationale.strip(): p.rationale=rationale.strip()


@voting_bp.post('/<int:proposal_id>/renew')
def renew(proposal_id):
    form=ExtendForm()
    if not form.validate_on_submit(): return outcome('invalid',400)
    p=locked_proposal(proposal_id)
    if p.author_id!=current_user.id: abort(403)
    now=datetime.utcnow()
    if active(p,now): return outcome('duplicate',409)
    mode=eligibility_mode()
    candidates=eligible_analyses(mode,current_user.id)
    match=next(((a,yes,no) for a,yes,no in candidates if a.id==p.analysis_id),None)
    if match is None:
        match=next(((a,yes,no) for a,yes,no in candidates if a.company_id==p.company_id),None)
    if match is None: return outcome('not_eligible',403)
    a,yes,no=match
    renew_proposal(p,form.days.data,mode,yes,no,now,analysis_id=a.id)
    db.session.commit()
    return outcome('renewed')


@voting_bp.post('/<int:proposal_id>/vote')
def vote(proposal_id):
    form = BallotForm()
    if not form.validate_on_submit():
        return outcome('invalid', 400)
    p = locked_proposal(proposal_id)
    now = datetime.utcnow()
    if not active(p, now):
        return outcome('closed', 409)
    row = Ballot.query.filter_by(recommendation_id=p.id,user_id=current_user.id).first()
    previous = row.vote if row else None
    value = None if form.vote.data=='remove' else form.vote.data=='yes'
    if value is None:
        if row: db.session.delete(row)
    elif row:
        row.vote = value; row.updated_at = now
    else:
        db.session.add(Ballot(recommendation_id=p.id,user_id=current_user.id,vote=value,created_at=now,updated_at=now))
    if previous is not value:
        event(p,'ballot',previous=previous,vote=value)
    db.session.commit()
    return outcome('removed' if value is None else 'voted')


@voting_bp.post('/<int:proposal_id>/extend')
def extend(proposal_id):
    form = ExtendForm()
    if not form.validate_on_submit(): return outcome('invalid',400)
    p = locked_proposal(proposal_id)
    if p.author_id != current_user.id: abort(403)
    now = datetime.utcnow()
    if not active(p,now): return outcome('closed',409)
    until = now+timedelta(days=form.days.data)
    if until <= p.expires_at: return outcome('not_later',400)
    previous = p.expires_at
    p.expires_at = until
    event(p,'extended',previous=previous.isoformat(),expires_at=until.isoformat())
    db.session.commit()
    return outcome('extended')


@voting_bp.post('/<int:proposal_id>/withdraw')
def withdraw(proposal_id):
    form = WithdrawForm()
    if not form.validate_on_submit(): return outcome('invalid',400)
    p = locked_proposal(proposal_id)
    if p.author_id != current_user.id: abort(403)
    if not active(p): return outcome('closed',409)
    p.withdrawn_at = datetime.utcnow()
    event(p,'withdrawn')
    db.session.commit()
    return outcome('withdrawn',history=True)


@voting_bp.post('/settings')
def settings():
    if not current_user.is_admin: abort(403)
    form = EligibilityForm()
    if not form.validate_on_submit(): return outcome('invalid',400)
    # This single validated setting and its activity record commit together.
    from ..models import ActivityLog
    previous = eligibility_mode()
    row = SystemSettings.query.filter_by(key='purchase_voting_eligibility').first()
    if row is None:
        row = SystemSettings(key='purchase_voting_eligibility',value_type='string');db.session.add(row)
    row.value = form.mode.data
    db.session.add(ActivityLog(user_id=current_user.id,action='purchase_voting_eligibility',details=f'{previous} -> {form.mode.data}'))
    db.session.commit()
    return outcome('settings_saved')


@voting_bp.get('/<int:proposal_id>')
def detail(proposal_id):
    p = db.get_or_404(Proposal,proposal_id)
    votes = Ballot.query.filter_by(recommendation_id=p.id).all()
    events = Event.query.options(joinedload(Event.actor)).filter_by(recommendation_id=p.id).order_by(Event.created_at,Event.id).all()
    return render_template('voting/detail.html',p=p,yes=sum(v.vote for v in votes),no=sum(not v.vote for v in votes),
                           events=events,is_active=active(p),local_time=local_time)
