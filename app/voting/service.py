"""Time-windowed purchase ballots. No pricing, trades or Board-vote writes."""
import re
from datetime import datetime, date
from zoneinfo import ZoneInfo
from sqlalchemy import case, func
from sqlalchemy.orm import joinedload
from ..extensions import db
from ..models import (Analysis, Company, CompanyTickerMapping, Vote, SystemSettings,
                      PurchaseRecommendation as Proposal, PurchaseRecommendationVote as Ballot,
                      PurchaseRecommendationAttachment as Attachment,
                      analysis_analysts)

MODES = ('board', 'approved')


def eligibility_mode():
    mode = SystemSettings.get('purchase_voting_eligibility', 'board')
    return mode if mode in MODES else 'board'


def eligible_analyses(mode=None, author_id=None):
    mode = mode or eligibility_mode()
    board = db.session.query(Vote.analysis_id,
        func.sum(case((Vote.vote.is_(True), 1), else_=0)).label('yes'),
        func.sum(case((Vote.vote.is_(False), 1), else_=0)).label('no')).group_by(Vote.analysis_id).subquery()
    other = db.session.query(CompanyTickerMapping.id).filter(
        CompanyTickerMapping.company_name == Company.name,
        CompanyTickerMapping.is_other_event.is_(True)).exists()
    query = db.session.query(Analysis, func.coalesce(board.c.yes, 0), func.coalesce(board.c.no, 0)).join(
        Company, Company.id == Analysis.company_id).outerjoin(board, board.c.analysis_id == Analysis.id).filter(
        Analysis.status.in_(['On Watchlist', 'Portfolio']), Analysis.analysis_date <= date.today(), ~other)
    if mode == 'board':
        query = query.filter(func.coalesce(board.c.yes, 0) > func.coalesce(board.c.no, 0))
    if author_id is not None:
        query = query.join(analysis_analysts, analysis_analysts.c.analysis_id == Analysis.id).filter(
            analysis_analysts.c.user_id == author_id, analysis_analysts.c.role == 'analyst')
    return query.options(joinedload(Analysis.company)).order_by(Company.name, Analysis.analysis_date.desc()).all()


def analyst_vote_counts(comment):
    """Read the club tally imported from Notion: for, neutral, against, absent."""
    text = (comment or '').strip()
    current = re.fullmatch(r'(\d+)\s*[-–]\s*\d+\s*[-–]\s*(\d+)\s*[-–]\s*\d+', text)
    if current:
        return int(current[1]), int(current[2])
    older = re.fullmatch(
        r'(\d+)\s+pro\s*[-–]\s*\d+\s+neu(?:trálně)?\s*[-–]\s*(\d+)\s+proti',
        text, re.IGNORECASE,
    )
    return (int(older[1]), int(older[2])) if older else None


def active(proposal, now=None):
    return proposal.withdrawn_at is None and proposal.expires_at > (now or datetime.utcnow())


def local_time(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo('UTC'))
    return value.astimezone(ZoneInfo('Europe/Prague')).strftime('%d.%m.%Y %H:%M')


def proposal_rows(user_id, history=False, page=1, now=None):
    now = now or datetime.utcnow()
    counts = db.session.query(Ballot.recommendation_id,
        func.sum(case((Ballot.vote.is_(True), 1), else_=0)).label('yes'),
        func.sum(case((Ballot.vote.is_(False), 1), else_=0)).label('no')).group_by(Ballot.recommendation_id).subquery()
    mine = db.session.query(Ballot.recommendation_id, Ballot.vote).filter(Ballot.user_id == user_id).subquery()
    files = db.session.query(Attachment.recommendation_id,func.count(Attachment.id).label('count')).group_by(Attachment.recommendation_id).subquery()
    query = db.session.query(Proposal, func.coalesce(counts.c.yes, 0), func.coalesce(counts.c.no, 0), mine.c.vote,
                             func.coalesce(files.c.count,0)).outerjoin(
        counts, counts.c.recommendation_id == Proposal.id).outerjoin(mine, mine.c.recommendation_id == Proposal.id).outerjoin(
        files, files.c.recommendation_id == Proposal.id)
    condition = (Proposal.withdrawn_at.is_(None)) & (Proposal.expires_at > now)
    if history:
        query = query.filter(~condition).order_by(func.coalesce(Proposal.withdrawn_at, Proposal.expires_at).desc(), Proposal.id.desc())
    else:
        query = query.filter(condition).order_by(func.coalesce(counts.c.yes, 0).desc(), Proposal.expires_at, Proposal.id)
    total = query.count()
    rows = query.options(joinedload(Proposal.analysis).joinedload(Analysis.company), joinedload(Proposal.author)).offset((page-1)*25).limit(25).all()
    return [dict(proposal=p, yes=yes, no=no, mine=mine_vote, expires_local=local_time(p.expires_at),
                 created_local=local_time(p.created_at),attachment_count=file_count) for p, yes, no, mine_vote, file_count in rows], total
