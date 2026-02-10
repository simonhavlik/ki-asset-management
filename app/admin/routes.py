from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, send_file, session, jsonify
from flask_login import login_required, current_user
from flask_wtf.csrf import validate_csrf
from werkzeug.utils import secure_filename
import os
import io
import csv
from datetime import datetime, date, timedelta
from sqlalchemy import desc, func

from ..extensions import db
from ..models import User, ActivityLog, CsvUpload, Analysis, Company, PerformanceCalculation, AnalystMapping, CompanyTickerMapping, Vote, PortfolioPurchase, Idea, IdeaComment, BenchmarkPrice, StockPrice, analysis_analysts, CompanySectorCache
from .forms import UserEditForm, CreateUserForm, CsvUploadForm, AnalystMappingForm, CompanyTickerForm
from ..utils.csv_import import CsvImporter
from ..utils.performance import PerformanceCalculator
from ..utils.email_normalization import normalize_email

admin_bp = Blueprint('admin', __name__, template_folder='../templates/admin')

# Helper decorator for admin-only routes
def admin_required(f):
    from functools import wraps
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            flash('Admin access required.', 'danger')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function


def get_portfolio_performance(purchased_only=False):
    """
    Calculate portfolio performance using cached data only (no live API calls).
    
    Args:
        purchased_only: If True, only include purchased stocks. If False, include all approved.
        
    Returns:
        Dict with portfolio performance data
    """
    # Get analyses to include
    if purchased_only:
        purchases = PortfolioPurchase.query.all()
        analysis_ids = [p.analysis_id for p in purchases]
        analyses = Analysis.query.filter(Analysis.id.in_(analysis_ids)).all() if analysis_ids else []
        # Map analysis_id to purchase_date for correct earliest date calculation
        purchase_dates = {p.analysis_id: p.purchase_date for p in purchases}
    else:
        analyses = []
        for analysis in Analysis.query.filter_by(status='On Watchlist').all():
            votes_yes = Vote.query.filter_by(analysis_id=analysis.id, vote=True).count()
            votes_no = Vote.query.filter_by(analysis_id=analysis.id, vote=False).count()
            if votes_yes > votes_no:
                analyses.append(analysis)
        purchase_dates = {}
    
    if not analyses:
        return None
    
    # Calculate portfolio returns from cached PerformanceCalculation
    total_return = 0.0
    count = 0
    earliest_date = None
    
    for analysis in analyses:
        perf = PerformanceCalculation.query.filter_by(analysis_id=analysis.id).order_by(desc(PerformanceCalculation.calculation_date)).first()
        if perf:
            total_return += float(perf.return_pct)
            count += 1
            # Use purchase_date if available, otherwise analysis_date
            entry_date = purchase_dates.get(analysis.id, analysis.analysis_date) if purchased_only else analysis.analysis_date
            if earliest_date is None or entry_date < earliest_date:
                earliest_date = entry_date
    
    if count == 0:
        return None
    
    avg_return = total_return / count
    
    # Calculate days since inception for annualized return
    days = (date.today() - earliest_date).days if earliest_date else 365
    if days > 0:
        annualized = ((1 + avg_return / 100) ** (365 / days) - 1) * 100
    else:
        annualized = avg_return
    
    # Use fallback benchmark values (approximate historical returns)
    # In production, these should be updated by a background job
    benchmark_data = _get_cached_benchmark_returns(days)
    
    return {
        'num_positions': count,
        'total_return': round(avg_return, 2),
        'annualized_return': round(annualized, 2),
        'start_date': earliest_date.isoformat() if earliest_date else None,
        'benchmark_spy': benchmark_data['SPY'],
        'benchmark_ftse': benchmark_data['VT'],
        'benchmark_eems': benchmark_data['EEMS'],
    }


def get_benchmark_price_on_date(ticker, target_date):
    """Get cached benchmark price on or before target_date."""
    price = BenchmarkPrice.query.filter(
        BenchmarkPrice.ticker == ticker,
        BenchmarkPrice.date <= target_date
    ).order_by(BenchmarkPrice.date.desc()).first()
    return float(price.close_price) if price else None


def get_cached_benchmark_return(ticker, days):
    """
    Calculate benchmark return using cached BenchmarkPrice data.
    Falls back to approximate calculation if no cached data.
    """
    try:
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        # Get start and end prices from cache
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


def _get_cached_benchmark_returns(days):
    """
    Get all benchmark returns using cached data or fallback approximations.
    """
    return {
        'SPY': round(get_cached_benchmark_return('SPY', days), 2),
        'VT': round(get_cached_benchmark_return('VT', days), 2),
        'EEMS': round(get_cached_benchmark_return('EEMS', days), 2)
    }


def get_portfolio_series(purchased_only=False, years=1):
    """
    Get portfolio time series data for charting using cached data only.
    
    Calculates the actual portfolio performance as an equal-weighted portfolio
    where each stock contributes from its entry date (analysis_date or purchase_date).
    
    The portfolio line shows:
    - From first stock entry: That stock's performance
    - From second stock entry: Average of both stocks' performances
    - From third stock entry: Average of all three, etc.
    
    Args:
        purchased_only: If True, only include purchased stocks
        years: Number of years to look back (1 for 1-year chart, 0 or None for inception)
        
    Returns:
        Dict with dates and series for portfolio and benchmarks
    """
    import pandas as pd
    from datetime import date, timedelta
    from ..models import StockPrice
    
    # Get analyses with their entry dates
    if purchased_only:
        purchases = PortfolioPurchase.query.all()
        analysis_ids = [p.analysis_id for p in purchases]
        analyses = Analysis.query.filter(Analysis.id.in_(analysis_ids)).all() if analysis_ids else []
        # Map analysis_id to purchase_date
        purchase_dates = {p.analysis_id: p.purchase_date for p in purchases}
    else:
        analyses = []
        for analysis in Analysis.query.filter_by(status='On Watchlist').all():
            votes_yes = Vote.query.filter_by(analysis_id=analysis.id, vote=True).count()
            votes_no = Vote.query.filter_by(analysis_id=analysis.id, vote=False).count()
            if votes_yes > votes_no:
                analyses.append(analysis)
        purchase_dates = {}
    
    if not analyses:
        return None
    
    # Get entry date for each analysis (purchase_date if available, else analysis_date)
    analysis_entries = []
    for analysis in analyses:
        entry_date = purchase_dates.get(analysis.id, analysis.analysis_date)
        analysis_entries.append({
            'analysis': analysis,
            'entry_date': entry_date
        })
    
    # Sort by entry date
    analysis_entries.sort(key=lambda x: x['entry_date'])
    
    # Determine date range
    # When years is specified, use fixed date range from today (not based on earliest entry)
    # This ensures benchmark comparisons are consistent across views
    end_date = date.today()
    if years:
        start_date = end_date - timedelta(days=365*years)
        # Filter entries to only those within the date range
        analysis_entries = [e for e in analysis_entries if e['entry_date'] >= start_date]
        if not analysis_entries:
            return None
    else:
        # Inception - from earliest entry
        start_date = analysis_entries[0]['entry_date']
    
    # Create monthly date points
    dates = pd.date_range(start=start_date, end=end_date, freq='MS')
    if len(dates) < 3:
        dates = pd.date_range(start=start_date, end=end_date, periods=6)
    
    portfolio_series = []
    date_labels = []
    
    for d in dates:
        date_str = d.strftime('%Y-%m-%d')
        date_labels.append(date_str)
        current_date = d.date()
        
        # Get all stocks that have entered the portfolio by this date
        active_entries = [e for e in analysis_entries if e['entry_date'] <= current_date]
        
        if not active_entries:
            portfolio_series.append(0)
            continue
        
        # Calculate equal-weighted average return of all active stocks
        total_return = 0
        count = 0
        
        for entry in active_entries:
            analysis = entry['analysis']
            entry_date = entry['entry_date']
            company = Company.query.get(analysis.company_id)
            
            if not company or not company.ticker_symbol:
                continue
            
            # Get price at entry date
            entry_price = StockPrice.query.filter(
                StockPrice.company_id == company.id,
                StockPrice.date <= entry_date
            ).order_by(StockPrice.date.desc()).first()
            
            # Get price at current chart date
            current_price = StockPrice.query.filter(
                StockPrice.company_id == company.id,
                StockPrice.date <= current_date
            ).order_by(StockPrice.date.desc()).first()
            
            if entry_price and current_price and float(entry_price.close_price) > 0:
                ret = ((float(current_price.close_price) - float(entry_price.close_price)) / 
                       float(entry_price.close_price)) * 100
                total_return += ret
                count += 1
        
        if count > 0:
            avg_return = total_return / count
            portfolio_series.append(round(avg_return, 2))
        else:
            portfolio_series.append(0)
    
    # Generate benchmark series from cached data
    spy_series = _get_benchmark_series_from_cache(dates, 'SPY')
    vt_series = _get_benchmark_series_from_cache(dates, 'VT')
    eems_series = _get_benchmark_series_from_cache(dates, 'EEMS')
    
    return {
        'dates': date_labels,
        'portfolio_series': portfolio_series,
        'spy_series': spy_series,
        'vt_series': vt_series,
        'eems_series': eems_series,
    }


def _get_benchmark_series_from_cache(dates, ticker):
    """
    Get benchmark return series from cached BenchmarkPrice data.
    Falls back to synthetic data if cache is empty.
    
    All benchmarks are normalized to start at 0% on the first chart date.
    Uses simple linear extrapolation for missing data to avoid compounding errors.
    """
    series = []
    
    if len(dates) == 0:
        return series
    
    # Normalize dates to date objects
    normalized_dates = []
    for d in dates:
        if hasattr(d, 'date') and callable(getattr(d, 'date')):
            normalized_dates.append(d.date())
        else:
            normalized_dates.append(d)
    
    first_date = normalized_dates[0]
    last_date = normalized_dates[-1]
    
    # Get the base price for the first chart date (or closest available before it)
    base_price = get_benchmark_price_on_date(ticker, first_date)
    base_price_date = first_date
    
    # If no price on first date, try to find the earliest available price after it
    if base_price is None:
        bp = BenchmarkPrice.query.filter(
            BenchmarkPrice.ticker == ticker,
            BenchmarkPrice.date >= first_date
        ).order_by(BenchmarkPrice.date.asc()).first()
        if bp:
            base_price = float(bp.close_price)
            base_price_date = bp.date
    
    # If still no base price, use approximate synthetic data
    if base_price is None:
        approx_prices = {'SPY': 400.0, 'VT': 100.0, 'EEMS': 50.0}
        base_price = approx_prices.get(ticker, 100.0)
        
        # Generate simple synthetic series based on annual return (no compounding)
        annual = {'SPY': 10.0, 'VT': 9.0, 'EEMS': 7.0}.get(ticker, 8.0)
        for i, current_date in enumerate(normalized_dates):
            days_from_start = (current_date - first_date).days
            ret = (annual / 365.0) * days_from_start
            series.append(round(ret, 2))
        return series
    
    # Get all available prices for this ticker up to the last date
    all_prices = {}
    for bp in BenchmarkPrice.query.filter(
        BenchmarkPrice.ticker == ticker,
        BenchmarkPrice.date <= last_date
    ).all():
        all_prices[bp.date] = float(bp.close_price)
    
    if not all_prices:
        # No prices at all - return flat line
        return [0.0] * len(normalized_dates)
    
    # Build series with proper lookup for missing dates
    for i, current_date in enumerate(normalized_dates):
        if current_date in all_prices:
            # Use actual price
            price = all_prices[current_date]
            ret = ((price - base_price) / base_price) * 100
            series.append(round(ret, 2))
        else:
            # Find the most recent price before this date
            most_recent_price = None
            for d, p in sorted(all_prices.items()):
                if d <= current_date:
                    most_recent_price = p
                else:
                    break
            
            if most_recent_price is not None:
                # Use the most recent known price
                ret = ((most_recent_price - base_price) / base_price) * 100
                series.append(round(ret, 2))
            else:
                # No data yet - use base price (0% return)
                series.append(0.0)
    
    return series


@admin_bp.route('/')
@admin_required
def dashboard():
    """Admin dashboard - redirects to analyst dashboard which includes admin data."""
    # Redirect to the analyst dashboard which now includes admin functionality
    return redirect(url_for('analyst.dashboard'))


@admin_bp.route('/users')
@admin_required
def users():
    """List all users."""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    users_query = User.query.order_by(User.created_at.desc())
    pagination = users_query.paginate(page=page, per_page=per_page)
    
    return render_template('admin/users.html', pagination=pagination)


@admin_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_user(user_id):
    """Edit a user."""
    user = User.query.get_or_404(user_id)
    form = UserEditForm(obj=user)
    
    if form.validate_on_submit():
        user.email = form.email.data
        user.full_name = form.full_name.data
        user.is_admin = form.is_admin.data
        user.is_active = form.is_active.data
        
        if form.password.data:
            user.set_password(form.password.data)
        
        db.session.commit()
        flash(f'User {user.email} updated.', 'success')
        return redirect(url_for('admin.users'))
    
    return render_template('admin/edit_user.html', form=form, user=user)


@admin_bp.route('/users/create', methods=['GET', 'POST'])
@admin_required
def create_user():
    """Create a new user."""
    form = CreateUserForm()
    
    if form.validate_on_submit():
        user = User(
            email=form.email.data,
            full_name=form.full_name.data,
            is_admin=form.is_admin.data
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        
        flash(f'User {user.email} created.', 'success')
        return redirect(url_for('admin.users'))
    
    return render_template('admin/create_user.html', form=form)


@admin_bp.route('/users/<int:user_id>/toggle', methods=['POST'])
@admin_required
def toggle_user(user_id):
    """Toggle user active status."""
    user = User.query.get_or_404(user_id)
    user.is_active = not user.is_active
    db.session.commit()
    flash(f'User {user.email} {"activated" if user.is_active else "deactivated"}.', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/upload-csv', methods=['GET', 'POST'])
@admin_required
def upload_csv():
    """Upload and process a CSV file. Invalidates all caches on successful import."""
    from ..utils.neon_cache import invalidate_all_public_cache
    
    form = CsvUploadForm()
    
    # Get last import summary from session
    last_import = session.pop('last_import_summary', None)
    
    if form.validate_on_submit():
        filename = secure_filename(form.csv_file.data.filename)
        content = form.csv_file.data.read().decode('utf-8')
        try:
            importer = CsvImporter(
                csv_content=content,
                filename=filename,
                uploaded_by=current_user.id
            )
            stats = importer.process()
            
            # Store summary in session for display
            session['last_import_summary'] = {
                'filename': filename,
                'created': stats.get('created', 0),
                'updated': stats.get('updated', 0),
                'skipped': stats.get('skipped', 0),
                'errors': len(stats.get('errors', [])),
                'ticker_resolutions': stats.get('ticker_resolutions', {})
            }
            
            if stats['success']:
                flash(f'CSV processed: {stats["created"]} created, {stats["updated"]} updated, {stats["skipped"]} skipped.', 'success')
                if stats['errors']:
                    flash(f'Errors: {len(stats["errors"])}. Check logs for details.', 'warning')
                
                # Invalidate all caches after successful import
                try:
                    invalidate_all_public_cache()
                    flash('Caches invalidated. Data will refresh on next page load.', 'info')
                except Exception as e:
                    current_app.logger.warning(f"Failed to invalidate caches: {e}")
            else:
                flash(f'Import failed: {stats.get("error", "Unknown error")}', 'danger')
                if stats.get('errors'):
                    for error in stats['errors'][:5]:  # Show first 5 errors
                        flash(error, 'warning')
            
            return redirect(url_for('admin.upload_csv'))
        except Exception as e:
            flash(f'Import failed: {str(e)}', 'danger')
            current_app.logger.exception('CSV import error')
    
    # List previous uploads
    uploads = CsvUpload.query.order_by(desc(CsvUpload.uploaded_at)).limit(20).all()
    return render_template('admin/upload_csv.html', form=form, uploads=uploads, last_import=last_import)


@admin_bp.route('/performance')
@login_required
def performance():
    """View performance of all analysts."""
    filter_param = request.args.get('filter', 'approved_only')
    annualized = request.args.get('annualized', 'false').lower() == 'true'
    # Backward compatibility: if 'status' param is provided, map to filter
    status_param = request.args.get('status')
    if status_param and filter_param == 'approved_only':
        # Map old status to appropriate filter
        if status_param == 'On Watchlist':
            filter_param = 'approved_only'
        elif status_param == 'Neutral':
            filter_param = 'neutral_approved'
        else:
            filter_param = 'all_stock'  # fallback
    calculator = PerformanceCalculator()
    analyst_performance = calculator.get_all_analysts_performance(status_filter=filter_param, annualized=annualized)
    # Aggregate overall stats
    total_analyses = sum(p['num_analyses'] for p in analyst_performance)
    avg_returns = [p['avg_return'] for p in analyst_performance if p['avg_return'] is not None]
    overall_avg = sum(avg_returns) / len(avg_returns) if avg_returns else None
    return render_template('admin/performance.html', 
                         analyst_performance=analyst_performance,
                         total_analyses=total_analyses,
                         avg_return=overall_avg,
                         current_filter=filter_param,
                         annualized=annualized)


@admin_bp.route('/recalculate-performance', methods=['POST'])
@admin_required
def recalculate_performance():
    """Trigger recalculation of all performance metrics with progress."""
    calculator = PerformanceCalculator()
    stats = calculator.recalculate_all()
    flash(f'Performance recalculated: {stats["calculated"]} analyses processed, {stats["skipped_no_ticker"]} missing ticker, {stats["skipped_no_price"]} missing price, {stats["skipped_other_event"]} other events.', 'success')
    return redirect(url_for('admin.performance'))


@admin_bp.route('/analyst-mappings')
@admin_required
def analyst_mappings():
    """Manage analyst name to user mappings."""
    form = AnalystMappingForm()
    
    # Get all mappings with user info
    mappings = db.session.query(AnalystMapping, User).join(User).order_by(AnalystMapping.analyst_name).all()
    
    # Get unmapped analyst names from analyses using safe ORM queries
    # instead of raw SQL to prevent SQL injection
    from sqlalchemy import distinct
    
    # Get all analyst names from analyses table
    analyst_names = db.session.query(distinct(analysis_analysts.c.user_id)).all()
    
    # Get mapped analyst names
    mapped_names = db.session.query(AnalystMapping.analyst_name).all()
    mapped_names_set = {m[0] for m in mapped_names}
    
    # Get unmapped analyst names by comparing with User table
    # Find users who are analysts but not in analyst_mappings
    unmapped_users = db.session.query(User).outerjoin(
        AnalystMapping, User.id == AnalystMapping.user_id
    ).filter(AnalystMapping.id.is_(None)).filter(
        User.full_name.isnot(None)
    ).order_by(User.full_name).all()
    
    # Create list of unmapped analyst names
    unmapped = []
    for user in unmapped_users:
        if user.full_name and user.full_name not in mapped_names_set:
            unmapped.append((user.full_name,))
    
    return render_template('admin/analyst_mappings.html', 
                         mappings=mappings, 
                         unmapped=unmapped,
                         form=form)


@admin_bp.route('/analyst-mappings/create', methods=['POST'])
@admin_required
def create_analyst_mapping():
    """Create a new analyst mapping."""
    form = AnalystMappingForm()
    if form.validate_on_submit():
        # Check if user exists
        user = User.query.filter_by(email=form.email.data).first()
        if not user:
            # Create placeholder user
            normalized = normalize_email(form.analyst_name.data)
            email = f"{normalized}@klubinvestoru.com"
            user = User(
                email=email,
                full_name=form.analyst_name.data,
                is_active=False
            )
            db.session.add(user)
            db.session.flush()
        
        mapping = AnalystMapping(
            analyst_name=form.analyst_name.data,
            user_id=user.id
        )
        db.session.add(mapping)
        db.session.commit()
        
        flash(f'Mapping created for {form.analyst_name.data}.', 'success')
    else:
        flash('Failed to create mapping.', 'danger')
    
    return redirect(url_for('admin.analyst_mappings'))


@admin_bp.route('/analyst-mappings/<int:mapping_id>/delete', methods=['POST'])
@admin_required
def delete_analyst_mapping(mapping_id):
    """Delete an analyst mapping."""
    mapping = AnalystMapping.query.get_or_404(mapping_id)
    db.session.delete(mapping)
    db.session.commit()
    flash('Mapping deleted.', 'success')
    return redirect(url_for('admin.analyst_mappings'))


@admin_bp.route('/company-tickers')
@admin_required
def company_tickers():
    """Manage company ticker mappings."""
    form = CompanyTickerForm()
    
    # Companies without tickers, excluding those marked as Other events
    missing = Company.query.filter(
        Company.ticker_symbol.is_(None)
    ).outerjoin(
        CompanyTickerMapping, Company.name == CompanyTickerMapping.company_name
    ).filter(
        (CompanyTickerMapping.is_other_event.is_(None)) | (CompanyTickerMapping.is_other_event == False)
    ).order_by(Company.name).all()
    
    # Existing mappings (not Other events)
    mappings = db.session.query(CompanyTickerMapping, Company).\
        join(Company, CompanyTickerMapping.company_name == Company.name).\
        filter(CompanyTickerMapping.is_other_event == False).\
        order_by(CompanyTickerMapping.company_name).all()
    
    # Other events
    other_events = db.session.query(CompanyTickerMapping, Company).\
        join(Company, CompanyTickerMapping.company_name == Company.name).\
        filter(CompanyTickerMapping.is_other_event == True).\
        order_by(CompanyTickerMapping.company_name).all()
    
    return render_template('admin/company_tickers.html',
                         missing=missing,
                         mappings=mappings,
                         other_events=other_events,
                         form=form)


@admin_bp.route('/company-tickers/company/<int:company_id>/set', methods=['POST'])
@admin_required
def set_company_ticker(company_id):
    """Set or update a company's ticker symbol."""
    company = Company.query.get_or_404(company_id)
    ticker = request.form.get('ticker_symbol', '').strip().upper()
    
    if not ticker:
        flash('Ticker symbol is required.', 'danger')
        return redirect(url_for('admin.company_tickers'))
    
    # Validate ticker has price data
    from ..utils.yahooquery_helper import fetch_prices
    from datetime import date, timedelta
    
    try:
        end_date = date.today()
        start_date = end_date - timedelta(days=7)
        df = fetch_prices(ticker, start_date, end_date)
        if df.empty:
            flash(f'Warning: No price data available for ticker {ticker}. The mapping was created but calculations may fail.', 'warning')
        else:
            flash(f'Ticker {ticker} validated with price data.', 'success')
    except Exception as e:
        flash(f'Warning: Could not validate ticker {ticker}: {e}. The mapping was created but may not work.', 'warning')
    
    # Update company
    company.ticker_symbol = ticker
    
    # Update or create mapping
    mapping = CompanyTickerMapping.query.filter_by(company_name=company.name).first()
    if mapping:
        mapping.ticker_symbol = ticker
        mapping.is_other_event = False
        mapping.source = 'manual'
    else:
        mapping = CompanyTickerMapping(
            company_name=company.name,
            ticker_symbol=ticker,
            source='manual'
        )
        db.session.add(mapping)
    
    db.session.commit()
    return redirect(url_for('admin.company_tickers'))


@admin_bp.route('/company-tickers/deepseek', methods=['POST'])
@admin_required
def deepseek_missing_tickers():
    """Attempt to extract tickers for all missing companies with price validation."""
    from ..utils.ticker_resolver import resolve_ticker, set_cached_ticker
    
    missing_companies = Company.query.filter(Company.ticker_symbol.is_(None)).all()
    
    stats = {
        'total': len(missing_companies),
        'resolved': 0,
        'other': 0,
        'failed': 0,
        'errors': []
    }
    
    for company in missing_companies:
        try:
            ticker, is_other, source = resolve_ticker(company.name)
            
            if is_other:
                # Mark as Other event
                company.ticker_symbol = None
                stats['other'] += 1
            elif ticker:
                # Valid ticker with price data found
                company.ticker_symbol = ticker
                stats['resolved'] += 1
            else:
                # Could not resolve
                stats['failed'] += 1
                
        except Exception as e:
            stats['errors'].append(f"{company.name}: {str(e)}")
            stats['failed'] += 1
            current_app.logger.exception(f"Error resolving ticker for {company.name}")
    
    db.session.commit()
    
    flash(f'Ticker resolution completed: {stats["resolved"]} resolved, {stats["other"]} marked as Other, {stats["failed"]} failed.', 'success')
    if stats['errors']:
        flash(f'Errors: {len(stats["errors"])}', 'warning')
    
    return redirect(url_for('admin.company_tickers'))


@admin_bp.route('/company-tickers/mapping/<int:mapping_id>/toggle-other', methods=['POST'])
@admin_required
def toggle_other_mapping(mapping_id):
    """Toggle is_other_event flag for a mapping."""
    mapping = CompanyTickerMapping.query.get_or_404(mapping_id)
    mapping.is_other_event = not mapping.is_other_event
    db.session.commit()
    if mapping.is_other_event:
        flash(f'{mapping.company_name} moved to Other Events.', 'success')
    else:
        flash(f'{mapping.company_name} moved back to ticker mappings.', 'success')
    return redirect(url_for('admin.company_tickers'))


@admin_bp.route('/company-tickers/company/<int:company_id>/mark-other', methods=['POST'])
@admin_required
def mark_company_other(company_id):
    """Create a mapping marked as other event for a company (missing ticker)."""
    company = Company.query.get_or_404(company_id)
    # Check if mapping already exists
    mapping = CompanyTickerMapping.query.filter_by(company_name=company.name).first()
    if mapping:
        mapping.is_other_event = True
    else:
        mapping = CompanyTickerMapping(
            company_name=company.name,
            ticker_symbol=None,
            source='manual',
            is_other_event=True
        )
        db.session.add(mapping)
    db.session.commit()
    flash(f'{company.name} moved to Other Events.', 'success')
    return redirect(url_for('admin.company_tickers'))


@admin_bp.route('/export-csv')
@login_required
def export_csv():
    """Export analyst performance as CSV."""
    calculator = PerformanceCalculator()
    data = calculator.get_all_analysts_performance()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Analyst Name', 'Analyses Count', 'Avg Return %', 'Median Return %', 'Win Rate %', 'Best Return %', 'Worst Return %'])
    for row in data:
        writer.writerow([
            row['analyst_name'],
            row['num_analyses'],
            row['avg_return'],
            row['median_return'],
            row['win_rate'],
            row['best_return'],
            row['worst_return']
        ])
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode()),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'analyst_performance_{datetime.now().strftime("%Y%m%d")}.csv'
    )


@admin_bp.route('/export-board-csv')
@admin_required
def export_board_csv():
    """Export board voting data as CSV."""
    analyses = Analysis.query.filter_by(status='On Watchlist').order_by(Analysis.analysis_date.desc()).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Company', 'Ticker', 'Analysis Date', 'Analysts', 'Votes Yes', 'Votes No', 'Status'])
    
    for analysis in analyses:
        votes_yes = Vote.query.filter_by(analysis_id=analysis.id, vote=True).count()
        votes_no = Vote.query.filter_by(analysis_id=analysis.id, vote=False).count()
        status = 'Purchased' if votes_yes > votes_no else 'Rejected' if votes_no > votes_yes else 'Tie'
        
        writer.writerow([
            analysis.company.name,
            analysis.company.ticker_symbol or '',
            analysis.analysis_date.strftime('%Y-%m-%d'),
            ', '.join([a.full_name or a.email for a in analysis.analysts]),
            votes_yes,
            votes_no,
            status
        ])
    
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode()),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'board_votes_{datetime.now().strftime("%Y%m%d")}.csv'
    )


@admin_bp.route('/activity')
@admin_required
def activity():
    """View activity logs."""
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    logs = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).paginate(
        page=page, per_page=per_page
    )
    
    return render_template('admin/activity.html', logs=logs)


@admin_bp.route('/debug-performance')
@admin_required
def debug_performance():
    """Debug page for performance calculations.
    
    Excludes companies marked as 'Other' events since those should not be
    included in performance calculations.
    """
    # Get all stock analyses (exclude 'Other' events)
    analyses = Analysis.query.filter(Analysis.status.in_(['On Watchlist', 'Neutral', 'Refused'])).all()
    
    # Categorize issues
    missing_ticker = []
    missing_price = []
    missing_perf = []
    
    for analysis in analyses:
        company = Company.query.get(analysis.company_id)
        if not company:
            continue
        
        # Check if this company is marked as Other event - skip entirely if so
        mapping = CompanyTickerMapping.query.filter_by(company_name=company.name).first()
        if mapping and mapping.is_other_event:
            continue  # Skip companies marked as Other events
            
        # Check for missing ticker
        if not company.ticker_symbol:
            missing_ticker.append((analysis, company))
            continue
        
        # Check for missing price data
        price_at_analysis = StockPrice.query.filter(
            StockPrice.company_id == company.id,
            StockPrice.date <= analysis.analysis_date
        ).order_by(StockPrice.date.desc()).first()
        
        current_price = StockPrice.query.filter(
            StockPrice.company_id == company.id
        ).order_by(StockPrice.date.desc()).first()
        
        if not price_at_analysis:
            missing_price.append((analysis, company, 'missing_price_at_date'))
        elif not current_price:
            missing_price.append((analysis, company, 'missing_current_price'))
        
        # Check for missing performance calculation
        perf = PerformanceCalculation.query.filter_by(analysis_id=analysis.id).first()
        if not perf:
            missing_perf.append((analysis, company, 'no_calculation'))
    
    # Build stats
    stats = {
        'total_analyses': len(analyses),
        'missing_ticker_count': len(missing_ticker),
        'missing_price_count': len(missing_price),
        'missing_perf_count': len(missing_perf)
    }
    
    return render_template('admin/debug_performance.html',
                         stats=stats,
                         missing_ticker=missing_ticker,
                         missing_price=missing_price,
                         missing_perf=missing_perf)


@admin_bp.route('/board')
@login_required
@admin_required
def board():
    """Board voting interface for portfolio decisions."""
    # Get analyses ready for Board vote (On Watchlist status)
    # Exclude analyses for companies marked as Other events
    analyses = Analysis.query.filter_by(status='On Watchlist').\
        join(Company, Analysis.company_id == Company.id).\
        outerjoin(CompanyTickerMapping, Company.name == CompanyTickerMapping.company_name).\
        filter(
            (CompanyTickerMapping.is_other_event.is_(None)) | (CompanyTickerMapping.is_other_event == False)
        ).\
        order_by(Analysis.analysis_date.desc()).all()
    
    # Get current user's votes (as a set of analysis IDs that user has voted on)
    user_votes = {v.analysis_id for v in Vote.query.filter_by(user_id=current_user.id).all()}
    
    # Get portfolio purchases
    purchases = PortfolioPurchase.query.order_by(PortfolioPurchase.purchase_date.desc()).all()
    purchased_ids = {p.analysis_id for p in purchases}
    
    # Use cached portfolio calculations for better performance
    from ..utils.neon_cache import (
        get_cached_board_portfolio_performance,
        get_cached_board_portfolio_series,
        get_last_recalculation_time
    )
    
    # Get portfolio performance (cached)
    portfolio_performance = get_cached_board_portfolio_performance(purchased_only=False)
    
    # Get portfolio time series data (cached)
    portfolio_series_all = get_cached_board_portfolio_series(purchased_only=False, years=None)
    portfolio_series_1y = get_cached_board_portfolio_series(purchased_only=False, years=1)
    
    # Get purchased portfolio data (cached)
    purchased_performance = get_cached_board_portfolio_performance(purchased_only=True)
    purchased_series_all = get_cached_board_portfolio_series(purchased_only=True, years=None)
    purchased_series_1y = get_cached_board_portfolio_series(purchased_only=True, years=1)
    
    # Get last recalculation time
    last_recalc = get_last_recalculation_time()
    
    return render_template('admin/board.html',
                         analyses=analyses,
                         user_votes=user_votes,
                         purchases=purchases,
                         purchased_ids=purchased_ids,
                         portfolio_performance=portfolio_performance,
                         portfolio_series_all=portfolio_series_all,
                         portfolio_series_1y=portfolio_series_1y,
                         purchased_performance=purchased_performance,
                         purchased_series_all=purchased_series_all,
                         purchased_series_1y=purchased_series_1y,
                         last_recalc=last_recalc)


@admin_bp.route('/board/vote/<int:analysis_id>', methods=['POST'])
@admin_required
def board_vote(analysis_id):
    """Cast a vote on an analysis."""
    vote_value = request.form.get('vote') == 'yes'
    
    # Check if vote exists
    vote = Vote.query.filter_by(analysis_id=analysis_id, user_id=current_user.id).first()
    if vote:
        vote.vote = vote_value
    else:
        vote = Vote(
            analysis_id=analysis_id,
            user_id=current_user.id,
            vote=vote_value
        )
        db.session.add(vote)
    
    db.session.commit()
    flash('Vote recorded.', 'success')
    return redirect(url_for('admin.board'))


@admin_bp.route('/board/cast-vote/<int:analysis_id>', methods=['POST'])
@admin_required
def cast_vote(analysis_id):
    """Cast a vote (alternative endpoint)."""
    return board_vote(analysis_id)


@admin_bp.route('/board/purchase/<int:analysis_id>', methods=['POST'])
@admin_required
def board_purchase(analysis_id):
    """Mark an analysis as purchased for the portfolio."""
    # Get purchase date from form or use current date
    purchase_date_str = request.form.get('purchase_date')
    if purchase_date_str:
        purchase_date = datetime.strptime(purchase_date_str, '%Y-%m-%d').date()
    else:
        purchase_date = datetime.now().date()
    
    # Check if purchase already exists
    existing = PortfolioPurchase.query.filter_by(analysis_id=analysis_id).first()
    if existing:
        existing.purchase_date = purchase_date
        existing.added_by = current_user.id
    else:
        purchase = PortfolioPurchase(
            analysis_id=analysis_id,
            purchase_date=purchase_date,
            added_by=current_user.id
        )
        db.session.add(purchase)
    
    # Also update the analysis.purchase_date field for convenience
    analysis = Analysis.query.get_or_404(analysis_id)
    analysis.purchase_date = purchase_date
    analysis.is_in_portfolio = True
    
    db.session.commit()
    flash('Added to portfolio.', 'success')
    return redirect(url_for('admin.board'))


@admin_bp.route('/board/update-purchase-date/<int:analysis_id>', methods=['POST'])
@admin_required
def update_purchase_date(analysis_id):
    """Update purchase date for an analysis."""
    purchase_date = request.form.get('purchase_date')
    if purchase_date:
        purchase = PortfolioPurchase.query.filter_by(analysis_id=analysis_id).first()
        if purchase:
            purchase.purchase_date = datetime.strptime(purchase_date, '%Y-%m-%d').date()
            db.session.commit()
            flash('Purchase date updated.', 'success')
    return redirect(url_for('admin.board'))


@admin_bp.route('/board/remove/<int:analysis_id>', methods=['POST'])
@admin_required
def remove_from_board(analysis_id):
    """Remove an analysis from the board."""
    # Delete all votes for this analysis
    Vote.query.filter_by(analysis_id=analysis_id).delete()
    db.session.commit()
    flash('Analysis removed from board.', 'success')
    return redirect(url_for('admin.board'))


@admin_bp.route('/board/remove-purchase/<int:analysis_id>', methods=['POST'])
@admin_required
def remove_purchase(analysis_id):
    """Remove purchase status from an analysis."""
    # Delete the portfolio purchase
    purchase = PortfolioPurchase.query.filter_by(analysis_id=analysis_id).first()
    if purchase:
        db.session.delete(purchase)
    
    # Update analysis
    analysis = Analysis.query.get_or_404(analysis_id)
    analysis.is_in_portfolio = False
    analysis.purchase_date = None
    
    db.session.commit()
    flash('Purchase removed.', 'success')
    return redirect(url_for('admin.board'))


@admin_bp.route('/board/remove-vote/<int:analysis_id>', methods=['POST'])
@admin_required
def remove_vote(analysis_id):
    """Remove current user's vote from an analysis."""
    vote = Vote.query.filter_by(analysis_id=analysis_id, user_id=current_user.id).first()
    if vote:
        db.session.delete(vote)
        db.session.commit()
        flash('Vote removed.', 'success')
    return redirect(url_for('admin.board'))


@admin_bp.route('/board/calculate-performance', methods=['POST'])
@admin_required
def calculate_portfolio_performance():
    """Calculate and update portfolio performance with full cache refresh."""
    from ..utils.neon_cache import admin_manual_recalculation
    
    try:
        # Run full recalculation with cache clearing and warming
        results = admin_manual_recalculation()
        
        if results['errors']:
            flash(f'Recalculation completed with {len(results["errors"])} errors. Check logs for details.', 'warning')
        else:
            flash(f'Performance recalculated: {results["performance_calculated"]} analyses. '
                  f'Caches refreshed: {", ".join(results["caches_warmed"])}. '
                  f'Time: {results["elapsed_seconds"]:.1f}s', 'success')
    except Exception as e:
        flash(f'Recalculation failed: {str(e)}', 'danger')
    
    return redirect(url_for('admin.board'))


@admin_bp.route('/admin/refresh-all-caches', methods=['POST'])
@admin_required
def refresh_all_caches():
    """Refresh all caches without recalculating performance."""
    from ..utils.neon_cache import invalidate_all_public_cache, invalidate_board_cache, warm_public_caches
    from ..utils.overview_cache import invalidate_cache as invalidate_overview_cache
    
    try:
        # Clear all caches including overview
        invalidate_all_public_cache()
        invalidate_board_cache()
        invalidate_overview_cache()  # Clear all overview caches
        
        # Warm caches
        warmed = warm_public_caches()
        
        flash(f'All caches cleared (including overview). Caches warmed: {", ".join(warmed)}. Go to Overview and refresh each view.', 'success')
    except Exception as e:
        flash(f'Cache refresh failed: {str(e)}', 'danger')
    
    return redirect(request.referrer or url_for('admin.dashboard'))


@admin_bp.route('/analyst/<int:analyst_id>')
@login_required
def analyst_details(analyst_id):
    """View detailed performance for a specific analyst."""
    from ..utils.performance import PerformanceCalculator
    
    # Allow users to view their own details, or admins to view any
    if not current_user.is_admin and current_user.id != analyst_id:
        flash('You can only view your own performance details.', 'warning')
        return redirect(url_for('analyst.dashboard'))
    
    user = User.query.get_or_404(analyst_id)
    
    calculator = PerformanceCalculator()
    
    # Get filter params
    current_filter = request.args.get('filter', 'approved_only')
    annualized = request.args.get('annualized', 'false').lower() == 'true'
    
    # Get analyst performance data
    perf_data = calculator.get_analyst_performance(analyst_id, status_filter=current_filter, annualized=annualized)
    
    # Get analyses with performance details
    analyses_with_perf = []
    analyses = db.session.query(Analysis).join(
        analysis_analysts, Analysis.id == analysis_analysts.c.analysis_id
    ).filter(
        analysis_analysts.c.user_id == analyst_id,
        analysis_analysts.c.role == 'analyst'
    ).all()
    
    for analysis in analyses:
        company = Company.query.get(analysis.company_id)
        perf = PerformanceCalculation.query.filter_by(analysis_id=analysis.id).order_by(
            desc(PerformanceCalculation.calculation_date)
        ).first()
        if perf:
            analyses_with_perf.append((analysis, perf, company))
    
    # Build analyst dict matching template expectations
    analyst_dict = {
        'analyst_id': user.id,
        'analyst_name': user.full_name or user.email.split('@')[0],
        'num_analyses': perf_data.get('num_analyses', 0),
        'avg_return': perf_data.get('avg_return'),
        'median_return': perf_data.get('median_return'),
        'win_rate': perf_data.get('win_rate'),
        'best_return': perf_data.get('best_return'),
        'worst_return': perf_data.get('worst_return')
    }
    
    # Build time series data for charts (similar to Board page)
    series_all = _build_analyst_series(analyses_with_perf, years=None)  # Inception
    series_1y = _build_analyst_series(analyses_with_perf, years=1)     # 1 year
    
    return render_template('admin/analyst_details.html',
                         analyst=analyst_dict,
                         analyses=analyses_with_perf,
                         series_all=series_all,
                         series_1y=series_1y,
                         current_filter=current_filter,
                         annualized=annualized)


def _build_analyst_series(analyses_with_perf, years=None):
    """
    Build time series data for analyst performance charts.
    
    Calculates the actual portfolio performance as an equal-weighted portfolio
    where each stock contributes from its analysis date.
    
    The line shows:
    - From first stock: That stock's performance
    - From second stock: Average of both stocks' performances
    - From third stock: Average of all three, etc.
    """
    import pandas as pd
    from datetime import date, timedelta
    
    if not analyses_with_perf:
        return None
    
    # Sort by analysis date
    sorted_analyses = sorted(analyses_with_perf, key=lambda x: x[0].analysis_date)
    
    # Determine date range
    # When years is specified, use fixed date range from today (not based on earliest analysis)
    # This ensures benchmark comparisons are consistent across views
    end_date = date.today()
    if years:
        start_date = end_date - timedelta(days=365*years)
        # Filter analyses to only those within the date range
        sorted_analyses = [(a, p, c) for a, p, c in sorted_analyses if a.analysis_date >= start_date]
        if not sorted_analyses:
            return None
    else:
        # Inception - from earliest analysis
        start_date = sorted_analyses[0][0].analysis_date
    
    # Create monthly date points
    dates = pd.date_range(start=start_date, end=end_date, freq='MS')
    if len(dates) < 3:
        dates = pd.date_range(start=start_date, end=end_date, periods=6)
    
    analyst_series = []
    date_labels = []
    
    for d in dates:
        date_str = d.strftime('%Y-%m-%d')
        date_labels.append(date_str)
        current_date = d.date()
        
        # Get all stocks that have been analyzed by this date
        active_analyses = [(a, p, c) for a, p, c in sorted_analyses if a.analysis_date <= current_date]
        
        if not active_analyses:
            analyst_series.append(0)
            continue
        
        # Calculate equal-weighted average return of all active stocks
        # Each stock's return is calculated from its analysis date to current date
        total_ret = 0
        count = 0
        
        for analysis, perf, company in active_analyses:
            # Get price at analysis date
            price_at_analysis = StockPrice.query.filter(
                StockPrice.company_id == company.id,
                StockPrice.date <= analysis.analysis_date
            ).order_by(StockPrice.date.desc()).first()
            
            # Get price at current chart date
            price_current = StockPrice.query.filter(
                StockPrice.company_id == company.id,
                StockPrice.date <= current_date
            ).order_by(StockPrice.date.desc()).first()
            
            if price_at_analysis and price_current and float(price_at_analysis.close_price) > 0:
                ret = ((float(price_current.close_price) - float(price_at_analysis.close_price)) / 
                       float(price_at_analysis.close_price)) * 100
                total_ret += ret
                count += 1
        
        if count > 0:
            avg_return = total_ret / count
            analyst_series.append(round(avg_return, 2))
        else:
            analyst_series.append(0)
    
    # Generate benchmark series
    spy_series = _get_benchmark_series_from_cache(dates, 'SPY')
    vt_series = _get_benchmark_series_from_cache(dates, 'VT')
    eems_series = _get_benchmark_series_from_cache(dates, 'EEMS')
    
    return {
        'dates': date_labels,
        'analyst_series': analyst_series,
        'spy_series': spy_series,
        'vt_series': vt_series,
        'eems_series': eems_series,
    }


@admin_bp.route('/update-benchmarks', methods=['POST'])
@admin_required
def update_benchmarks():
    """Update cached benchmark prices from Yahoo Finance."""
    tickers = ['SPY', 'VT', 'EEMS']
    end_date = date.today()
    # Fetch 5 years of data to cover all possible analysis histories
    # This ensures we have data for views going back several years
    start_date = end_date - timedelta(days=1825)  # 5 years of data
    
    updated = 0
    errors = []
    
    for ticker in tickers:
        try:
            from ..utils.yahooquery_helper import fetch_prices
            df = fetch_prices(ticker, start_date, end_date)
            
            if df.empty:
                errors.append(f"{ticker}: No data returned")
                continue
            
            # Get existing dates for this ticker
            existing_dates = {bp.date for bp in BenchmarkPrice.query.filter_by(ticker=ticker).all()}
            
            new_records = 0
            for _, row in df.iterrows():
                price_date = row['Date'].date() if hasattr(row['Date'], 'date') else row['Date']
                
                if price_date in existing_dates:
                    continue
                
                bp = BenchmarkPrice(
                    ticker=ticker,
                    date=price_date,
                    close_price=row['close_price']
                )
                db.session.add(bp)
                new_records += 1
            
            db.session.commit()
            updated += new_records
            
        except Exception as e:
            errors.append(f"{ticker}: {str(e)}")
            current_app.logger.error(f"Error updating benchmark {ticker}: {e}")
    
    if errors:
        flash(f'Benchmarks updated: {updated} new prices. Errors: {", ".join(errors)}', 'warning')
    else:
        flash(f'Benchmarks updated: {updated} new prices cached.', 'success')
    
    return redirect(request.referrer or url_for('admin.board'))


# API Routes for AJAX calls

@admin_bp.route('/api/company-tickers/resolve/<int:company_id>', methods=['POST'])
@admin_required
def api_resolve_ticker(company_id):
    """API endpoint to resolve ticker for a single company."""
    from flask import jsonify, request
    from ..utils.ticker_resolver import resolve_ticker
    
    company = Company.query.get_or_404(company_id)
    
    try:
        ticker, is_other, source = resolve_ticker(company.name, force_refresh=True)
        
        if is_other:
            return jsonify({'success': True, 'ticker': None, 'is_other': True, 'source': source})
        elif ticker:
            # Update company
            company.ticker_symbol = ticker
            db.session.commit()
            return jsonify({'success': True, 'ticker': ticker, 'is_other': False, 'source': source})
        else:
            return jsonify({'success': False, 'error': 'Could not resolve ticker'})
    except Exception as e:
        current_app.logger.error(f"Error resolving ticker for {company.name}: {e}")
        return jsonify({'success': False, 'error': str(e)})


@admin_bp.route('/api/mark-as-other/<int:company_id>', methods=['POST'])
@admin_required
def api_mark_as_other(company_id):
    """Mark a company as 'Other' (non-stock event)."""
    from flask import jsonify
    
    company = Company.query.get_or_404(company_id)
    
    try:
        # Check if mapping exists
        mapping = CompanyTickerMapping.query.filter_by(company_name=company.name).first()
        if mapping:
            mapping.is_other_event = True
            mapping.ticker_symbol = None
        else:
            mapping = CompanyTickerMapping(
                company_name=company.name,
                ticker_symbol=None,
                source='manual',
                is_other_event=True
            )
            db.session.add(mapping)
        
        # Clear company ticker
        company.ticker_symbol = None
        db.session.commit()
        
        return jsonify({'success': True, 'message': f'{company.name} marked as Other'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error marking {company.name} as other: {e}")
        return jsonify({'success': False, 'error': str(e)})


@admin_bp.route('/api/update-ticker/<int:company_id>', methods=['POST'])
@admin_required
def api_update_ticker(company_id):
    """Update ticker symbol for a company manually."""
    from flask import jsonify, request
    
    company = Company.query.get_or_404(company_id)
    
    try:
        data = request.get_json()
        if not data or 'ticker' not in data:
            return jsonify({'success': False, 'error': 'No ticker provided'})
        
        ticker = data['ticker'].strip().upper()
        if not ticker:
            return jsonify({'success': False, 'error': 'Empty ticker'})
        
        # Update company
        company.ticker_symbol = ticker
        
        # Update or create mapping
        mapping = CompanyTickerMapping.query.filter_by(company_name=company.name).first()
        if mapping:
            mapping.ticker_symbol = ticker
            mapping.is_other_event = False
            mapping.source = 'manual'
        else:
            mapping = CompanyTickerMapping(
                company_name=company.name,
                ticker_symbol=ticker,
                source='manual'
            )
            db.session.add(mapping)
        
        db.session.commit()
        return jsonify({'success': True, 'ticker': ticker})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating ticker for {company.name}: {e}")
        return jsonify({'success': False, 'error': str(e)})


@admin_bp.route('/api/toggle-mapping-other/<int:mapping_id>', methods=['POST'])
@admin_required
def api_toggle_mapping_other(mapping_id):
    """Toggle a mapping as Other event (mark as non-stock)."""
    from flask import jsonify
    
    mapping = CompanyTickerMapping.query.get_or_404(mapping_id)
    
    try:
        # Mark as Other event
        mapping.is_other_event = True
        
        # Also clear the company ticker
        company = Company.query.filter_by(name=mapping.company_name).first()
        if company:
            company.ticker_symbol = None
        
        db.session.commit()
        return jsonify({'success': True, 'message': f'{mapping.company_name} marked as Other'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error marking {mapping.company_name} as other: {e}")
        return jsonify({'success': False, 'error': str(e)})


@admin_bp.route('/api/move-back-from-other/<int:mapping_id>', methods=['POST'])
@admin_required
def api_move_back_from_other(mapping_id):
    """Move a company back from Other events with optional ticker."""
    from flask import jsonify, request
    
    mapping = CompanyTickerMapping.query.get_or_404(mapping_id)
    
    try:
        data = request.get_json() or {}
        ticker = data.get('ticker', '').strip().upper()
        company_id = data.get('company_id')
        
        if ticker:
            # Validate ticker has price data
            from ..utils.yahooquery_helper import fetch_prices
            from datetime import date, timedelta
            
            try:
                end_date = date.today()
                start_date = end_date - timedelta(days=7)
                df = fetch_prices(ticker, start_date, end_date)
                if df.empty:
                    return jsonify({'success': False, 'error': f'No price data available for ticker {ticker}'})
            except Exception as e:
                return jsonify({'success': False, 'error': f'Could not validate ticker {ticker}: {e}'})
            
            # Update mapping with ticker
            mapping.ticker_symbol = ticker
            mapping.is_other_event = False
            mapping.source = 'manual'
            
            # Update company ticker
            company = Company.query.filter_by(name=mapping.company_name).first()
            if company:
                company.ticker_symbol = ticker
            elif company_id:
                company = Company.query.get(company_id)
                if company:
                    company.ticker_symbol = ticker
        else:
            # Just toggle the flag without setting a ticker
            mapping.is_other_event = False
        
        db.session.commit()
        return jsonify({'success': True, 'message': f'{mapping.company_name} moved back', 'ticker': ticker if ticker else None})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error moving {mapping.company_name} back: {e}")
        return jsonify({'success': False, 'error': str(e)})


# Comprehensive Export Routes

@admin_bp.route('/export/comprehensive')
@login_required
def export_comprehensive():
    """
    Comprehensive Excel export with all analyst data.
    Supports cached downloads or generating fresh data.
    """
    from ..utils.export_helper import (
        generate_comprehensive_export, 
        get_cached_export_info,
        get_sector_cache_info
    )
    
    force_new = request.args.get('fresh', 'false').lower() == 'true'
    
    try:
        data, is_cached, cache_info = generate_comprehensive_export(force_new=force_new)
        
        if is_cached:
            flash(f'Downloaded cached export from {cache_info["age_days"]} days ago.', 'info')
        else:
            flash('Generated fresh export successfully.', 'success')
        
        return send_file(
            io.BytesIO(data),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'analyst_comprehensive_report_{datetime.now().strftime("%Y%m%d_%H%M")}.xlsx'
        )
    except ImportError as e:
        flash('Excel export requires pandas and openpyxl. Please install: pip install pandas openpyxl', 'danger')
        return redirect(request.referrer or url_for('admin.performance'))
    except Exception as e:
        current_app.logger.error(f'Error generating comprehensive export: {e}')
        flash(f'Error generating export: {str(e)}', 'danger')
        return redirect(request.referrer or url_for('admin.performance'))


@admin_bp.route('/export/status')
@login_required
def export_status():
    """Get status of cached exports for AJAX calls."""
    from ..utils.export_helper import get_cached_export_info, get_sector_cache_info
    
    comprehensive_cache = get_cached_export_info('comprehensive')
    sector_cache = get_sector_cache_info()
    
    return {
        'comprehensive': {
            'has_cache': comprehensive_cache is not None,
            'age_days': comprehensive_cache['age_days'] if comprehensive_cache else None,
            'created_at': comprehensive_cache['created_at'].isoformat() if comprehensive_cache else None,
            'is_valid': comprehensive_cache['is_valid'] if comprehensive_cache else False
        },
        'sector': sector_cache
    }


@admin_bp.route('/export/refresh-sectors', methods=['POST'])
@login_required
def refresh_sectors():
    """Trigger sector cache refresh in background."""
    from ..utils.sector_helper import refresh_all_sectors
    
    try:
        stats = refresh_all_sectors()
        flash(f'Sector refresh started: {stats["updated"]} updated, {stats["failed"]} failed.', 'success')
    except Exception as e:
        flash(f'Error refreshing sectors: {str(e)}', 'danger')
    
    return redirect(request.referrer or url_for('analyst.overview'))


@admin_bp.route('/unified-update')
@admin_required
def unified_update():
    """
    Unified Update page - combines CSV upload, ticker mappings, recalculation, and debug tools.
    This is the main update interface for the entire system.
    """
    from ..models import SystemSettings, RecalculationLog, CsvUpload
    import os

    recent_logs = RecalculationLog.query.order_by(
        RecalculationLog.started_at.desc()
    ).limit(10).all()

    recent_uploads = CsvUpload.query.order_by(
        CsvUpload.uploaded_at.desc()
    ).limit(5).all()

    auto_recalc_enabled = SystemSettings.get('auto_recalc_enabled', False)
    auto_recalc_day = SystemSettings.get('auto_recalc_day', 'fri')
    auto_recalc_hour = SystemSettings.get('auto_recalc_hour', 23)
    auto_recalc_minute = SystemSettings.get('auto_recalc_minute', 0)
    notion_api_key = os.environ.get('NOTION_API_KEY', '') or SystemSettings.get('notion_api_key', '')
    notion_database_id = os.environ.get('NOTION_DATABASE_ID', '') or SystemSettings.get('notion_database_id', '')
    notion_configured = bool(notion_api_key and notion_database_id)

    total_analyses = Analysis.query.count()
    missing_tickers = Company.query.filter(
        Company.ticker_symbol.is_(None)
    ).outerjoin(
        CompanyTickerMapping, Company.name == CompanyTickerMapping.company_name
    ).filter(
        (CompanyTickerMapping.is_other_event.is_(None)) | (CompanyTickerMapping.is_other_event == False)
    ).count()

    return render_template('admin/unified_update.html',
                         recent_logs=recent_logs,
                         recent_uploads=recent_uploads,
                         auto_recalc_enabled=auto_recalc_enabled,
                         auto_recalc_day=auto_recalc_day,
                         auto_recalc_hour=auto_recalc_hour,
                         auto_recalc_minute=auto_recalc_minute,
                         notion_configured=notion_configured,
                         total_analyses=total_analyses,
                         missing_tickers=missing_tickers)


@admin_bp.route('/unified-update/settings', methods=['POST'])
@admin_required
def unified_update_settings():
    """Save automated recalculation settings."""
    from ..models import SystemSettings

    auto_recalc_enabled = request.form.get('auto_recalc_enabled') == 'on'
    auto_recalc_day = request.form.get('auto_recalc_day', 'fri')
    auto_recalc_hour = int(request.form.get('auto_recalc_hour', 23))
    auto_recalc_minute = int(request.form.get('auto_recalc_minute', 0))

    SystemSettings.set('auto_recalc_enabled', auto_recalc_enabled, 'boolean', 'Enable automated recalculation')
    SystemSettings.set('auto_recalc_day', auto_recalc_day, 'string', 'Day of week for automated recalculation')
    SystemSettings.set('auto_recalc_hour', auto_recalc_hour, 'integer', 'Hour for automated recalculation')
    SystemSettings.set('auto_recalc_minute', auto_recalc_minute, 'integer', 'Minute for automated recalculation')

    flash('Settings saved successfully.', 'success')
    return redirect(url_for('admin.unified_update'))


@admin_bp.route('/unified-update/download-notion', methods=['POST'])
@admin_required
def download_notion_csv():
    """Download CSV from Notion and import."""
    from ..models import SystemSettings
    from ..utils.notion_helper import NotionAPIError, download_notion_export
    from ..utils.csv_import import CsvImporter
    import os

    api_key = os.environ.get('NOTION_API_KEY', '') or SystemSettings.get('notion_api_key', '')
    database_id = os.environ.get('NOTION_DATABASE_ID', '') or SystemSettings.get('notion_database_id', '')

    if not api_key or not database_id:
        flash('Notion API key or database ID not configured. Set NOTION_API_KEY and NOTION_DATABASE_ID in .env.', 'danger')
        return redirect(url_for('admin.unified_update'))

    try:
        column_mapping = {
            'Company': 'Company',
            'Date': 'Date',
            'Sector': 'Sector',
            'Analyst': 'Analyst',
            'Opponent': 'Opponent',
            'Comment': 'Comment',
            'Status': 'Status',
            'Files & media': 'Files & media'
        }

        result = download_notion_export(database_id, api_key, column_mapping)
        csv_content = result['csv_content']

        if not csv_content:
            flash('No data found in Notion database.', 'warning')
            return redirect(url_for('admin.unified_update'))

        importer = CsvImporter(
            csv_content=csv_content,
            filename=f'notion_export_{datetime.now().strftime("%Y%m%d_%H%M")}.csv',
            uploaded_by=current_user.id
        )
        stats = importer.process()

        if stats['success']:
            flash(f'Notion import completed: {stats["created"]} created, {stats["updated"]} updated, {stats["skipped"]} skipped.', 'success')
        else:
            flash(f'Import failed: {stats.get("error", "Unknown error")}', 'danger')

    except NotionAPIError as e:
        flash(f'Notion error: {str(e)}', 'danger')
    except Exception as e:
        current_app.logger.exception('Notion download failed')
        flash(f'Error downloading from Notion: {str(e)}', 'danger')

    return redirect(url_for('admin.unified_update'))


@admin_bp.route('/unified-update/full-recalc', methods=['POST'])
@admin_required
def full_recalculation():
    """
    Perform a full system recalculation.
    This recalculates prices, performance, benchmarks, and invalidates all caches.
    Uses unified_calculator for progress tracking.
    """
    from .. import create_app
    from ..utils.unified_calculator import recalculate_all_unified, is_calculation_running
    from datetime import date, timedelta
    import threading

    if is_calculation_running():
        return jsonify({'error': 'A recalculation is already in progress'}), 400

    def run_full_recalc():
        app = create_app()
        with app.app_context():
            try:
                from ..extensions import db as db_local
                from ..models import RecalculationLog
                from ..utils.neon_cache import invalidate_all_public_cache as inv_pub, invalidate_board_cache as inv_board, warm_public_caches as warm_pub
                from ..utils.overview_cache import invalidate_cache as inv_overview, save_overview_cache
                from ..utils.yahooquery_helper import fetch_benchmark_prices as fetch_bp
                from ..utils.unified_calculator import recalculate_all_unified as recalc_unified

                log_entry = RecalculationLog(run_type='manual')
                db_local.session.add(log_entry)
                db_local.session.commit()

                stats = {
                    'analyses_processed': 0,
                    'prices_updated': 0,
                    'calculations_updated': 0,
                    'errors_count': 0
                }

                tickers = ['SPY', 'VT', 'EEMS']
                end_date = date.today()
                start_date = end_date - timedelta(days=1825)

                for ticker in tickers:
                    try:
                        df = fetch_bp(ticker, start_date, end_date)
                        if not df.empty:
                            stats['prices_updated'] += len(df)
                    except Exception as e:
                        stats['errors_count'] += 1

                try:
                    all_views_data = recalc_unified(force=True)
                    for cache_key, view_data in all_views_data.items():
                        save_overview_cache(cache_key, view_data)
                except Exception as e:
                    stats['errors_count'] += 1

                inv_pub()
                inv_board()
                inv_overview()
                warm_pub()

                log_entry.mark_completed(stats)

            except Exception as e:
                try:
                    from ..models import RecalculationLog
                    log_entry = RecalculationLog(run_type='manual')
                    db_local.session.add(log_entry)
                    db_local.session.commit()
                    log_entry.mark_failed(str(e))
                except:
                    pass

    thread = threading.Thread(target=run_full_recalc, daemon=True)
    thread.start()

    return jsonify({'status': 'started', 'message': 'Full recalculation started'})

    return jsonify({'status': 'started', 'message': 'Full recalculation started in background'})


@admin_bp.route('/unified-update/recalculate-progress')
@admin_required
def recalculate_progress():
    """
    SSE endpoint for real-time recalculation progress updates.
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

            should_send = (last_status is None or
                          current_status != last_status or
                          len(current_logs) != last_logs_count)

            if should_send:
                data = progress.to_dict()
                yield f"data: {json.dumps(data)}\n\n"

                last_status = current_status
                last_logs_count = len(current_logs)
                idle_count = 0

                if current_status in ['completed', 'error']:
                    time.sleep(2)
                    yield f"data: {json.dumps(progress.to_dict())}\n\n"
                    break
            else:
                idle_count += 1
                if idle_count >= 20:
                    yield f"data: {json.dumps(progress.to_dict())}\n\n"
                    idle_count = 0

            time.sleep(0.5)

    return current_app.response_class(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
    )


@admin_bp.route('/unified-update/logs')
@admin_required
def recalculation_logs():
    """View recalculation logs."""
    from ..models import RecalculationLog
    
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    logs = RecalculationLog.query.order_by(
        RecalculationLog.started_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('admin/recalculation_logs.html', logs=logs)


@admin_bp.route('/unified-update/ticker-resolver', methods=['POST'])
@admin_required
def resolve_missing_tickers():
    """Resolve all missing tickers using AI/ticker resolver."""
    from ..utils.ticker_resolver import resolve_ticker
    
    missing_companies = Company.query.filter(Company.ticker_symbol.is_(None)).all()
    
    stats = {
        'total': len(missing_companies),
        'resolved': 0,
        'other': 0,
        'failed': 0
    }
    
    for company in missing_companies:
        try:
            ticker, is_other, source = resolve_ticker(company.name)
            if is_other:
                stats['other'] += 1
            elif ticker:
                company.ticker_symbol = ticker
                stats['resolved'] += 1
            else:
                stats['failed'] += 1
        except Exception as e:
            stats['failed'] += 1
            current_app.logger.error(f"Error resolving ticker for {company.name}: {e}")
    
    db.session.commit()
    
    flash(f'Ticker resolution: {stats["resolved"]} resolved, {stats["other"]} marked as Other, {stats["failed"]} failed.', 'success')
    return redirect(url_for('admin.unified_update'))
