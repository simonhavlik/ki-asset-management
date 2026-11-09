from datetime import datetime, timedelta
from flask import Blueprint, abort, current_app, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from ..extensions import db
from ..models import (Analysis, SystemSettings, PurchaseRecommendation as Proposal,
                      PurchaseRecommendationVote as Ballot, PurchaseRecommendationEvent as Event,
                      PurchaseRecommendationAttachment as Attachment)
from .forms import (AttachmentForm, BallotForm, EditRecommendationForm, EligibilityForm,
                    ExtendForm, RecommendationForm, WithdrawForm)
from . import storage
from .service import (active, analyst_vote_counts, eligibility_mode, eligible_analyses, local_time,
                      proposal_rows)

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


def can_administer():
    return current_user.is_admin and not session.get('admin_view_as_user')


def can_edit_proposal(proposal):
    return proposal.author_id == current_user.id or can_administer()


def page_context(history=False):
    page = max(1, request.args.get('page', 1, type=int))
    rows, total = proposal_rows(current_user.id, history, page)
    mode = eligibility_mode()
    approved = eligible_analyses(mode)
    owned = {a.id for a, yes, no in eligible_analyses(mode, current_user.id)}
    proposable = {a.id for a, _, _ in approved} if can_administer() else owned
    active_companies = {cid for cid, in db.session.query(Proposal.company_id).filter(
        Proposal.author_id == current_user.id, Proposal.withdrawn_at.is_(None), Proposal.expires_at > datetime.utcnow()).all()}
    active_owned = {a.id for a, yes, no in approved if a.company_id in active_companies}
    return dict(rows=rows, total=total, page=page, has_more=page*25<total, history=history,
                mode=mode, approved=approved, owned=owned, active_owned=active_owned,
                proposable=proposable, can_administer=can_administer(),
                can_propose=bool(proposable-active_owned),
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
    context = page_context()
    tallies = {a.id: analyst_vote_counts(a.comment) for a, _, _ in context['approved']}
    return render_template('voting/index.html', approved_view=True, analyst_tallies=tallies,
                           **context)


@voting_bp.get('/live')
def live():
    history = request.args.get('history') == '1'
    page = max(1, request.args.get('page',1,type=int))
    rows, total = proposal_rows(current_user.id, history, page)
    response = jsonify(html=render_template('voting/_proposals.html', rows=rows, history=history, page=page, can_administer=can_administer(), csrf_form=WithdrawForm()), total=total)
    response.headers['Cache-Control'] = 'no-store'
    return response


@voting_bp.post('/propose')
def propose():
    form = RecommendationForm()
    if not form.validate_on_submit():
        return outcome('invalid', 400)
    metadata = None
    if form.file.data:
        if not storage.configured():
            return outcome('attachment_unavailable', 503)
        try:
            metadata = storage.validate_upload(form.file.data)
        except ValueError as exc:
            return outcome(str(exc), 400)
    # Company-level lock also covers two analyses of the same stock.
    from ..models import Company
    company_id = db.session.query(Analysis.company_id).filter_by(id=form.analysis_id.data).scalar()
    if company_id is None: return outcome('not_eligible',403)
    db.session.query(Company).filter_by(id=company_id).with_for_update().first()
    mode = eligibility_mode()
    author_filter = None if can_administer() else current_user.id
    match = next(((a, yes, no) for a, yes, no in eligible_analyses(mode, author_filter) if a.id == form.analysis_id.data), None)
    if match is None:
        return outcome('not_eligible', 403)
    now = datetime.utcnow()
    previous = Proposal.query.filter_by(company_id=company_id, author_id=current_user.id).with_for_update().first()
    if previous and active(previous, now):
        return outcome('duplicate', 409)
    analysis, yes, no = match
    if previous and metadata:
        error = attachment_limits(previous.id, metadata)
        if error:
            return outcome(error, 409)
    if previous:
        renew_proposal(previous, form.days.data, mode, yes, no, now, form.rationale.data, analysis.id)
        db.session.commit()
        return finish_proposal(previous.id, 'renewed', form.file.data, metadata)
    p = Proposal(analysis_id=analysis.id, company_id=analysis.company_id, author_id=current_user.id, created_at=now,
                 window_started_at=now,
                 expires_at=now+timedelta(days=form.days.data), rationale=(form.rationale.data or '').strip(),
                 eligibility_mode=mode, board_yes=yes, board_no=no)
    db.session.add(p); db.session.flush()
    event(p, 'created', days=form.days.data, expires_at=p.expires_at.isoformat(), eligibility_mode=mode, board_yes=yes, board_no=no)
    db.session.commit()
    return finish_proposal(p.id, 'created', form.file.data, metadata)


def finish_proposal(proposal_id, notice, file, metadata):
    if metadata is None:
        return outcome(notice)
    error, _ = store_attachment(proposal_id, file, metadata)
    # The recommendation is already saved: retry only the file, never the proposal.
    return redirect(url_for('voting.detail', proposal_id=proposal_id,
                            notice='proposal_attachment_failed' if error else 'attachment_added',
                            _anchor='attachments'), code=303)


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
    candidates=eligible_analyses(mode, None if can_administer() else current_user.id)
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
    if not can_administer(): abort(403)
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
                           events=events,is_active=active(p),local_time=local_time,
                           attachments=Attachment.query.filter_by(recommendation_id=p.id).order_by(Attachment.created_at).all(),
                           attachment_form=AttachmentForm(),storage_ready=storage.configured(),
                           can_administer=can_administer(), can_edit=can_edit_proposal(p),
                           edit_form=EditRecommendationForm(rationale=p.rationale),
                           text_saved=request.args.get('notice')=='text_saved',
                           attachment_notice=request.args.get('notice')=='attachment_added',
                           attachment_retry=request.args.get('notice')=='proposal_attachment_failed')


@voting_bp.post('/<int:proposal_id>/edit')
def edit(proposal_id):
    form = EditRecommendationForm()
    if not form.validate_on_submit():
        return outcome('invalid_text', 400)
    proposal = locked_proposal(proposal_id)
    if not can_edit_proposal(proposal):
        abort(403)
    rationale = (form.rationale.data or '').strip()
    if proposal.rationale != rationale:
        event(proposal, 'text_edited', previous_rationale=proposal.rationale)
        proposal.rationale = rationale
        db.session.commit()
    list_view = 'index' if active(proposal) else 'history'
    if request.form.get('return_to') == list_view:
        page = max(1, request.form.get('page', 1, type=int))
        return redirect(url_for('voting.' + list_view, page=page, edited=proposal_id,
                                _anchor=f'proposal-{proposal_id}'), code=303)
    return redirect(url_for('voting.detail', proposal_id=proposal_id, notice='text_saved'),
                    code=303)


@voting_bp.post('/<int:proposal_id>/attachments')
def attach(proposal_id):
    form=AttachmentForm()
    if not form.validate_on_submit():return outcome('attachment_type',400)
    p=db.get_or_404(Proposal,proposal_id)
    if p.author_id!=current_user.id and not can_administer():abort(403)
    if not storage.configured():return outcome('attachment_unavailable',503)
    try:metadata=storage.validate_upload(form.file.data)
    except ValueError as exc:return outcome(str(exc),400)
    error, status = store_attachment(proposal_id, form.file.data, metadata)
    if error:
        return outcome(error, status)
    return redirect(url_for('voting.detail',proposal_id=proposal_id,notice='attachment_added'),code=303)


def attachment_limits(proposal_id, metadata):
    query = Attachment.query.filter_by(recommendation_id=proposal_id)
    if query.filter_by(sha256=metadata['sha256']).first():
        return 'attachment_duplicate'
    count, total = db.session.query(
        func.count(Attachment.id), func.coalesce(func.sum(Attachment.size_bytes), 0)
    ).filter_by(recommendation_id=proposal_id).one()
    if count >= storage.MAX_FILES or total + metadata['size_bytes'] > storage.MAX_PROPOSAL_BYTES:
        return 'attachment_quota'


def store_attachment(proposal_id, file, metadata):
    """Store one validated file without holding a database connection during R2 I/O."""
    error = attachment_limits(proposal_id, metadata)
    if error:
        return error, 409
    db.session.commit()
    key = None
    try:
        key = storage.upload(file, metadata, proposal_id)
        p = locked_proposal(proposal_id)
        error = attachment_limits(proposal_id, metadata)
        if error:
            db.session.rollback()
            storage.delete_uploaded(key)
            key = None
            return error, 409
        row = Attachment(recommendation_id=p.id, uploaded_by=current_user.id, object_key=key,
                         **{name: metadata[name] for name in
                            ('filename', 'content_type', 'size_bytes', 'sha256')})
        db.session.add(row)
        db.session.flush()
        event(p, 'attachment_added', attachment_id=row.id, filename=row.filename,
              size_bytes=row.size_bytes)
        db.session.commit()
    except Exception:
        db.session.rollback()
        if key:
            try:
                storage.delete_uploaded(key)
            except Exception:
                current_app.logger.warning('Could not clean up unattached R2 object')
        current_app.logger.exception('Private recommendation attachment upload failed')
        return 'attachment_failed', 503
    return None, 303


@voting_bp.get('/attachments/<int:attachment_id>/download')
def attachment_download(attachment_id):
    row=db.get_or_404(Attachment,attachment_id)
    if not storage.configured():return outcome('attachment_unavailable',503)
    try:return redirect(storage.download_url(row),code=302)
    except Exception:return outcome('attachment_failed',503)
