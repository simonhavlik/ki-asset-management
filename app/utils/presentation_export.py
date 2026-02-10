"""
Presentation export module for creating fiscal.ai-style charts and tables.

Generates presentation-ready:
- High-resolution charts with daily datapoints
- Analyst summary tables
- Sector analysis tables (best & risk)
- Growth timeline visualizations
- PowerPoint export
"""

import io
import base64
import json
import logging
import os
from datetime import datetime, timedelta, date
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict

import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle
from matplotlib.ticker import FuncFormatter
import numpy as np

from sqlalchemy import func, desc, distinct
from ..extensions import db
from ..models import (
    Analysis, User, Company, PerformanceCalculation, 
    AnalystMapping, PortfolioPurchase, CompanySectorCache, Vote,
    StockPrice
)

logger = logging.getLogger(__name__)

# Professional color palette
COLORS = {
    'primary': '#2563eb',      # Blue
    'secondary': '#10b981',    # Green
    'accent': '#f59e0b',       # Amber
    'danger': '#ef4444',       # Red
    'purple': '#8b5cf6',       # Purple
    'cyan': '#06b6d4',         # Cyan
    'gray': '#6b7280',         # Gray
    'light_gray': '#e5e7eb',   # Light gray
    'background': '#fafafa',   # Background
    'grid': '#e5e7eb',         # Grid lines
}

CHART_STYLE = {
    'figure.facecolor': 'white',
    'axes.facecolor': 'white',
    'axes.edgecolor': COLORS['light_gray'],
    'axes.grid': True,
    'grid.alpha': 0.3,
    'grid.color': COLORS['grid'],
    'axes.labelcolor': COLORS['gray'],
    'text.color': '#374151',
    'xtick.color': COLORS['gray'],
    'ytick.color': COLORS['gray'],
    'font.size': 10,
    'axes.titlesize': 14,
    'axes.labelsize': 11,
}

plt.rcParams.update(CHART_STYLE)


def format_return_pct(x, pos):
    """Format y-axis as percentage."""
    return f'{x:+.0f}%'


def generate_portfolio_chart_series(analysis_ids: List[int], years: Optional[int] = None, method: str = 'incremental') -> Dict:
    """
    Generate portfolio performance chart data with monthly datapoints.
    
    Supports two calculation methods:
    - 'equal': Traditional equal-weighted average (each position weighted equally)
    - 'incremental': Incremental equal-weight rebalancing (realistic portfolio simulation)
    
    The incremental method simulates actually managing a portfolio:
    - Start with 100% in the first stock
    - When adding the Nth stock, rebalance to equal weights (each gets 1/N of total value)
    - This reflects real portfolio management where you sell portions of existing holdings
      to fund new positions, maintaining equal weight allocation
    
    Args:
        analysis_ids: List of analysis IDs to include
        years: Optional limit to last N years
        method: 'equal' or 'incremental' (default: incremental)
    
    Returns:
        Dict with dates and values for charting
    """
    from ..models import StockPrice, Company
    
    if not analysis_ids:
        return {'dates': [], 'values': []}
    
    # Get analyses
    analyses = Analysis.query.filter(Analysis.id.in_(analysis_ids)).all()
    if not analyses:
        return {'dates': [], 'values': []}
    
    # Sort by analysis date
    analyses = sorted(analyses, key=lambda x: x.analysis_date)
    end_date = date.today()
    
    # Determine date range based on years parameter
    # This ensures benchmark comparisons are consistent across views
    if years:
        # Use fixed date range (e.g., last 12 months from today)
        # This ensures benchmarks start from the same point regardless of view
        earliest_date = end_date - timedelta(days=years*365)
        # Filter analyses to only those within the date range
        analyses = [a for a in analyses if a.analysis_date >= earliest_date]
    else:
        # For 'all' series, use the earliest analysis date
        earliest_date = analyses[0].analysis_date if analyses else end_date
    
    # Generate monthly date points
    try:
        import pandas as pd
        dates = pd.date_range(start=earliest_date, end=end_date, freq='MS')
        if len(dates) < 3:
            dates = pd.date_range(start=earliest_date, end=end_date, periods=6)
    except ImportError:
        # Fallback without pandas
        dates = []
        current = earliest_date
        while current <= end_date:
            dates.append(current)
            # Add approximately one month
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)
    
    date_labels = []
    values = []
    
    for d in dates:
        date_str = d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d)
        date_labels.append(date_str)
        current_date = d.date() if hasattr(d, 'date') else d
        
        # Get all stocks that have been analyzed by this date
        active_analyses = [a for a in analyses if a.analysis_date <= current_date]
        
        if not active_analyses:
            values.append(0)
            continue
        
        if method == 'incremental':
            # Incremental equal-weight rebalancing method
            # Simulates actual portfolio management
            values.append(calculate_incremental_portfolio_value(active_analyses, current_date))
        else:
            # Traditional equal-weighted average
            total_ret = 0
            count = 0
            
            for analysis in active_analyses:
                company = Company.query.get(analysis.company_id)
                if not company or not company.ticker_symbol:
                    continue
                
                # Get price at analysis date
                entry_price = StockPrice.query.filter(
                    StockPrice.company_id == company.id,
                    StockPrice.date <= analysis.analysis_date
                ).order_by(StockPrice.date.desc()).first()
                
                # Get price at current chart date
                current_price = StockPrice.query.filter(
                    StockPrice.company_id == company.id,
                    StockPrice.date <= current_date
                ).order_by(StockPrice.date.desc()).first()
                
                if entry_price and current_price and float(entry_price.close_price) > 0:
                    ret = ((float(current_price.close_price) - float(entry_price.close_price)) / 
                           float(entry_price.close_price)) * 100
                    total_ret += ret
                    count += 1
            
            if count > 0:
                values.append(round(total_ret / count, 2))
            else:
                values.append(0)
    
    return {
        'dates': date_labels,
        'values': values,
        'count': len(date_labels),
        'method': method
    }


def calculate_incremental_portfolio_value(analyses: List, current_date: date) -> float:
    """
    Calculate portfolio value using incremental equal-weight rebalancing.
    
    This simulates a realistic portfolio where each new position causes rebalancing:
    - Start with 100% in first stock
    - When adding 2nd stock: sell 50% of 1st, buy 2nd (now 50/50)
    - When adding 3rd stock: sell 33% of each, buy 3rd (now 33/33/33)
    - And so on...
    
    Args:
        analyses: List of Analysis objects sorted by date
        current_date: Date to calculate value for
        
    Returns:
        Portfolio return percentage relative to initial investment
    """
    from ..models import StockPrice, Company
    
    if not analyses:
        return 0
    
    # Track portfolio state: {analysis_id: {'shares': x, 'entry_date': date}}
    portfolio = {}
    total_value = 100.0  # Start with 100 units (representing 100%)
    
    for i, analysis in enumerate(analyses):
        company = Company.query.get(analysis.company_id)
        if not company or not company.ticker_symbol:
            continue
        
        # Get price at analysis date (entry)
        entry_price = StockPrice.query.filter(
            StockPrice.company_id == company.id,
            StockPrice.date <= analysis.analysis_date
        ).order_by(StockPrice.date.desc()).first()
        
        if not entry_price or float(entry_price.close_price) <= 0:
            continue
        
        entry_price_val = float(entry_price.close_price)
        
        if i == 0:
            # First stock: allocate 100% of portfolio
            shares = total_value / entry_price_val
            portfolio[analysis.id] = {
                'company_id': company.id,
                'shares': shares,
                'entry_date': analysis.analysis_date,
                'entry_price': entry_price_val
            }
        else:
            # Subsequent stocks: rebalance to equal weights
            # 1. Calculate current portfolio value before rebalancing
            current_portfolio_value = 0
            for pid, pos in portfolio.items():
                # Get current price at the new entry date
                current_price = StockPrice.query.filter(
                    StockPrice.company_id == pos['company_id'],
                    StockPrice.date <= analysis.analysis_date
                ).order_by(StockPrice.date.desc()).first()
                
                if current_price:
                    current_portfolio_value += pos['shares'] * float(current_price.close_price)
            
            # 2. Add new stock with 1/(i+1) of total value
            new_allocation = current_portfolio_value / (i + 1)
            new_shares = new_allocation / entry_price_val
            
            # 3. Rebalance existing positions to equal weights
            # Each position (including new) should have 1/(i+1) of total
            portfolio[analysis.id] = {
                'company_id': company.id,
                'shares': new_shares,
                'entry_date': analysis.analysis_date,
                'entry_price': entry_price_val
            }
            
            # Rebalance existing positions
            for pid, pos in portfolio.items():
                if pid != analysis.id:
                    # Get price at rebalancing date
                    rebalance_price = StockPrice.query.filter(
                        StockPrice.company_id == pos['company_id'],
                        StockPrice.date <= analysis.analysis_date
                    ).order_by(StockPrice.date.desc()).first()
                    
                    if rebalance_price:
                        old_value = pos['shares'] * float(rebalance_price.close_price)
                        # New value should be equal allocation
                        new_value = current_portfolio_value / (i + 1)
                        # Adjust shares
                        pos['shares'] = pos['shares'] * (new_value / old_value) if old_value > 0 else pos['shares']
    
    # Calculate final portfolio value at current_date
    final_value = 0
    for pid, pos in portfolio.items():
        current_price = StockPrice.query.filter(
            StockPrice.company_id == pos['company_id'],
            StockPrice.date <= current_date
        ).order_by(StockPrice.date.desc()).first()
        
        if current_price:
            final_value += pos['shares'] * float(current_price.close_price)
        else:
            # Use last known price if no data for current date
            final_value += pos['shares'] * pos['entry_price']
    
    # Return percentage gain/loss
    if total_value > 0:
        return round(((final_value - total_value) / total_value) * 100, 2)
    return 0


def create_performance_chart(
    series_data: Dict[str, Any],
    title: str = "Portfolio Performance",
    width: int = 12,
    height: int = 6,
    dpi: int = 150
) -> bytes:
    """
    Create a beautiful performance chart image.
    
    Args:
        series_data: Dict with dates and values
        title: Chart title
        width: Figure width in inches
        height: Figure height in inches
        dpi: Resolution
        
    Returns:
        PNG image bytes
    """
    fig, ax = plt.subplots(figsize=(width, height), dpi=dpi)
    
    date_strings = series_data.get('dates', [])
    values = series_data.get('values', [])
    
    if not date_strings:
        ax.text(0.5, 0.5, 'No data available', 
                ha='center', va='center', transform=ax.transAxes,
                fontsize=14, color=COLORS['gray'])
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', 
                   facecolor='white', edgecolor='none')
        buf.seek(0)
        plt.close(fig)
        return buf.getvalue()
    
    # Parse string dates to datetime objects
    dates = []
    for d in date_strings:
        if isinstance(d, str):
            try:
                dates.append(datetime.strptime(d, '%Y-%m-%d'))
            except ValueError:
                continue
        else:
            dates.append(d)
    
    if not dates or len(dates) != len(values):
        ax.text(0.5, 0.5, 'Invalid data', 
                ha='center', va='center', transform=ax.transAxes,
                fontsize=14, color=COLORS['gray'])
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', 
                   facecolor='white', edgecolor='none')
        buf.seek(0)
        plt.close(fig)
        return buf.getvalue()
    
    # Plot line with gradient fill
    ax.plot(dates, values, color=COLORS['primary'], linewidth=2.5, label='Portfolio')
    
    # Add gradient fill
    ax.fill_between(dates, values, alpha=0.15, color=COLORS['primary'])
    
    # Add zero line
    ax.axhline(y=0, color=COLORS['gray'], linestyle='--', alpha=0.5, linewidth=1)
    
    # Color positive/negative regions
    for i in range(len(dates)-1):
        if values[i] >= 0:
            ax.fill_between([dates[i], dates[i+1]], [values[i], values[i+1]], 
                          0, alpha=0.1, color=COLORS['secondary'])
        else:
            ax.fill_between([dates[i], dates[i+1]], [values[i], values[i+1]], 
                          0, alpha=0.1, color=COLORS['danger'])
    
    # Formatting
    ax.set_title(title, fontweight='bold', pad=20, fontsize=16)
    ax.set_xlabel('Date', fontweight='medium')
    ax.set_ylabel('Return (%)', fontweight='medium')
    
    # Format y-axis as percentage
    ax.yaxis.set_major_formatter(FuncFormatter(format_return_pct))
    
    # Format x-axis dates
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.xticks(rotation=45, ha='right')
    
    # Add latest value annotation
    if values:
        latest_val = values[-1]
        latest_date = dates[-1]
        color = COLORS['secondary'] if latest_val >= 0 else COLORS['danger']
        ax.annotate(f'{latest_val:+.1f}%',
                   xy=(latest_date, latest_val),
                   xytext=(10, 10), textcoords='offset points',
                   bbox=dict(boxstyle='round,pad=0.5', facecolor=color, alpha=0.9),
                   color='white', fontweight='bold', fontsize=11)
    
    plt.tight_layout()
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', 
               facecolor='white', edgecolor='none', dpi=dpi)
    buf.seek(0)
    plt.close(fig)
    
    return buf.getvalue()


def create_comparison_chart(
    portfolio_data: Dict,
    spy_data: Dict,
    vt_data: Dict,
    title: str = "Portfolio vs Benchmarks",
    width: int = 12,
    height: int = 6,
    dpi: int = 150
) -> bytes:
    """Create multi-line comparison chart."""
    fig, ax = plt.subplots(figsize=(width, height), dpi=dpi)
    
    # Plot each series
    if portfolio_data.get('dates'):
        ax.plot(portfolio_data['dates'], portfolio_data['values'], 
               color=COLORS['primary'], linewidth=2.5, label='KI Portfolio')
    
    if spy_data.get('dates'):
        ax.plot(spy_data['dates'], spy_data['values'], 
               color=COLORS['accent'], linewidth=2, linestyle='--', label='S&P 500')
    
    if vt_data.get('dates'):
        ax.plot(vt_data['dates'], vt_data['values'], 
               color=COLORS['cyan'], linewidth=2, linestyle='-.', label='FTSE All-World')
    
    ax.axhline(y=0, color=COLORS['gray'], linestyle='--', alpha=0.5, linewidth=1)
    
    ax.set_title(title, fontweight='bold', pad=20, fontsize=16)
    ax.set_xlabel('Date', fontweight='medium')
    ax.set_ylabel('Return (%)', fontweight='medium')
    ax.yaxis.set_major_formatter(FuncFormatter(format_return_pct))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.xticks(rotation=45, ha='right')
    ax.legend(loc='upper left', framealpha=0.95)
    
    plt.tight_layout()
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight',
               facecolor='white', edgecolor='none', dpi=dpi)
    buf.seek(0)
    plt.close(fig)
    
    return buf.getvalue()


def get_analyst_summary_table() -> Dict[str, Any]:
    """
    Get comprehensive analyst summary for presentation tables.
    
    Returns:
        Dict with columns and rows for analyst table
    """
    from ..models import analysis_analysts
    
    users = User.query.filter_by(is_active=True).all()
    
    rows = []
    for user in users:
        # Count analyses where user is analyst (role='analyst')
        as_analyst = db.session.query(analysis_analysts).filter(
            analysis_analysts.c.user_id == user.id,
            analysis_analysts.c.role == 'analyst'
        ).count()
        
        # Count analyses where user is opponent (role='opponent')
        as_opponent = db.session.query(analysis_analysts).filter(
            analysis_analysts.c.user_id == user.id,
            analysis_analysts.c.role == 'opponent'
        ).count()
        
        total_analyses = as_analyst + as_opponent
        
        # Skip analysts with no analyses
        if total_analyses == 0:
            continue
        
        # Count approved (watchlist) analyses
        approved_analyses = db.session.query(analysis_analysts).join(
            Analysis, analysis_analysts.c.analysis_id == Analysis.id
        ).filter(
            analysis_analysts.c.user_id == user.id,
            Analysis.status == 'On Watchlist'
        ).count()
        
        # Count investments (purchased) - analyses with purchases where user is involved
        user_analysis_ids = db.session.query(analysis_analysts.c.analysis_id).filter(
            analysis_analysts.c.user_id == user.id
        ).subquery()
        
        investment_count = PortfolioPurchase.query.filter(
            PortfolioPurchase.analysis_id.in_(user_analysis_ids)
        ).distinct(PortfolioPurchase.analysis_id).count()
        
        # Calculate average return on approved analyses
        avg_return_result = db.session.query(
            func.avg(PerformanceCalculation.return_pct)
        ).join(
            Analysis, PerformanceCalculation.analysis_id == Analysis.id
        ).join(
            analysis_analysts, PerformanceCalculation.analysis_id == analysis_analysts.c.analysis_id
        ).filter(
            analysis_analysts.c.user_id == user.id,
            Analysis.status == 'On Watchlist'
        ).scalar()
        
        rows.append({
            'name': user.full_name or user.email.split('@')[0],
            'email': user.email,
            'total_analyses': total_analyses,
            'as_analyst': as_analyst,
            'as_opponent': as_opponent,
            'approved_analyses': approved_analyses,
            'investments': investment_count,
            'avg_return': float(avg_return_result) if avg_return_result else None,
            'win_rate': None  # Will calculate if needed
        })
    
    # Sort by total analyses descending
    rows.sort(key=lambda x: x['total_analyses'], reverse=True)
    
    return {
        'columns': [
            {'key': 'name', 'label': 'Analyst', 'align': 'left'},
            {'key': 'total_analyses', 'label': 'Total Analyses', 'align': 'center'},
            {'key': 'approved_analyses', 'label': 'Approved', 'align': 'center'},
            {'key': 'investments', 'label': 'Investments', 'align': 'center'},
            {'key': 'avg_return', 'label': 'Avg Return', 'align': 'right', 'format': 'percent'},
        ],
        'rows': rows,
        'summary': {
            'total_analysts': len(rows),
            'total_analyses': sum(r['total_analyses'] for r in rows),
            'total_approved': sum(r['approved_analyses'] for r in rows),
            'total_investments': sum(r['investments'] for r in rows),
        }
    }


def get_sector_analysis(use_cache: bool = True) -> Dict[str, Any]:
    """
    Get best sectors and sectors by risk for presentation.
    Uses file-based caching for speed.
    
    Args:
        use_cache: If True, use cached data if available
        
    Returns:
        Dict with best_sectors and risk_sectors tables
    """
    import os
    cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'instance', 'overview_cache')
    cache_file = os.path.join(cache_dir, 'sector_analysis_cache.json')
    
    # Try to get from file cache
    if use_cache and os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                cached = json.load(f)
            cached_at = datetime.fromisoformat(cached.get('cached_at', '2000-01-01'))
            age_days = (datetime.utcnow() - cached_at).days
            
            if age_days < 7:  # 7 day cache
                logger.info(f"Using file cache for sector analysis ({age_days} days old)")
                return cached['data']
        except Exception as e:
            logger.warning(f"Error reading sector analysis cache: {e}")
    
    # Calculate fresh data
    sector_data = db.session.query(
        CompanySectorCache.sector,
        func.count(distinct(Analysis.id)).label('analysis_count'),
        func.avg(PerformanceCalculation.return_pct).label('avg_return'),
        func.stddev(PerformanceCalculation.return_pct).label('stddev_return')
    ).join(
        Company, CompanySectorCache.company_id == Company.id
    ).join(
        Analysis, Analysis.company_id == Company.id
    ).join(
        PerformanceCalculation, PerformanceCalculation.analysis_id == Analysis.id
    ).filter(
        Analysis.status == 'On Watchlist'
    ).group_by(
        CompanySectorCache.sector
    ).having(
        func.count(distinct(Analysis.id)) >= 2  # At least 2 analyses
    ).all()
    
    # Best sectors by return - only positive returns
    best_sectors = []
    for row in sector_data:
        if row.avg_return is not None and float(row.avg_return) > 0:
            best_sectors.append({
                'sector': row.sector,
                'count': row.analysis_count,
                'avg_return': float(row.avg_return),
                'stddev': float(row.stddev_return) if row.stddev_return else 0
            })
    
    best_sectors.sort(key=lambda x: x['avg_return'], reverse=True)
    
    # Risk sectors (exclude 0 stddev, include negative returns too)
    risk_sectors = []
    for row in sector_data:
        if row.avg_return is not None:
            stddev_val = float(row.stddev_return) if row.stddev_return else 0
            if stddev_val > 0:
                risk_sectors.append({
                    'sector': row.sector,
                    'count': row.analysis_count,
                    'avg_return': float(row.avg_return),
                    'stddev': stddev_val
                })
    
    risk_sectors.sort(key=lambda x: x['stddev'], reverse=True)
    
    result = {
        'best_sectors': {
            'columns': [
                {'key': 'sector', 'label': 'Sector', 'align': 'left'},
                {'key': 'count', 'label': 'Analyses', 'align': 'center'},
                {'key': 'avg_return', 'label': 'Avg Return', 'align': 'right', 'format': 'percent'},
                {'key': 'stddev', 'label': 'Volatility', 'align': 'right', 'format': 'percent'},
            ],
            'rows': best_sectors[:10]  # Top 10
        },
        'risk_sectors': {
            'columns': [
                {'key': 'sector', 'label': 'Sector', 'align': 'left'},
                {'key': 'count', 'label': 'Analyses', 'align': 'center'},
                {'key': 'avg_return', 'label': 'Avg Return', 'align': 'right', 'format': 'percent'},
                {'key': 'stddev', 'label': 'Risk (σ)', 'align': 'right', 'format': 'percent'},
            ],
            'rows': risk_sectors[:10]  # Top 10 riskiest
        }
    }
    
    # Save to file cache
    try:
        os.makedirs(cache_dir, exist_ok=True)
        with open(cache_file, 'w') as f:
            json.dump({
                'cached_at': datetime.utcnow().isoformat(),
                'data': result
            }, f, default=str)
        logger.info("Cached sector analysis to file")
    except Exception as e:
        logger.error(f"Error caching sector analysis: {e}")
    
    return result


def get_growth_timeline(use_cache: bool = True) -> Dict[str, Any]:
    """
    Get timeline data for analyses growth chart.
    Uses simple file-based caching.
    
    Args:
        use_cache: If True, use cached data if available
        
    Returns:
        Dict with monthly cumulative counts
    """
    import os
    import json
    
    cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'instance', 'overview_cache')
    cache_file = os.path.join(cache_dir, 'growth_timeline_cache.json')
    
    # Try to get from file cache
    if use_cache and os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                cached = json.load(f)
            cached_at = datetime.fromisoformat(cached.get('cached_at', '2000-01-01'))
            age_days = (datetime.utcnow() - cached_at).days
            
            if age_days < 7:  # 7 day cache
                logger.info(f"Using file cache for growth timeline ({age_days} days old)")
                data = cached['data']
                # Convert string dates back to date objects
                data['dates'] = [datetime.strptime(d, '%Y-%m-%d').date() if isinstance(d, str) else d 
                               for d in data.get('dates', [])]
                return data
        except Exception as e:
            logger.warning(f"Error reading growth timeline cache: {e}")
    
    # Calculate fresh data
    analyses = Analysis.query.all()
    
    # Group by month
    monthly_data = defaultdict(lambda: {'total': 0, 'approved': 0})
    
    for analysis in analyses:
        if analysis.analysis_date:
            month_key = analysis.analysis_date.replace(day=1)
            monthly_data[month_key]['total'] += 1
            if analysis.status == 'On Watchlist':
                monthly_data[month_key]['approved'] += 1
    
    # Sort by month
    sorted_months = sorted(monthly_data.keys())
    
    dates = []
    total_cumulative = []
    approved_cumulative = []
    
    total = 0
    approved = 0
    
    for month in sorted_months:
        total += monthly_data[month]['total']
        approved += monthly_data[month]['approved']
        
        dates.append(month)
        total_cumulative.append(total)
        approved_cumulative.append(approved)
    
    result = {
        'dates': dates,
        'total_analyses': total_cumulative,
        'approved_analyses': approved_cumulative,
        'summary': {
            'total': total,
            'approved': approved
        }
    }
    
    # Save to file cache
    try:
        os.makedirs(cache_dir, exist_ok=True)
        with open(cache_file, 'w') as f:
            json.dump({
                'cached_at': datetime.utcnow().isoformat(),
                'data': {
                    'dates': [d.isoformat() if hasattr(d, 'isoformat') else str(d) for d in dates],
                    'total_analyses': total_cumulative,
                    'approved_analyses': approved_cumulative,
                    'summary': result['summary']
                }
            }, f, default=str)
        logger.info("Cached growth timeline to file")
    except Exception as e:
        logger.error(f"Error caching growth timeline: {e}")
    
    return result


def get_growth_timeline_for_chart() -> Dict[str, Any]:
    """
    Get growth timeline data formatted for Chart.js on main page.
    
    Returns:
        Dict with labels and datasets for Chart.js
    """
    data = get_growth_timeline(use_cache=True)
    
    if not data.get('dates'):
        return {'labels': [], 'datasets': []}
    
    # Format dates as strings
    labels = []
    for d in data['dates']:
        if isinstance(d, (datetime, date)):
            labels.append(d.strftime('%b %Y'))
        else:
            labels.append(str(d))
    
    return {
        'labels': labels,
        'datasets': [
            {
                'label': 'Total Analyses',
                'data': data['total_analyses'],
                'borderColor': '#2563eb',
                'backgroundColor': 'rgba(37, 99, 235, 0.1)',
                'borderWidth': 2.5,
                'tension': 0.4,
                'fill': True,
                'pointRadius': 3,
                'pointHoverRadius': 6
            },
            {
                'label': 'Approved',
                'data': data['approved_analyses'],
                'borderColor': '#10b981',
                'backgroundColor': 'rgba(16, 185, 129, 0.1)',
                'borderWidth': 2.5,
                'tension': 0.4,
                'fill': True,
                'pointRadius': 3,
                'pointHoverRadius': 6
            }
        ],
        'summary': data.get('summary', {})
    }


def create_growth_chart(
    timeline_data: Dict,
    width: int = 12,
    height: int = 6,
    dpi: int = 150
) -> bytes:
    """Create beautiful growth timeline chart."""
    fig, ax = plt.subplots(figsize=(width, height), dpi=dpi)
    
    dates = timeline_data.get('dates', [])
    
    if not dates:
        ax.text(0.5, 0.5, 'No timeline data available',
               ha='center', va='center', transform=ax.transAxes,
               fontsize=14, color=COLORS['gray'])
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight',
                   facecolor='white', edgecolor='none')
        buf.seek(0)
        plt.close(fig)
        return buf.getvalue()
    
    # Plot lines
    ax.plot(dates, timeline_data['total_analyses'], 
           color=COLORS['primary'], linewidth=2.5, label='Total Analyses', marker='o', markersize=4)
    ax.plot(dates, timeline_data['approved_analyses'], 
           color=COLORS['secondary'], linewidth=2.5, label='Approved', marker='s', markersize=4)
    
    # Styling
    ax.set_title('KI AM Analysis Growth Over Time', fontweight='bold', pad=20, fontsize=16)
    ax.set_xlabel('Date', fontweight='medium')
    ax.set_ylabel('Cumulative Count', fontweight='medium')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.xticks(rotation=45, ha='right')
    ax.legend(loc='upper left', framealpha=0.95)
    
    # Add value labels on last point
    if dates:
        ax.annotate(f"{timeline_data['total_analyses'][-1]}", 
                   xy=(dates[-1], timeline_data['total_analyses'][-1]),
                   xytext=(10, 0), textcoords='offset points',
                   fontsize=10, fontweight='bold', color=COLORS['primary'])
    
    plt.tight_layout()
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight',
               facecolor='white', edgecolor='none', dpi=dpi)
    buf.seek(0)
    plt.close(fig)
    
    return buf.getvalue()


def create_bar_chart(
    data: List[Dict],
    value_key: str,
    label_key: str,
    title: str,
    color: str = None,
    horizontal: bool = True,
    width: int = 10,
    height: int = 6,
    dpi: int = 150
) -> bytes:
    """Create bar chart for sector/data visualization."""
    fig, ax = plt.subplots(figsize=(width, height), dpi=dpi)
    
    if not data:
        ax.text(0.5, 0.5, 'No data available',
               ha='center', va='center', transform=ax.transAxes,
               fontsize=14, color=COLORS['gray'])
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight',
                   facecolor='white', edgecolor='none')
        buf.seek(0)
        plt.close(fig)
        return buf.getvalue()
    
    labels = [d[label_key] for d in data]
    values = [d[value_key] for d in data]
    
    if horizontal:
        bars = ax.barh(labels, values, color=color or COLORS['primary'], alpha=0.8)
        ax.set_xlabel('Return (%)', fontweight='medium')
        
        # Add value labels
        for bar, val in zip(bars, values):
            width = bar.get_width()
            ax.text(width, bar.get_y() + bar.get_height()/2,
                   f' {val:+.1f}%', ha='left', va='center', fontweight='bold')
    else:
        bars = ax.bar(labels, values, color=color or COLORS['primary'], alpha=0.8)
        ax.set_ylabel('Return (%)', fontweight='medium')
        plt.xticks(rotation=45, ha='right')
    
    ax.set_title(title, fontweight='bold', pad=20, fontsize=16)
    ax.axvline(x=0, color=COLORS['gray'], linestyle='-', alpha=0.3)
    
    plt.tight_layout()
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight',
               facecolor='white', edgecolor='none', dpi=dpi)
    buf.seek(0)
    plt.close(fig)
    
    return buf.getvalue()


def generate_all_presentation_exports(filter_type: str = 'board_approved', high_resolution: bool = False) -> Dict[str, Any]:
    """
    Generate all presentation exports at once.
    
    Args:
        filter_type: Type of filter for portfolio data
        high_resolution: If True, generate charts with more data points
        
    Returns:
        Dict with all charts and tables as base64-encoded images/data
    """
    logger.info(f"Generating presentation exports (high_res={high_resolution})...")
    start_time = datetime.now()
    
    # Get analysis IDs based on filter
    if filter_type == 'purchased':
        purchases = PortfolioPurchase.query.all()
        analysis_ids = [p.analysis_id for p in purchases]
    elif filter_type == 'board_approved':
        # Board approved = On Watchlist with more yes votes than no
        analyses = []
        for analysis in Analysis.query.filter_by(status='On Watchlist').all():
            votes_yes = Vote.query.filter_by(analysis_id=analysis.id, vote=True).count()
            votes_no = Vote.query.filter_by(analysis_id=analysis.id, vote=False).count()
            if votes_yes > votes_no:
                analyses.append(analysis.id)
        analysis_ids = analyses
    elif filter_type == 'all_approved':
        analyses = Analysis.query.filter_by(status='On Watchlist').all()
        analysis_ids = [a.id for a in analyses]
    else:
        analyses = Analysis.query.all()
        analysis_ids = [a.id for a in analyses]
    
    exports = {
        'generated_at': datetime.now().isoformat(),
        'filter_type': filter_type,
        'charts': {},
        'tables': {}
    }
    
    # Performance chart
    series_data = generate_portfolio_chart_series(analysis_ids)
    if series_data.get('dates'):
        chart_bytes = create_performance_chart(series_data, 
            title=f"Portfolio Performance ({filter_type.replace('_', ' ').title()})")
        exports['charts']['performance'] = base64.b64encode(chart_bytes).decode('utf-8')
    
    # Growth timeline chart
    timeline_data = get_growth_timeline()
    if timeline_data.get('dates'):
        chart_bytes = create_growth_chart(timeline_data)
        exports['charts']['growth_timeline'] = base64.b64encode(chart_bytes).decode('utf-8')
    
    # Analyst summary table
    analyst_data = get_analyst_summary_table()
    exports['tables']['analysts'] = analyst_data
    
    # Sector analysis
    sector_data = get_sector_analysis()
    exports['tables']['best_sectors'] = sector_data['best_sectors']
    exports['tables']['risk_sectors'] = sector_data['risk_sectors']
    
    # Sector charts
    if sector_data['best_sectors']['rows']:
        chart_bytes = create_bar_chart(
            sector_data['best_sectors']['rows'][:8],
            'avg_return', 'sector',
            'Top Sectors by Return',
            color=COLORS['secondary'],
            horizontal=True
        )
        exports['charts']['sector_returns'] = base64.b64encode(chart_bytes).decode('utf-8')
    
    if sector_data['risk_sectors']['rows']:
        chart_bytes = create_bar_chart(
            sector_data['risk_sectors']['rows'][:8],
            'stddev', 'sector',
            'Sectors by Risk (Volatility)',
            color=COLORS['danger'],
            horizontal=True
        )
        exports['charts']['sector_risk'] = base64.b64encode(chart_bytes).decode('utf-8')
    
    elapsed = (datetime.now() - start_time).total_seconds()
    logger.info(f"Presentation exports generated in {elapsed:.1f}s")
    
    exports['generation_time_seconds'] = elapsed
    
    return exports
