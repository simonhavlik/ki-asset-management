from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify
from flask_login import login_required, current_user
from sqlalchemy import desc, func
from datetime import date, timedelta, datetime
from typing import Optional, Dict, Any, List
import logging

from ..extensions import db
from ..models import Analysis, PerformanceCalculation, Company, StockPrice, analysis_analysts, User, ActivityLog, CsvUpload, Vote, PortfolioPurchase, BenchmarkPrice
from ..utils.performance import PerformanceCalculator
from ..utils.sector_helper import get_company_sector, get_sector_distribution

analyst_bp = Blueprint('analyst', __name__, template_folder='../templates/analyst')
logger = logging.getLogger(__name__)

@analyst_bp.before_request
def before_request():
    if not current_user.is_authenticated:
        flash('Please log in to access this page.', 'warning')
        return redirect(url_for('auth.login'))
    if current_user.is_admin:
        # Admins can also view analyst pages, but we may redirect to admin dashboard?
        pass

def generate_ai_insights(performance, comparison_data):
    """Generate AI-powered insights based on performance data."""
    insights = []
    
    if performance.get('avg_return') is None:
        insights.append({
            'type': 'Getting Started',
            'text': 'Complete your first approved analysis to start tracking your performance!'
        })
        return insights
    
    avg_return = performance['avg_return']
    win_rate = performance.get('win_rate', 0)
    team_avg = comparison_data.get('team_avg', 0)
    spy_diff = comparison_data.get('spy_diff', 0)
    
    # Performance vs benchmarks
    if avg_return > team_avg:
        insights.append({
            'type': 'Performance',
            'text': f"Great job! You're outperforming the team average by {avg_return - team_avg:.1f}%. Keep up the good work!"
        })
    elif avg_return < team_avg - 5:
        insights.append({
            'type': 'Improvement Opportunity',
            'text': f"Your returns are below the team average. Consider reviewing your stock selection criteria or position sizing."
        })
    
    # Benchmark comparison
    if spy_diff > 5:
        insights.append({
            'type': 'Alpha Generation',
            'text': f"You're beating the S&P 500 by {spy_diff:.1f}%! You're generating significant alpha."
        })
    elif spy_diff < -10:
        insights.append({
            'type': 'Risk Management',
            'text': f"Consider reviewing your risk management. The S&P 500 is outperforming your picks by {abs(spy_diff):.1f}%."
        })
    
    # Win rate insights
    if win_rate >= 70:
        insights.append({
            'type': 'Consistency',
            'text': f"Excellent win rate of {win_rate:.0f}%! You're consistently picking winning stocks."
        })
    elif win_rate < 40 and performance['num_analyses'] >= 5:
        insights.append({
            'type': 'Win Rate',
            'text': f"Your win rate is {win_rate:.0f}%. Focus on improving your conviction level before making recommendations."
        })
    
    # Portfolio concentration advice
    if performance['num_analyses'] < 3:
        insights.append({
            'type': 'Diversification',
            'text': "You have fewer than 3 approved analyses. Consider building more positions for better diversification."
        })
    
    return insights[:3]  # Limit to top 3 insights


def calculate_stock_impacts(analyst_id):
    """Calculate the impact of each stock on the analyst's portfolio."""
    calculator = PerformanceCalculator()
    
    # Get all approved analyses for this analyst
    analyses = db.session.query(Analysis).join(
        analysis_analysts, Analysis.id == analysis_analysts.c.analysis_id
    ).filter(
        analysis_analysts.c.user_id == analyst_id,
        analysis_analysts.c.role == 'analyst',
        Analysis.status == 'On Watchlist'
    ).all()
    
    if not analyses:
        return []
    
    # Calculate returns and weights
    stock_data = []
    total_return_sum = 0
    
    for analysis in analyses:
        # Skip other events
        if calculator._is_other_event(analysis.company):
            continue
            
        pc = PerformanceCalculation.query.filter_by(
            analysis_id=analysis.id
        ).order_by(PerformanceCalculation.calculation_date.desc()).first()
        
        if pc and pc.return_pct is not None:
            stock_data.append({
                'analysis_id': analysis.id,
                'name': analysis.company.name,
                'ticker': analysis.company.ticker_symbol or 'N/A',
                'return_pct': float(pc.return_pct),
                'analysis_date': analysis.analysis_date
            })
            total_return_sum += float(pc.return_pct)
    
    if not stock_data:
        return []
    
    # Calculate weights and contributions
    n_stocks = len(stock_data)
    equal_weight = 1.0 / n_stocks if n_stocks > 0 else 0
    
    for stock in stock_data:
        stock['weight'] = equal_weight
        # Contribution = weight * return, normalized to show actual impact
        stock['contribution'] = equal_weight * stock['return_pct']
    
    # Sort by absolute contribution (impact)
    stock_data.sort(key=lambda x: abs(x['contribution']), reverse=True)
    
    return stock_data[:10]  # Top 10 by impact


def get_analysis_ids_for_filter(filter_type):
    """
    Get analysis IDs based on filter type.
    
    Filter types:
    - purchased: Only purchased stocks
    - board_approved: Board approved (more yes votes than no)
    - all_approved: All approved by analysts (On Watchlist)
    - approved_neutral: Approved + neutral
    - all: All stocks
    """
    if filter_type == 'purchased':
        purchases = PortfolioPurchase.query.all()
        return [p.analysis_id for p in purchases]
    
    elif filter_type == 'board_approved':
        analyses = []
        for analysis in Analysis.query.filter_by(status='On Watchlist').all():
            votes_yes = Vote.query.filter_by(analysis_id=analysis.id, vote=True).count()
            votes_no = Vote.query.filter_by(analysis_id=analysis.id, vote=False).count()
            if votes_yes > votes_no:
                analyses.append(analysis.id)
        return analyses
    
    elif filter_type == 'all_approved':
        return [a.id for a in Analysis.query.filter_by(status='On Watchlist').all()]
    
    elif filter_type == 'approved_neutral':
        return [a.id for a in Analysis.query.filter(Analysis.status.in_(['On Watchlist', 'Neutral'])).all()]
    
    else:  # all
        return [a.id for a in Analysis.query.filter(Analysis.status.in_(['On Watchlist', 'Neutral', 'Refused'])).all()]


def get_portfolio_performance_for_analyses(analysis_ids):
    """Calculate portfolio performance for a list of analysis IDs."""
    if not analysis_ids:
        return {
            'num_positions': 0,
            'total_return': None,
            'annualized_return': None,
            'start_date': None,
            'benchmark_spy': None,
            'benchmark_ftse': None,
            'benchmark_eems': None
        }
    
    analyses = Analysis.query.filter(Analysis.id.in_(analysis_ids)).all()
    
    total_return = 0.0
    annualized_return = 0.0
    count = 0
    earliest_date = None
    
    for analysis in analyses:
        perf = PerformanceCalculation.query.filter_by(
            analysis_id=analysis.id
        ).order_by(PerformanceCalculation.calculation_date.desc()).first()
        
        if perf:
            ret = float(perf.return_pct)
            total_return += ret
            
            # Calculate annualized return
            days = (date.today() - analysis.analysis_date).days
            if days > 365:
                annualized = ((1 + ret / 100) ** (365 / days) - 1) * 100
            else:
                annualized = ret
            annualized_return += annualized
            
            count += 1
            
            if earliest_date is None or analysis.analysis_date < earliest_date:
                earliest_date = analysis.analysis_date
    
    if count == 0:
        return {
            'num_positions': 0,
            'total_return': None,
            'annualized_return': None,
            'start_date': None,
            'benchmark_spy': None,
            'benchmark_ftse': None,
            'benchmark_eems': None
        }
    
    avg_return = total_return / count
    avg_annualized = annualized_return / count
    
    # Calculate benchmark returns for the same period
    from ..admin.routes import get_cached_benchmark_return
    days = (date.today() - earliest_date).days if earliest_date else 365
    
    return {
        'num_positions': count,
        'total_return': round(avg_return, 2),
        'annualized_return': round(avg_annualized, 2),
        'start_date': earliest_date.isoformat() if earliest_date else None,
        'benchmark_spy': round(get_cached_benchmark_return('SPY', days), 2),
        'benchmark_ftse': round(get_cached_benchmark_return('VT', days), 2),
        'benchmark_eems': round(get_cached_benchmark_return('EEMS', days), 2)
    }


def get_portfolio_series_for_analyses(analysis_ids, years=None, method='incremental'):
    """
    Get portfolio time series data for a list of analysis IDs.
    
    Args:
        analysis_ids: List of analysis IDs
        years: Optional time range in years
        method: 'incremental' or 'equal' - calculation method
               'incremental': Realistic portfolio simulation with rebalancing at each addition
               'equal': Simple equal-weighted average of returns
    
    Returns:
        Dict with dates and series data for charting
    """
    from ..utils.presentation_export import generate_portfolio_chart_series
    
    # Use the centralized function which supports both methods
    series_data = generate_portfolio_chart_series(analysis_ids, years=years, method=method)
    
    if not series_data or not series_data.get('dates'):
        return None
    
    # Get dates for benchmark series
    import pandas as pd
    dates = pd.to_datetime(series_data['dates'])
    
    # Get benchmark series
    from ..admin.routes import _get_benchmark_series_from_cache
    spy_series = _get_benchmark_series_from_cache(dates, 'SPY')
    vt_series = _get_benchmark_series_from_cache(dates, 'VT')
    eems_series = _get_benchmark_series_from_cache(dates, 'EEMS')
    
    return {
        'dates': series_data['dates'],
        'portfolio_series': series_data['values'],
        'spy_series': spy_series,
        'vt_series': vt_series,
        'eems_series': eems_series,
        'method': method
    }


def get_sector_statistics(analysis_ids, use_cached_only=True):
    """Get sector statistics for a list of analyses - uses cached data only to avoid blocking."""
    from ..utils.sector_helper import get_company_sector_async, get_sector_stats_cache_info
    
    sector_returns = {}
    sector_counts = {}
    
    analyses = Analysis.query.filter(Analysis.id.in_(analysis_ids)).all()
    
    for analysis in analyses:
        company = Company.query.get(analysis.company_id)
        if not company:
            continue
        
        # Use async/non-blocking version that returns cached data immediately
        sector = get_company_sector_async(company)
        if not sector:
            sector = 'Unknown'
        
        perf = PerformanceCalculation.query.filter_by(
            analysis_id=analysis.id
        ).order_by(PerformanceCalculation.calculation_date.desc()).first()
        
        if perf:
            ret = float(perf.return_pct)
            
            if sector not in sector_returns:
                sector_returns[sector] = []
                sector_counts[sector] = 0
            
            sector_returns[sector].append(ret)
            sector_counts[sector] += 1
    
    # Calculate statistics per sector
    sector_stats = []
    for sector, returns in sector_returns.items():
        if returns:
            avg_return = sum(returns) / len(returns)
            positive_count = sum(1 for r in returns if r > 0)
            positive_ratio = (positive_count / len(returns)) * 100
            
            # Calculate risk (standard deviation)
            if len(returns) > 1:
                mean = avg_return
                variance = sum((r - mean) ** 2 for r in returns) / len(returns)
                risk = variance ** 0.5
            else:
                risk = 0
            
            sector_stats.append({
                'sector': sector,
                'count': sector_counts[sector],
                'avg_return': round(avg_return, 2),
                'positive_ratio': round(positive_ratio, 2),
                'risk': round(risk, 2),
                'min_return': round(min(returns), 2),
                'max_return': round(max(returns), 2)
            })
    
    # Sort by different metrics
    by_return = sorted(sector_stats, key=lambda x: x['avg_return'], reverse=True)[:5]
    by_risk = sorted(sector_stats, key=lambda x: x['risk'], reverse=True)[:5]
    
    # Get cache info
    cache_info = get_sector_stats_cache_info()
    
    return {
        'all_sectors': sector_stats,
        'top_by_return': by_return,
        'top_by_risk': by_risk,
        'sector_counts': sector_counts,
        'cache_info': cache_info
    }


def get_cached_benchmark_return(ticker, days):
    """
    Calculate benchmark return using cached BenchmarkPrice data.
    Falls back to approximate calculation if no cached data.
    """
    try:
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        start_price = BenchmarkPrice.query.filter(
            BenchmarkPrice.ticker == ticker,
            BenchmarkPrice.date <= start_date
        ).order_by(BenchmarkPrice.date.desc()).first()
        
        end_price = BenchmarkPrice.query.filter(
            BenchmarkPrice.ticker == ticker,
            BenchmarkPrice.date <= end_date
        ).order_by(BenchmarkPrice.date.desc()).first()
        
        if start_price and end_price:
            return ((float(end_price.close_price) - float(start_price.close_price)) / 
                    float(start_price.close_price)) * 100
    except Exception as e:
        pass
    
    # Fallback to approximate calculation
    annual_returns = {'SPY': 10.0, 'VT': 9.0, 'EEMS': 7.0}
    annual = annual_returns.get(ticker, 8.0)
    years = days / 365.0
    return ((1 + annual/100) ** years - 1) * 100


def _get_benchmark_series_from_cache(dates, ticker):
    """
    Get benchmark return series from cached BenchmarkPrice data.
    Falls back to synthetic data if cache is empty.
    
    Uses simple linear extrapolation for missing data to avoid compounding errors.
    """
    series = []
    
    if not dates:
        return series
    
    # Normalize dates to datetime objects
    normalized_dates = []
    for d in dates:
        if hasattr(d, 'date') and callable(getattr(d, 'date')):
            normalized_dates.append(d.date() if hasattr(d, 'date') else d)
        else:
            normalized_dates.append(d)
    
    first_date = normalized_dates[0]
    
    # Get base price (price at or before first date)
    base_price_rec = BenchmarkPrice.query.filter(
        BenchmarkPrice.ticker == ticker,
        BenchmarkPrice.date <= first_date
    ).order_by(BenchmarkPrice.date.desc()).first()
    
    if base_price_rec is None:
        # Try to get earliest price after first date
        base_price_rec = BenchmarkPrice.query.filter(
            BenchmarkPrice.ticker == ticker,
            BenchmarkPrice.date >= first_date
        ).order_by(BenchmarkPrice.date.asc()).first()
    
    if base_price_rec is None:
        # No data at all - use approximate synthetic data
        approx_prices = {'SPY': 400.0, 'VT': 100.0, 'EEMS': 50.0}
        base_price = approx_prices.get(ticker, 100.0)
        
        # Generate simple synthetic series based on annual return
        annual = {'SPY': 10.0, 'VT': 9.0, 'EEMS': 7.0}.get(ticker, 8.0)
        for i, current_date in enumerate(normalized_dates):
            days_from_start = (current_date - first_date).days
            ret = (annual / 365.0) * days_from_start
            series.append(round(ret, 2))
        return series
    
    base_price = float(base_price_rec.close_price)
    base_price_date = base_price_rec.date
    
    # Get all available prices for this ticker up to the last date
    last_date = normalized_dates[-1]
    all_prices = {}
    for bp in BenchmarkPrice.query.filter(
        BenchmarkPrice.ticker == ticker,
        BenchmarkPrice.date <= last_date
    ).all():
        all_prices[bp.date] = float(bp.close_price)
    
    if not all_prices:
        # No prices at all - return flat line
        return [0.0] * len(normalized_dates)
    
    # Build series with interpolation for missing dates
    last_known_price = base_price
    last_known_date = base_price_date
    
    for i, current_date in enumerate(normalized_dates):
        if current_date in all_prices:
            # Use actual price
            price = all_prices[current_date]
            ret = ((price - base_price) / base_price) * 100
            series.append(round(ret, 2))
            last_known_price = price
            last_known_date = current_date
        else:
            # Find the most recent price before this date
            most_recent_date = None
            most_recent_price = None
            for d, p in sorted(all_prices.items()):
                if d <= current_date:
                    most_recent_date = d
                    most_recent_price = p
                else:
                    break
            
            if most_recent_price is not None:
                # Use the most recent known price
                ret = ((most_recent_price - base_price) / base_price) * 100
                series.append(round(ret, 2))
                last_known_price = most_recent_price
                last_known_date = most_recent_date
            else:
                # No data yet - use base price (0% return)
                series.append(0.0)
    
    return series


def get_analyst_rankings():
    """Get various analyst rankings."""
    calculator = PerformanceCalculator()
    
    # Get all analysts performance
    all_perfs = calculator.get_all_analysts_performance()
    
    # 1. Top 5 by board approved analyses
    board_approved_counts = []
    for user in User.query.all():
        count = db.session.query(Analysis).join(
            analysis_analysts, Analysis.id == analysis_analysts.c.analysis_id
        ).filter(
            analysis_analysts.c.user_id == user.id,
            analysis_analysts.c.role == 'analyst',
            Analysis.status == 'On Watchlist'
        ).count()
        board_approved_counts.append({
            'analyst_id': user.id,
            'analyst_name': user.full_name or user.email.split('@')[0],
            'count': count
        })
    top_board_approved = sorted(board_approved_counts, key=lambda x: x['count'], reverse=True)[:5]
    
    # 2. Top 5 by total analyses (approved + neutral + refused)
    total_counts = []
    for user in User.query.all():
        count = db.session.query(Analysis).join(
            analysis_analysts, Analysis.id == analysis_analysts.c.analysis_id
        ).filter(
            analysis_analysts.c.user_id == user.id,
            analysis_analysts.c.role == 'analyst',
            Analysis.status.in_(['On Watchlist', 'Neutral', 'Refused'])
        ).count()
        total_counts.append({
            'analyst_id': user.id,
            'analyst_name': user.full_name or user.email.split('@')[0],
            'count': count
        })
    top_total = sorted(total_counts, key=lambda x: x['count'], reverse=True)[:5]
    
    # 3. Top 5 by win rate (min 3 analyses)
    win_rates = []
    for perf in all_perfs:
        if perf['num_analyses'] >= 3 and perf['win_rate'] is not None:
            win_rates.append({
                'analyst_id': perf['analyst_id'],
                'analyst_name': perf['analyst_name'],
                'win_rate': perf['win_rate'],
                'num_analyses': perf['num_analyses']
            })
    top_win_rate = sorted(win_rates, key=lambda x: x['win_rate'], reverse=True)[:5]
    
    # 4. Top 5 by performance
    top_performance = sorted(
        [p for p in all_perfs if p['avg_return'] is not None],
        key=lambda x: x['avg_return'],
        reverse=True
    )[:5]
    
    return {
        'top_board_approved': top_board_approved,
        'top_total': top_total,
        'top_win_rate': top_win_rate,
        'top_performance': top_performance
    }


@analyst_bp.route('/')
@login_required
def dashboard():
    """Analyst dashboard with personal statistics."""
    # If admin, include admin dashboard data
    if current_user.is_admin:
        from ..models import User, ActivityLog, CsvUpload, Company
        
        # Gather admin stats
        total_users = User.query.count()
        active_users = User.query.filter_by(is_active=True).count()
        admin_users = User.query.filter_by(is_admin=True).count()
        
        total_analyses = Analysis.query.count()
        approved_analyses_count = Analysis.query.filter_by(status='On Watchlist').count()
        
        total_companies = Company.query.count()
        csv_uploads = CsvUpload.query.count()
        
        # Recent activity
        recent_activity = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).limit(10).all()
        
        admin_stats = {
            'total_users': total_users,
            'active_users': active_users,
            'admin_users': admin_users,
            'total_analyses': total_analyses,
            'approved_analyses': approved_analyses_count,
            'total_companies': total_companies,
            'csv_uploads': csv_uploads
        }
    else:
        admin_stats = None
        recent_activity = None
    
    calculator = PerformanceCalculator()
    
    # Count analyses where user is analyst (role 'analyst')
    my_analyses = db.session.query(Analysis).join(
        analysis_analysts, Analysis.id == analysis_analysts.c.analysis_id
    ).filter(
        analysis_analysts.c.user_id == current_user.id,
        analysis_analysts.c.role == 'analyst'
    ).all()
    
    approved = [a for a in my_analyses if a.status == 'On Watchlist']
    
    # Calculate performance
    perf = calculator.get_analyst_performance(current_user.id)
    
    # Get all analysts performance for comparison
    all_perfs = calculator.get_all_analysts_performance()
    
    # Calculate team average and find best analyst
    returns = [p['avg_return'] for p in all_perfs if p['avg_return'] is not None]
    team_avg_return = sum(returns) / len(returns) if returns else 0
    best_analyst_return = max(returns) if returns else 0
    
    # Find user's rank
    analyst_rank = 1
    total_analysts = len(all_perfs)
    for i, p in enumerate(all_perfs, 1):
        if p['analyst_id'] == current_user.id:
            analyst_rank = i
            break
    
    # Get benchmark comparisons
    spy_return = 15.0  # S&P 500 approximate
    vt_return = 12.0   # FTSE All-World approximate
    
    user_return = perf.get('avg_return') or 0
    benchmark_comparison = {
        'spy_diff': user_return - spy_return,
        'vt_diff': user_return - vt_return
    }
    
    comparison_data = {
        'team_avg': team_avg_return,
        'spy_diff': benchmark_comparison['spy_diff'],
        'vt_diff': benchmark_comparison['vt_diff']
    }
    
    # Generate AI insights
    ai_insights = generate_ai_insights(perf, comparison_data)
    
    # Calculate stock impacts
    stock_impacts = calculate_stock_impacts(current_user.id)
    
    # Recent analyses
    recent = db.session.query(Analysis).join(
        analysis_analysts, Analysis.id == analysis_analysts.c.analysis_id
    ).filter(
        analysis_analysts.c.user_id == current_user.id
    ).order_by(desc(Analysis.analysis_date)).limit(10).all()
    
    return render_template('analyst/dashboard.html',
                           total_analyses=len(my_analyses),
                           approved_analyses=len(approved),
                           performance=perf,
                           recent_analyses=recent,
                           team_avg_return=team_avg_return,
                           best_analyst_return=best_analyst_return,
                           analyst_rank=analyst_rank,
                           total_analysts=total_analysts,
                           benchmark_comparison=benchmark_comparison,
                           ai_insights=ai_insights,
                           stock_impacts=stock_impacts,
                           admin_stats=admin_stats,
                           recent_activity=recent_activity)


@analyst_bp.route('/performance')
@login_required
def performance():
    """Detailed performance view for the logged‑in analyst."""
    annualized = request.args.get('annualized', 'false').lower() == 'true'
    calculator = PerformanceCalculator()
    perf = calculator.get_analyst_performance(current_user.id, annualized=annualized)
    
    # Get list of analyses with performance calculations
    analyses = db.session.query(Analysis).join(
        analysis_analysts, Analysis.id == analysis_analysts.c.analysis_id
    ).filter(
        analysis_analysts.c.user_id == current_user.id,
        analysis_analysts.c.role == 'analyst',
        Analysis.status == 'On Watchlist'
    ).all()
    
    # Attach latest performance calculation for each analysis
    analysis_data = []
    for a in analyses:
        pc = PerformanceCalculation.query.filter_by(
            analysis_id=a.id
        ).order_by(PerformanceCalculation.calculation_date.desc()).first()
        annualized_return = None
        if pc and annualized:
            annualized_return = calculator._annualize_return(
                float(pc.return_pct), a.analysis_date, pc.calculation_date
            )
        analysis_data.append({
            'analysis': a,
            'performance': pc,
            'company': a.company,
            'annualized_return': annualized_return
        })
    
    return render_template('analyst/performance.html',
                           performance=perf,
                           analysis_data=analysis_data,
                           annualized=annualized)


@analyst_bp.route('/overview')
@login_required
def overview():
    """
    Overview page with portfolio charts, sector statistics, and analyst rankings.
    Uses 7-day caching for fast filter switching with smart view hierarchy.
    Auto-refreshes if cache is older than 7 days.
    Supports two calculation methods:
    - incremental: Realistic portfolio simulation with rebalancing
    - equal: Simple equal-weighted average
    """
    from ..utils.overview_cache import (
        get_cached_overview_data, save_overview_cache, 
        get_cache_status, should_use_cache, get_cache_age_days
    )
    from ..utils.unified_calculator import UnifiedDataCalculator, recalculate_all_unified
    
    # Get filter and method from request
    current_filter = request.args.get('filter', 'board_approved')
    calc_method = request.args.get('method', 'incremental')
    force_refresh = request.args.get('refresh') == 'true' and current_user.is_admin
    
    # Validate method parameter
    if calc_method not in ['incremental', 'equal']:
        calc_method = 'incremental'
    
    # Check if we should auto-refresh (cache older than 7 days)
    cache_key = f"{current_filter}_{calc_method}"
    cache_age_days = get_cache_age_days(cache_key)
    auto_refresh = cache_age_days is None or cache_age_days >= 7
    
    # Try to get cached data
    cache_data = None
    from_cache = False
    
    if not force_refresh and not auto_refresh:
        # Try the specific cache first
        cache_data = get_cached_overview_data(cache_key)
        
        # If not found, try broader view caches (smart filtering)
        if not cache_data:
            cache_data = _try_broader_view_cache(current_filter, calc_method)
    
    if cache_data and not force_refresh:
        # Use cached data
        portfolio_performance = cache_data['portfolio_performance']
        series_all = cache_data['series_all']
        series_1y = cache_data['series_1y']
        sector_stats = cache_data['sector_stats']
        analyst_rankings = cache_data['analyst_rankings']
        positive_ratio = cache_data['positive_ratio']
        total_with_perf = cache_data.get('total_positions', 0)
        from_cache = True
    else:
        # Need to calculate fresh data
        # Use unified calculator for efficient recalculation
        if auto_refresh and not force_refresh:
            logger.info(f"Auto-refreshing overview data (cache is {cache_age_days} days old)")
        
        # Use unified calculator
        calculator = UnifiedDataCalculator()
        all_views_data = calculator.recalculate_all(force=force_refresh)
        
        # Get data for current view (cache keys now include method)
        view_cache_key = f"{current_filter}_{calc_method}"
        view_data = all_views_data.get(view_cache_key, {})
        
        portfolio_performance = view_data.get('portfolio_performance', {})
        series_all = view_data.get('series_all')
        series_1y = view_data.get('series_1y')
        sector_stats = view_data.get('sector_stats', {})
        analyst_rankings = view_data.get('analyst_rankings', {})
        positive_ratio = view_data.get('positive_ratio', 0)
        total_with_perf = view_data.get('total_positions', 0)
        
        # Save all views to cache (keys already include method from calculator)
        for view_cache_key, view_data in all_views_data.items():
            save_overview_cache(view_cache_key, view_data)
        
        from_cache = False
    
    # Get cache status for admin
    cache_status = get_cache_status() if current_user.is_admin else None
    
    # Check if we need to show auto-refresh notice
    needs_refresh = cache_age_days is not None and cache_age_days >= 7
    
    return render_template('analyst/overview.html',
                           current_filter=current_filter,
                           calc_method=calc_method,
                           portfolio_performance=portfolio_performance,
                           series_all=series_all,
                           series_1y=series_1y,
                           sector_stats=sector_stats,
                           analyst_rankings=analyst_rankings,
                           positive_ratio=positive_ratio,
                           total_positions=total_with_perf,
                           from_cache=from_cache,
                           cache_status=cache_status,
                           needs_refresh=needs_refresh)


def _try_broader_view_cache(current_filter: str, calc_method: str) -> Optional[Dict]:
    """
    Try to find cached data from a broader view that can filter to current view.
    
    View hierarchy: all > approved_neutral > all_approved > board_approved > purchased
    
    Returns cached data if found and can be filtered, None otherwise.
    
    NOTE: Currently disabled because returning broader view data without
    recalculating series causes incorrect benchmark values. Each view must
    have its own correctly calculated series data.
    """
    # DISABLED: Broader view cache lookup causes incorrect benchmark series
    # because series data needs to be recalculated for each specific view's
    # date range and analysis set. Returning broader view data results in
    # wrong benchmark amplitudes for narrower views.
    return None


@analyst_bp.route('/analyses')
@login_required
def analyses():
    """List all analyses where the user is involved (as analyst or opponent)."""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    analyses_query = db.session.query(Analysis).join(
        analysis_analysts, Analysis.id == analysis_analysts.c.analysis_id
    ).filter(
        analysis_analysts.c.user_id == current_user.id
    ).order_by(desc(Analysis.analysis_date))
    
    pagination = analyses_query.paginate(page=page, per_page=per_page)
    
    return render_template('analyst/analyses.html', pagination=pagination)


# =============================================================================
# SSE Progress Endpoint for Real-time Recalculation
# =============================================================================

@analyst_bp.route('/recalculate-progress')
@login_required
def recalculate_progress():
    """
    SSE endpoint for real-time recalculation progress updates.
    Streams progress data as server-sent events.
    """
    from ..utils.unified_calculator import get_progress
    import json
    import time
    
    def generate():
        last_status = None
        last_logs_count = 0
        idle_count = 0
        
        while True:
            progress = get_progress()
            current_status = progress.status
            current_logs = progress.logs
            
            # Always send first update to establish connection
            # Then only send if something changed
            should_send = (last_status is None or 
                          current_status != last_status or 
                          len(current_logs) != last_logs_count)
            
            if should_send:
                data = progress.to_dict()
                yield f"data: {json.dumps(data)}\n\n"
                
                last_status = current_status
                last_logs_count = len(current_logs)
                idle_count = 0
                
                # If completed or error, stop streaming after a few more seconds
                if current_status in ['completed', 'error']:
                    # Keep connection open a bit longer to ensure client gets final state
                    time.sleep(2)
                    yield f"data: {json.dumps(progress.to_dict())}\n\n"
                    break
            else:
                # Send heartbeat every 10 seconds to keep connection alive
                idle_count += 1
                if idle_count >= 20:  # 20 * 0.5s = 10 seconds
                    yield f"data: {json.dumps(progress.to_dict())}\n\n"
                    idle_count = 0
            
            time.sleep(0.5)  # Poll every 500ms
    
    return current_app.response_class(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'  # Disable nginx buffering
        }
    )


@analyst_bp.route('/recalculate-all', methods=['POST'])
@login_required
def recalculate_all():
    """
    Trigger full recalculation of all overview data.
    Returns immediately and continues calculation in background.
    """
    logger.info(f"Recalculate-all called by user: {current_user.email} (admin: {current_user.is_admin})")
    
    if not current_user.is_admin:
        logger.warning(f"Unauthorized recalculation attempt by {current_user.email}")
        return jsonify({'error': 'Unauthorized - Admin access required'}), 403
    
    from ..utils.unified_calculator import recalculate_all_unified, reset_progress, get_progress, is_calculation_running
    from ..utils.overview_cache import save_overview_cache, invalidate_cache
    import threading
    
    # Check if already running
    if is_calculation_running():
        logger.warning("Recalculation already in progress")
        return jsonify({'error': 'Recalculation already in progress'}), 409
    
    # Capture the app in the closure
    app = current_app._get_current_object()
    
    def run_recalculation():
        """Run recalculation in background thread."""
        logger.info("Background recalculation thread started")
        try:
            with app.app_context():
                all_views_data = recalculate_all_unified(force=True)
                
                # Save all views to cache (keys already include method from calculator)
                for cache_key, view_data in all_views_data.items():
                    save_overview_cache(cache_key, view_data)
                
                logger.info("Background recalculation completed successfully")
        except Exception as e:
            logger.exception("Error during background recalculation")
            progress = get_progress()
            progress.update_status("error")
            progress.log(f"ERROR: {str(e)}")
    
    try:
        # Reset progress and start recalculation in background
        reset_progress()
        progress = get_progress()
        progress.log("Recalculation endpoint called - starting background thread...")
        
        # Start recalculation in background thread
        thread = threading.Thread(target=run_recalculation, name="RecalculationThread")
        thread.daemon = True
        thread.start()
        
        logger.info("Recalculation background thread started successfully")
        
        return jsonify({
            'success': True,
            'message': 'Recalculation started in background'
        })
        
    except Exception as e:
        logger.exception("Error starting recalculation")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
