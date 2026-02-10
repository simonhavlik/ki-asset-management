"""
Main blueprint for public pages.

This module handles all public-facing routes including the landing page,
about page, and legal pages (privacy, terms).

Routes:
    /           : Landing page with team info and performance highlights
    /about      : About the club and platform
    /privacy    : Privacy policy
    /terms      : Terms of service
    /wall       : Public ideas wall
"""

from flask import Blueprint, render_template, redirect, url_for, current_app, request, flash, abort
from flask_login import current_user, login_required
from datetime import datetime, date, timedelta
from sqlalchemy import func

from ..extensions import db
from ..models import Analysis, Vote, PerformanceCalculation, User, CsvUpload, Idea, IdeaComment, BlogPost
from ..security import rate_limit, InputValidator, sanitize_input

# Create blueprint for main routes
main_bp = Blueprint('main', __name__, template_folder='../templates/main')


def get_benchmark_price_on_date(ticker, target_date):
    """Get cached benchmark price on or before target_date."""
    from ..models import BenchmarkPrice
    price = BenchmarkPrice.query.filter(
        BenchmarkPrice.ticker == ticker,
        BenchmarkPrice.date <= target_date
    ).order_by(BenchmarkPrice.date.desc()).first()
    return float(price.close_price) if price else None


def get_benchmark_return(ticker: str, days: int = 365) -> float:
    """
    Get benchmark return using cached BenchmarkPrice data.
    Falls back to approximate calculation if no cached data.
    Uses same logic as Board page.
    
    Args:
        ticker: ETF ticker (e.g., 'SPY', 'VT', 'EEMS')
        days: Number of days to look back
        
    Returns:
        Percentage return over the period
    """
    try:
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        # Get start and end prices from cache (same as Board page)
        start_price = get_benchmark_price_on_date(ticker, start_date)
        end_price = get_benchmark_price_on_date(ticker, end_date)
        
        if start_price and end_price:
            return ((end_price - start_price) / start_price) * 100
    except Exception as e:
        current_app.logger.warning(f"Error getting cached benchmark for {ticker}: {e}")
    
    # Fallback to approximate calculation
    annual_returns = {'SPY': 10.0, 'VT': 9.0, 'EEMS': 7.0}
    annual = annual_returns.get(ticker, 8.0)
    years = days / 365.0
    return ((1 + annual/100) ** years - 1) * 100


def get_portfolio_1yr_return():
    """
    Calculate portfolio 1-year return using cached PerformanceCalculation data.
    No live API calls - uses pre-calculated returns from database.
    """
    from ..models import Vote
    
    try:
        # Get Board-approved positions (votes_yes > votes_no)
        approved_analysis_ids = []
        for analysis in Analysis.query.filter_by(status='On Watchlist').all():
            votes_yes = Vote.query.filter_by(analysis_id=analysis.id, vote=True).count()
            votes_no = Vote.query.filter_by(analysis_id=analysis.id, vote=False).count()
            if votes_yes > votes_no:
                approved_analysis_ids.append(analysis.id)
        
        if not approved_analysis_ids:
            return None
        
        # Use cached PerformanceCalculation data (no live API calls)
        total_return = 0.0
        count = 0
        
        for analysis_id in approved_analysis_ids:
            perf = PerformanceCalculation.query.filter_by(
                analysis_id=analysis_id
            ).order_by(PerformanceCalculation.calculation_date.desc()).first()
            
            if perf:
                total_return += float(perf.return_pct)
                count += 1
        
        if count > 0:
            return round(total_return / count, 2)
        return None
    except Exception as e:
        current_app.logger.warning(f"Error calculating portfolio return: {e}")
        return None


def get_dashboard_stats():
    """
    Get dashboard statistics for the main page.
    
    Returns:
        dict: Statistics including:
            - total_users: Number of analysts/users
            - total_analyses: Total number of analyses
            - approved_analyses: Number of 'On Watchlist' analyses
            - portfolio_positions: Number of Board-approved positions (votes_yes > votes_no)
            - portfolio_return: Average 1-year return of Board portfolio (for fair benchmark comparison)
            - portfolio_return_inception: Average return since inception
            - portfolio_updated: Date of last portfolio calculation
            - total_meetings: Total unique meeting dates
            - benchmark_spy: S&P 500 1-year return
            - benchmark_ftse: FTSE All-World 1-year return
            - benchmark_eems: Emerging Markets 1-year return
    """
    try:
        # Get total users count (analysts)
        total_users = User.query.count()
        
        # Get total analyses count
        total_analyses = Analysis.query.count()
        
        # Get approved analyses count (On Watchlist)
        approved_analyses = Analysis.query.filter_by(status='On Watchlist').count()
        
        # Get total meetings - count unique analysis dates (each date = one meeting)
        total_meetings = db.session.query(func.count(func.distinct(Analysis.analysis_date))).scalar() or 0
        
        # Get Board-approved positions (votes_yes > votes_no)
        approved_analysis_ids = []
        earliest_date = None
        for analysis in Analysis.query.filter_by(status='On Watchlist').all():
            votes_yes = Vote.query.filter_by(analysis_id=analysis.id, vote=True).count()
            votes_no = Vote.query.filter_by(analysis_id=analysis.id, vote=False).count()
            if votes_yes > votes_no:
                approved_analysis_ids.append(analysis.id)
                if earliest_date is None or analysis.analysis_date < earliest_date:
                    earliest_date = analysis.analysis_date
        
        portfolio_positions = len(approved_analysis_ids)
        
        # Calculate since-inception return (same as Board page for fair comparison)
        portfolio_return = None
        portfolio_return_inception = None
        portfolio_updated = None
        days_since_inception = 365  # default to 1 year
        
        if approved_analysis_ids:
            total_return = 0.0
            count = 0
            latest_date = None
            
            for analysis_id in approved_analysis_ids:
                perf = PerformanceCalculation.query.filter_by(
                    analysis_id=analysis_id
                ).order_by(PerformanceCalculation.calculation_date.desc()).first()
                
                if perf:
                    total_return += float(perf.return_pct)
                    count += 1
                    if latest_date is None or perf.calculation_date > latest_date:
                        latest_date = perf.calculation_date
            
            if count > 0:
                portfolio_return_inception = round(total_return / count, 2)
                portfolio_return = portfolio_return_inception
                portfolio_updated = latest_date
                
                # Calculate days since inception for benchmark comparison
                if earliest_date:
                    days_since_inception = (date.today() - earliest_date).days
        
        # Get benchmark returns over same period as portfolio (for fair comparison)
        benchmark_spy = get_benchmark_return('SPY', days_since_inception)
        benchmark_ftse = get_benchmark_return('VT', days_since_inception)  # FTSE All-World
        benchmark_eems = get_benchmark_return('EEMS', days_since_inception)  # Emerging Markets
        
        # Calculate portfolio risk metrics
        portfolio_metrics = calculate_portfolio_metrics(approved_analysis_ids, portfolio_return)
        
        return {
            'total_users': total_users,
            'total_analyses': total_analyses,
            'approved_analyses': approved_analyses,
            'portfolio_positions': portfolio_positions,
            'total_meetings': total_meetings,
            'portfolio_return': portfolio_return,
            'portfolio_return_inception': portfolio_return_inception,
            'portfolio_updated': portfolio_updated,
            'benchmark_spy': round(benchmark_spy, 2),
            'benchmark_ftse': round(benchmark_ftse, 2),
            'benchmark_eems': round(benchmark_eems, 2),
            **portfolio_metrics
        }
    except Exception as e:
        current_app.logger.error(f"Error fetching dashboard stats: {e}")
        # Return default values if database is not available
        return {
            'total_users': 0,
            'total_analyses': 0,
            'approved_analyses': 0,
            'portfolio_positions': 0,
            'total_meetings': 60,
            'portfolio_return': None,
            'portfolio_return_inception': None,
            'portfolio_updated': None,
            'benchmark_spy': 15.0,
            'benchmark_ftse': 12.0,
            'benchmark_eems': 8.0,
            'max_drawdown': None,
            'volatility': None,
            'beta': None,
            'alpha_spy': None,
            'sharpe_ratio': None,
            'win_rate': None
        }


def calculate_portfolio_metrics(approved_analysis_ids, portfolio_return):
    """
    Calculate advanced portfolio risk metrics for institutional reporting.
    
    Args:
        approved_analysis_ids: List of approved analysis IDs
        portfolio_return: Overall portfolio return percentage
        
    Returns:
        dict: Portfolio metrics including:
            - max_drawdown: Maximum peak-to-trough decline
            - volatility: Annualized volatility (standard deviation)
            - beta: Portfolio beta relative to S&P 500
            - alpha: Excess return over benchmark
            - sharpe_ratio: Risk-adjusted return measure
            - win_rate: Percentage of positions with positive returns
    """
    try:
        from ..models import Vote
        import math
        
        if not approved_analysis_ids:
            return {
                'max_drawdown': None,
                'volatility': None,
                'beta': None,
                'alpha_spy': None,
                'sharpe_ratio': None,
                'win_rate': None
            }
        
        # Get all performance calculations for approved analyses
        portfolio_returns = []
        winning_positions = 0
        total_positions = 0
        
        for analysis_id in approved_analysis_ids:
            perf = PerformanceCalculation.query.filter_by(
                analysis_id=analysis_id
            ).order_by(PerformanceCalculation.calculation_date.desc()).first()
            
            if perf and perf.return_pct is not None:
                ret = float(perf.return_pct)
                portfolio_returns.append(ret)
                total_positions += 1
                if ret > 0:
                    winning_positions += 1
        
        if not portfolio_returns:
            return {
                'max_drawdown': None,
                'volatility': None,
                'beta': None,
                'alpha_spy': None,
                'sharpe_ratio': None,
                'win_rate': None
            }
        
        # Calculate win rate
        win_rate = (winning_positions / total_positions * 100) if total_positions > 0 else None
        
        # Calculate volatility (simplified annualized standard deviation)
        if len(portfolio_returns) > 1:
            mean_return = sum(portfolio_returns) / len(portfolio_returns)
            variance = sum((r - mean_return) ** 2 for r in portfolio_returns) / len(portfolio_returns)
            # Annualize volatility (assuming monthly data, multiply by sqrt(12))
            volatility = math.sqrt(variance) * math.sqrt(12)
        else:
            volatility = None
        
        # Calculate max drawdown (simplified from peak)
        if portfolio_returns:
            cumulative = []
            running_total = 0
            for ret in portfolio_returns:
                running_total += ret
                cumulative.append(running_total)
            
            peak = cumulative[0] if cumulative else 0
            max_dd = 0
            for value in cumulative:
                if value > peak:
                    peak = value
                dd = peak - value
                if dd > max_dd:
                    max_dd = dd
            max_drawdown = max_dd
        else:
            max_drawdown = None
        
        # Calculate alpha (excess return vs S&P 500)
        # Using approximate S&P 500 return of 10% annually
        spy_return = 10.0
        alpha_spy = (portfolio_return - spy_return) if portfolio_return else None
        
        # Beta estimation (simplified - assume higher volatility = higher beta)
        # In reality, this requires correlation analysis with market returns
        if volatility:
            # Rough estimate: beta ~ portfolio_vol / market_vol
            # Market vol typically ~15-20%, but this is a simplified heuristic
            market_vol = 16.0
            beta = min(max(volatility / market_vol, 0.5), 2.0)  # Cap between 0.5 and 2.0
        else:
            beta = None
        
        # Sharpe ratio (simplified with risk-free rate ~3%)
        risk_free_rate = 3.0
        if portfolio_return and volatility:
            sharpe_ratio = (portfolio_return - risk_free_rate) / volatility
        else:
            sharpe_ratio = None
        
        return {
            'max_drawdown': round(max_drawdown, 2) if max_drawdown else None,
            'volatility': round(volatility, 2) if volatility else None,
            'beta': round(beta, 2) if beta else None,
            'alpha_spy': round(alpha_spy, 2) if alpha_spy is not None else None,
            'sharpe_ratio': round(sharpe_ratio, 2) if sharpe_ratio else None,
            'win_rate': round(win_rate, 1) if win_rate else None
        }
        
    except Exception as e:
        current_app.logger.warning(f"Error calculating portfolio metrics: {e}")
        return {
            'max_drawdown': None,
            'volatility': None,
            'beta': None,
            'alpha_spy': None,
            'sharpe_ratio': None,
            'win_rate': None
        }


def get_portfolio_chart_data(method='incremental'):
    """
    Get portfolio performance chart data for the main page hero section.
    Shows all approved (board-approved) positions since inception.
    
    Uses incremental equal-weight rebalancing by default for realistic
    portfolio simulation, or simple equal-weighting if specified.
    
    Args:
        method: 'incremental' (default) or 'equal' - calculation method
    
    Returns:
        Dict with dates and portfolio/benchmark series or None if no data
    """
    from ..models import Vote
    from ..utils.presentation_export import generate_portfolio_chart_series
    
    try:
        # Get Board-approved analyses (votes_yes > votes_no)
        analyses = []
        for analysis in Analysis.query.filter_by(status='On Watchlist').all():
            votes_yes = Vote.query.filter_by(analysis_id=analysis.id, vote=True).count()
            votes_no = Vote.query.filter_by(analysis_id=analysis.id, vote=False).count()
            if votes_yes > votes_no:
                analyses.append(analysis)
        
        if not analyses:
            return None
        
        # Get analysis IDs
        analysis_ids = [a.id for a in analyses]
        
        # Use centralized function with selected method
        series_data = generate_portfolio_chart_series(analysis_ids, years=None, method=method)
        
        if not series_data or not series_data.get('dates'):
            return None
        
        # Get benchmark series
        import pandas as pd
        dates = pd.to_datetime(series_data['dates'])
        earliest_date = analyses[0].analysis_date
        
        spy_series = []
        vt_series = []
        eems_series = []
        
        for d in dates:
            current_date = d.date()
            spy_series.append(_get_benchmark_return_for_date('SPY', earliest_date, current_date))
            vt_series.append(_get_benchmark_return_for_date('VT', earliest_date, current_date))
            eems_series.append(_get_benchmark_return_for_date('EEMS', earliest_date, current_date))
        
        return {
            'dates': series_data['dates'],
            'portfolio_series': series_data['values'],
            'spy_series': spy_series,
            'vt_series': vt_series,
            'eems_series': eems_series,
            'method': method
        }
    except Exception as e:
        current_app.logger.warning(f"Error generating portfolio chart data: {e}")
        return None


def _get_benchmark_return_for_date(ticker: str, start_date: date, end_date: date) -> float:
    """Get benchmark return from start_date to end_date."""
    from ..models import BenchmarkPrice
    
    try:
        start_price = BenchmarkPrice.query.filter(
            BenchmarkPrice.ticker == ticker,
            BenchmarkPrice.date <= start_date
        ).order_by(BenchmarkPrice.date.desc()).first()
        
        end_price = BenchmarkPrice.query.filter(
            BenchmarkPrice.ticker == ticker,
            BenchmarkPrice.date <= end_date
        ).order_by(BenchmarkPrice.date.desc()).first()
        
        if start_price and end_price:
            return round(((float(end_price.close_price) - float(start_price.close_price)) / 
                         float(start_price.close_price)) * 100, 2)
    except Exception:
        pass
    
    # Fallback: calculate approximate return based on days
    days = (end_date - start_date).days
    annual_returns = {'SPY': 10.0, 'VT': 9.0, 'EEMS': 7.0}
    annual = annual_returns.get(ticker, 8.0)
    years = days / 365.0
    return round(((1 + annual/100) ** years - 1) * 100, 2)


@main_bp.route('/')
def index():
    """
    Landing page - Premium public homepage.
    
    This page is now displayed to all visitors including authenticated users.
    Uses aggressive caching to minimize Neon DB compute unit usage.
    
    Returns:
        Rendered index.html template with cached stats
    """
    # Use cached data to avoid DB calls (Neon optimization)
    from ..utils.neon_cache import (
        get_cached_main_stats,
        get_cached_portfolio_chart,
        get_cached_growth_timeline,
        get_cached_top_sectors,
        get_cached_latest_blog_posts
    )
    
    stats = get_cached_main_stats()
    chart_data = get_cached_portfolio_chart()
    growth_data = get_cached_growth_timeline()
    top_sectors = get_cached_top_sectors()
    latest_blog_posts = get_cached_latest_blog_posts(limit=3)
    
    return render_template('main/index.html', 
                         stats=stats, 
                         chart_data=chart_data,
                         growth_data=growth_data,
                         top_sectors=top_sectors,
                         latest_blog_posts=latest_blog_posts)


@main_bp.route('/about')
def about():
    """
    About page - Detailed information about the platform.
    
    Returns:
        Rendered about.html template
    """
    return render_template('main/about.html')


@main_bp.route('/privacy')
def privacy():
    """
    Privacy policy page.
    
    Returns:
        Rendered privacy.html template
    """
    return render_template('main/privacy.html')


@main_bp.route('/terms')
def terms():
    """
    Terms of service page.

    Returns:
        Rendered terms.html template
    """
    return render_template('main/terms.html')


@main_bp.route('/methodology')
def methodology():
    """
    Calculation methodology page.

    Provides detailed documentation of all mathematical formulas and
    calculation methods used in the platform.

    Returns:
        Rendered methodology.html template
    """
    return render_template('main/methodology.html')


@main_bp.route('/health')
def health_check():
    """
    Health check endpoint for monitoring services (e.g., UptimeRobot).
    Returns 200 OK without hitting the database to save Neon CU-hours.
    
    Returns:
        JSON with status and timestamp
    """
    from datetime import datetime
    return {
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'neon_optimize': True
    }


@main_bp.route('/wall')
def wall():
    """
    Public ideas wall for stock ideas sharing.
    Uses caching to minimize Neon DB compute unit usage.
    
    Returns:
        Rendered wall.html template with ideas
    """
    page = request.args.get('page', 1, type=int)
    per_page = 12
    
    # Use cached data to avoid DB calls (Neon optimization)
    from ..utils.neon_cache import get_cached_wall_ideas
    
    cache_data = get_cached_wall_ideas(page=page, per_page=per_page)
    
    return render_template('main/wall.html', 
                         ideas=cache_data['ideas'], 
                         pagination=cache_data['pagination'])


@main_bp.route('/wall/new', methods=['POST'])
@login_required
@rate_limit(limit=10, window=3600)  # 10 ideas per hour
def new_idea():
    """
    Create a new stock idea with input validation.
    Invalidates wall cache after creation.
    
    Returns:
        Redirect to wall page
    """
    title = request.form.get('title', '').strip()
    content = request.form.get('content', '').strip()
    sentiment = request.form.get('sentiment', 'neutral')
    ticker = request.form.get('ticker', '').strip().upper()
    
    # Validate required fields
    if not title or not content:
        flash('Title and content are required.', 'danger')
        return redirect(url_for('main.wall'))
    
    # Validate input lengths
    is_valid, sanitized_title, error = InputValidator.validate_length('title', title)
    if not is_valid:
        flash(error, 'danger')
        return redirect(url_for('main.wall'))
    
    is_valid, sanitized_content, error = InputValidator.validate_length('content', content)
    if not is_valid:
        flash(error, 'danger')
        return redirect(url_for('main.wall'))
    
    # Validate sentiment value
    valid_sentiments = ['bullish', 'bearish', 'neutral']
    if sentiment not in valid_sentiments:
        sentiment = 'neutral'
    
    # Validate ticker format (if provided)
    if ticker:
        # Only allow alphanumeric characters and common ticker symbols
        import re
        if not re.match(r'^[A-Z0-9\.\-]+$', ticker) or len(ticker) > 20:
            flash('Invalid ticker format.', 'danger')
            return redirect(url_for('main.wall'))
    
    idea = Idea(
        title=sanitized_title,
        content=sanitized_content,
        sentiment=sentiment,
        ticker=ticker if ticker else None,
        author_id=current_user.id
    )
    
    db.session.add(idea)
    db.session.commit()
    
    # Invalidate wall cache after new idea
    try:
        from ..utils.neon_cache import invalidate_wall_cache
        invalidate_wall_cache()
    except Exception as e:
        current_app.logger.warning(f"Failed to invalidate wall cache: {e}")
    
    flash('Your idea has been shared!', 'success')
    return redirect(url_for('main.wall'))


@main_bp.route('/wall/idea/<int:idea_id>/comment', methods=['POST'])
@login_required
@rate_limit(limit=20, window=3600)  # 20 comments per hour
def add_comment(idea_id):
    """
    Add a comment to an idea with input validation.
    
    Args:
        idea_id: ID of the idea to comment on
        
    Returns:
        Redirect to wall page
    """
    idea = Idea.query.get_or_404(idea_id)
    content = request.form.get('content', '').strip()
    
    if not content:
        flash('Comment cannot be empty.', 'danger')
        return redirect(url_for('main.wall'))
    
    # Validate input length
    is_valid, sanitized_content, error = InputValidator.validate_length('comment', content)
    if not is_valid:
        flash(error, 'danger')
        return redirect(url_for('main.wall'))
    
    comment = IdeaComment(
        idea_id=idea.id,
        author_id=current_user.id,
        content=sanitized_content
    )
    
    db.session.add(comment)
    db.session.commit()
    
    flash('Comment added!', 'success')
    return redirect(url_for('main.wall'))


@main_bp.route('/wall/idea/<int:idea_id>/like', methods=['POST'])
@login_required
def like_idea(idea_id):
    """
    Like an idea.
    In NEON_OPTIMIZE mode, skips cache invalidation for likes (non-critical).
    
    Args:
        idea_id: ID of the idea to like
        
    Returns:
        JSON response with updated like count
    """
    import os
    
    idea = Idea.query.get_or_404(idea_id)
    idea.likes_count += 1
    db.session.commit()
    
    # Skip cache invalidation for likes in NEON_OPTIMIZE mode
    # Likes are non-critical and will refresh on next page load
    if os.environ.get('NEON_OPTIMIZE', 'true').lower() != 'true':
        try:
            from ..utils.neon_cache import invalidate_wall_cache
            invalidate_wall_cache()
        except Exception:
            pass
    
    return {'success': True, 'likes': idea.likes_count}


@main_bp.route('/wall/idea/<int:idea_id>/edit', methods=['POST'])
@login_required
@rate_limit(limit=10, window=3600)
def edit_idea(idea_id):
    """
    Edit an existing idea.
    Only the author or admin can edit.
    Invalidates wall cache after edit.
    
    Args:
        idea_id: ID of the idea to edit
        
    Returns:
        Redirect to wall page
    """
    idea = Idea.query.get_or_404(idea_id)
    
    # Check permissions
    if current_user.id != idea.author_id and not current_user.is_admin:
        flash('You can only edit your own ideas.', 'danger')
        return redirect(url_for('main.wall'))
    
    title = request.form.get('title', '').strip()
    content = request.form.get('content', '').strip()
    sentiment = request.form.get('sentiment', 'neutral')
    ticker = request.form.get('ticker', '').strip().upper()
    
    # Validate required fields
    if not title or not content:
        flash('Title and content are required.', 'danger')
        return redirect(url_for('main.wall'))
    
    # Validate input lengths
    is_valid, sanitized_title, error = InputValidator.validate_length('title', title)
    if not is_valid:
        flash(error, 'danger')
        return redirect(url_for('main.wall'))
    
    is_valid, sanitized_content, error = InputValidator.validate_length('content', content)
    if not is_valid:
        flash(error, 'danger')
        return redirect(url_for('main.wall'))
    
    # Validate sentiment value
    valid_sentiments = ['bullish', 'bearish', 'neutral']
    if sentiment not in valid_sentiments:
        sentiment = 'neutral'
    
    # Validate ticker format (if provided)
    if ticker:
        import re
        if not re.match(r'^[A-Z0-9\.\-]+$', ticker) or len(ticker) > 20:
            flash('Invalid ticker format.', 'danger')
            return redirect(url_for('main.wall'))
    
    # Update idea
    idea.title = sanitized_title
    idea.content = sanitized_content
    idea.sentiment = sentiment
    idea.ticker = ticker if ticker else None
    idea.updated_at = datetime.utcnow()
    
    db.session.commit()
    
    # Invalidate wall cache after edit
    try:
        from ..utils.neon_cache import invalidate_wall_cache
        invalidate_wall_cache()
    except Exception as e:
        current_app.logger.warning(f"Failed to invalidate wall cache: {e}")
    
    flash('Your idea has been updated!', 'success')
    return redirect(url_for('main.wall'))


@main_bp.route('/wall/idea/<int:idea_id>/delete', methods=['POST'])
@login_required
def delete_idea(idea_id):
    """
    Delete an idea.
    Only the author or admin can delete.
    Invalidates wall cache after delete.
    
    Args:
        idea_id: ID of the idea to delete
        
    Returns:
        Redirect to wall page
    """
    idea = Idea.query.get_or_404(idea_id)
    
    # Check permissions
    if current_user.id != idea.author_id and not current_user.is_admin:
        flash('You can only delete your own ideas.', 'danger')
        return redirect(url_for('main.wall'))
    
    # Delete all comments first
    IdeaComment.query.filter_by(idea_id=idea.id).delete()
    
    # Delete the idea
    db.session.delete(idea)
    db.session.commit()
    
    # Invalidate wall cache after delete
    try:
        from ..utils.neon_cache import invalidate_wall_cache
        invalidate_wall_cache()
    except Exception as e:
        current_app.logger.warning(f"Failed to invalidate wall cache: {e}")
    
    flash('Idea has been deleted.', 'success')
    return redirect(url_for('main.wall'))
