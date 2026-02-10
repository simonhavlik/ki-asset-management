"""
Unified data calculator for efficient overview recalculation.

This module provides a unified approach to calculating all overview data:
1. Fetch all stock price data ONCE
2. Calculate all performance metrics for all analyses
3. Filter views (approved, purchased, board_approved, etc.) from the unified dataset
4. Cache results for fast subsequent access

This is much more efficient than fetching data separately for each view.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import threading

from sqlalchemy import func
from ..extensions import db
from ..models import Analysis, PerformanceCalculation, Company, StockPrice, User, analysis_analysts, Vote, PortfolioPurchase
from .yahooquery_helper import fetch_prices, get_price_on_date, get_latest_price
from .performance import PerformanceCalculator

logger = logging.getLogger(__name__)


@dataclass
class CalculationProgress:
    """Track progress of calculation for SSE updates."""
    total_companies: int = 0
    processed_companies: int = 0
    current_company: str = ""
    status: str = "idle"  # idle, fetching_prices, calculating, completed, error
    message: str = ""
    logs: List[str] = field(default_factory=list)
    _lock: Any = field(default_factory=threading.Lock)
    
    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'total': self.total_companies,
                'processed': self.processed_companies,
                'current': self.current_company,
                'status': self.status,
                'message': self.message,
                'progress_pct': round((self.processed_companies / self.total_companies * 100), 1) if self.total_companies > 0 else 0,
                'logs': list(self.logs[-50:])  # Keep last 50 logs
            }
    
    def log(self, message: str):
        """Add a log message with timestamp."""
        timestamp = datetime.now().strftime('%H:%M:%S')
        with self._lock:
            self.logs.append(f"[{timestamp}] {message}")
            self.message = message
        logger.info(message)
        
    def update_status(self, status: str):
        """Update status thread-safely."""
        with self._lock:
            self.status = status
            
    def update_progress(self, current: str, processed: int):
        """Update progress thread-safely."""
        with self._lock:
            self.current_company = current
            self.processed_companies = processed


class UnifiedDataCalculator:
    """
    Unified calculator that fetches all data once and derives all views from it.
    
    Key optimizations:
    1. Fetch stock prices for all companies in parallel batches
    2. Calculate all performance metrics once
    3. Filter different views from the unified dataset (no refetching)
    4. Progressive caching - broader views cache data for narrower views
    """
    
    # Define view hierarchy - broader views provide data for narrower ones
    VIEW_HIERARCHY = {
        'all': ['all_approved', 'approved_neutral', 'board_approved', 'purchased'],
        'approved_neutral': ['all_approved', 'board_approved', 'purchased'],
        'all_approved': ['board_approved', 'purchased'],
        'board_approved': ['purchased'],
        'purchased': []
    }
    
    def __init__(self, progress: Optional[CalculationProgress] = None):
        self.progress = progress or CalculationProgress()
        self.calculator = PerformanceCalculator()
        self._unified_data: Optional[Dict[str, Any]] = None
        
    def recalculate_all(self, force: bool = False) -> Dict[str, Any]:
        """
        Recalculate ALL data in one efficient pass.
        
        Returns dict with all calculated data for all views.
        """
        start_time = time.time()
        self.progress.update_status("fetching_prices")
        self.progress.log("Starting unified recalculation...")
        
        try:
            # Step 1: Get all analyses and their companies
            all_analyses = self._get_all_analyses_with_companies()
            self.progress.total_companies = len(all_analyses)
            self.progress.log(f"Found {len(all_analyses)} companies to process")
            
            # Step 2: Fetch prices for all companies in parallel batches
            self._fetch_all_prices_parallel(all_analyses)
            
            # Step 3: Calculate performance for all analyses
            self.progress.update_status("calculating")
            self.progress.log("Calculating performance metrics...")
            performance_data = self._calculate_all_performance(all_analyses)
            
            # Step 4: Build unified dataset with all metadata
            self._unified_data = self._build_unified_dataset(all_analyses, performance_data)
            
            # Step 5: Calculate all views from unified data
            self.progress.log("Building view datasets...")
            all_views_data = self._calculate_all_views()
            
            elapsed = time.time() - start_time
            self.progress.update_status("completed")
            self.progress.log(f"Recalculation completed in {elapsed:.1f}s")
            
            return all_views_data
            
        except Exception as e:
            self.progress.update_status("error")
            self.progress.log(f"ERROR: {str(e)}")
            logger.exception("Error during unified recalculation")
            raise
    
    def _get_all_analyses_with_companies(self) -> List[Dict]:
        """Get all analyses with their company info."""
        analyses = db.session.query(Analysis, Company).join(
            Company, Analysis.company_id == Company.id
        ).filter(
            Analysis.status.in_(['On Watchlist', 'Neutral', 'Refused'])
        ).all()
        
        result = []
        for analysis, company in analyses:
            if not company.ticker_symbol:
                continue
            if self.calculator._is_other_event(company):
                continue
                
            result.append({
                'analysis': analysis,
                'company': company,
                'analysis_id': analysis.id,
                'company_id': company.id,
                'company_name': company.name,
                'ticker': company.ticker_symbol,
                'status': analysis.status,
                'analysis_date': analysis.analysis_date,
                'purchase_date': analysis.purchase_date
            })
        
        return result
    
    def _fetch_all_prices_parallel(self, analyses: List[Dict], batch_size: int = 20):
        """Fetch prices for all companies using YahooQuery's multi-ticker feature."""
        # Group by company to avoid duplicate fetches
        companies_to_fetch = {}
        for item in analyses:
            company_id = item['company_id']
            if company_id not in companies_to_fetch:
                companies_to_fetch[company_id] = item['company']
        
        total = len(companies_to_fetch)
        self.progress.log(f"FETCHING PRICES: {total} unique companies to process")
        self.progress.log(f"Using multi-ticker batch fetching (batch size: {batch_size})")
        
        # Get list of companies and their tickers
        company_list = list(companies_to_fetch.values())
        processed = 0
        
        # Process in batches using multi-ticker fetching
        for i in range(0, len(company_list), batch_size):
            batch_num = (i // batch_size) + 1
            total_batches = (len(company_list) + batch_size - 1) // batch_size
            batch = company_list[i:i + batch_size]
            
            self.progress.log(f"--- Batch {batch_num}/{total_batches} ({len(batch)} companies) ---")
            
            # Get tickers for this batch
            tickers = [c.ticker_symbol for c in batch if c.ticker_symbol]
            
            if not tickers:
                self.progress.log("No valid tickers in batch, skipping...")
                continue
            
            try:
                # Use multi-ticker fetching - ONE API call for entire batch!
                from .yahooquery_helper import fetch_prices_batch
                from ..models import StockPrice
                
                # Determine date range for this batch (earliest analysis date to today)
                earliest_date = min((c.created_at for c in batch if hasattr(c, 'created_at') and c.created_at), default=datetime.now() - timedelta(days=365*2))
                start_date = earliest_date.date() if isinstance(earliest_date, datetime) else earliest_date
                start_date = start_date - timedelta(days=7)  # Buffer for price on exact date
                end_date = date.today()
                
                # Fetch all prices in ONE API call
                batch_results = fetch_prices_batch(tickers, start_date, end_date)
                
                # Process results for each company
                for company in batch:
                    processed += 1
                    self.progress.update_progress(company.name, processed)
                    
                    if company.ticker_symbol not in batch_results:
                        self.progress.log(f"[{processed}/{total}] {company.name} ({company.ticker_symbol}): No data returned")
                        continue
                    
                    df = batch_results[company.ticker_symbol]
                    
                    if df.empty:
                        self.progress.log(f"[{processed}/{total}] {company.name} ({company.ticker_symbol}): Empty data")
                        continue
                    
                    # Check which dates are already stored
                    existing_dates = {sp.date for sp in StockPrice.query.filter_by(company_id=company.id).all()}
                    
                    # Insert new records
                    new_records = 0
                    for _, row in df.iterrows():
                        price_date = row['Date'].date() if hasattr(row['Date'], 'date') else row['Date']
                        if price_date not in existing_dates:
                            sp = StockPrice(
                                company_id=company.id,
                                date=price_date,
                                close_price=float(row['close_price']),
                                volume=row.get('volume')
                            )
                            db.session.add(sp)
                            new_records += 1
                    
                    if new_records > 0:
                        db.session.commit()
                        self.progress.log(f"[{processed}/{total}] {company.name} ({company.ticker_symbol}): Added {new_records} new prices")
                    else:
                        self.progress.log(f"[{processed}/{total}] {company.name} ({company.ticker_symbol}): Already up to date")
                
                self.progress.log(f"Batch {batch_num} complete: {processed}/{total} ({processed/total*100:.1f}%)")
                
                # Small delay between batches to be nice to the API
                time.sleep(0.5)
                
            except Exception as e:
                self.progress.log(f"ERROR in batch {batch_num}: {str(e)}")
                logger.exception(f"Error fetching batch {batch_num}")
                # Continue with next batch
    
    def _calculate_all_performance(self, analyses: List[Dict]) -> Dict[int, Dict]:
        """Calculate performance for all analyses."""
        performance_data = {}
        
        for item in analyses:
            analysis = item['analysis']
            company = item['company']
            
            try:
                # Get prices
                price_at_analysis = get_price_on_date(company.id, analysis.analysis_date)
                price_current = get_latest_price(company.id)
                
                if price_at_analysis and price_current and price_at_analysis > 0:
                    # Convert Decimal to float for calculations
                    price_analysis_f = float(price_at_analysis)
                    price_current_f = float(price_current)
                    
                    return_pct = ((price_current_f - price_analysis_f) / price_analysis_f) * 100
                    
                    # Calculate annualized return
                    days = (date.today() - analysis.analysis_date).days
                    if days > 365:
                        annualized = ((1 + return_pct / 100) ** (365 / days) - 1) * 100
                    else:
                        annualized = return_pct
                    
                    performance_data[analysis.id] = {
                        'return_pct': return_pct,
                        'annualized_return': annualized,
                        'price_at_analysis': price_analysis_f,
                        'price_current': price_current_f,
                        'days_held': days
                    }
                    
                    # Store in database (using float values)
                    self._store_performance_calculation(analysis.id, price_analysis_f, price_current_f, return_pct)
                    
            except Exception as e:
                logger.warning(f"Error calculating performance for {company.name}: {e}")
        
        return performance_data
    
    def _store_performance_calculation(self, analysis_id: int, price_at_analysis: float, 
                                       price_current: float, return_pct: float):
        """Store or update performance calculation in database."""
        today = date.today()
        
        existing = PerformanceCalculation.query.filter_by(
            analysis_id=analysis_id,
            calculation_date=today
        ).first()
        
        if existing:
            existing.price_at_analysis = price_at_analysis
            existing.price_current = price_current
            existing.return_pct = return_pct
            existing.calculated_at = datetime.utcnow()
        else:
            pc = PerformanceCalculation(
                analysis_id=analysis_id,
                calculation_date=today,
                price_at_analysis=price_at_analysis,
                price_current=price_current,
                return_pct=return_pct
            )
            db.session.add(pc)
        
        db.session.commit()
    
    def _build_unified_dataset(self, analyses: List[Dict], performance_data: Dict[int, Dict]) -> Dict[str, Any]:
        """Build unified dataset with all analyses and their metadata."""
        unified = {
            'analyses': {},
            'by_status': {
                'On Watchlist': [],
                'Neutral': [],
                'Refused': []
            },
            'by_board_approval': [],
            'by_purchase': [],
            'metadata': {
                'total_count': 0,
                'with_performance': 0,
                'calculation_date': date.today().isoformat()
            }
        }
        
        # Get all votes and purchases for efficient lookup
        all_votes = self._get_all_votes()
        all_purchases = self._get_all_purchases()
        
        for item in analyses:
            analysis = item['analysis']
            company = item['company']
            perf = performance_data.get(analysis.id)
            
            analysis_data = {
                'analysis_id': analysis.id,
                'company_id': company.id,
                'company_name': company.name,
                'ticker': company.ticker_symbol,
                'status': analysis.status,
                'analysis_date': analysis.analysis_date.isoformat() if analysis.analysis_date else None,
                'purchase_date': analysis.purchase_date.isoformat() if analysis.purchase_date else None,
                'performance': perf,
                'board_approved': self._is_board_approved(analysis.id, all_votes),
                'purchased': analysis.id in all_purchases
            }
            
            unified['analyses'][analysis.id] = analysis_data
            unified['by_status'][analysis.status].append(analysis.id)
            
            if analysis_data['board_approved']:
                unified['by_board_approval'].append(analysis.id)
            
            if analysis_data['purchased']:
                unified['by_purchase'].append(analysis.id)
            
            unified['metadata']['total_count'] += 1
            if perf:
                unified['metadata']['with_performance'] += 1
        
        return unified
    
    def _get_all_votes(self) -> Dict[int, Tuple[int, int]]:
        """Get all votes grouped by analysis_id. Returns dict of analysis_id -> (yes_count, no_count)."""
        votes = db.session.query(Vote).all()
        vote_counts = {}
        
        for vote in votes:
            if vote.analysis_id not in vote_counts:
                vote_counts[vote.analysis_id] = [0, 0]
            if vote.vote:
                vote_counts[vote.analysis_id][0] += 1
            else:
                vote_counts[vote.analysis_id][1] += 1
        
        return vote_counts
    
    def _get_all_purchases(self) -> set:
        """Get all purchased analysis IDs."""
        purchases = PortfolioPurchase.query.all()
        return {p.analysis_id for p in purchases}
    
    def _is_board_approved(self, analysis_id: int, all_votes: Dict) -> bool:
        """Check if analysis is board approved (more yes than no votes)."""
        if analysis_id not in all_votes:
            return False
        yes_count, no_count = all_votes[analysis_id]
        return yes_count > no_count
    
    def _calculate_all_views(self) -> Dict[str, Any]:
        """Calculate data for all views from the unified dataset."""
        if not self._unified_data:
            raise ValueError("Unified data not built yet")
        
        views = {}
        
        # Calculate each view for both methods
        for view_name in ['all', 'approved_neutral', 'all_approved', 'board_approved', 'purchased']:
            for method in ['incremental', 'equal']:
                cache_key = f"{view_name}_{method}"
                self.progress.log(f"Calculating view: {view_name} (method: {method})")
                views[cache_key] = self._calculate_view(view_name, method)
        
        return views
    
    def _calculate_view(self, view_name: str, method: str = 'incremental') -> Dict[str, Any]:
        """Calculate data for a specific view from unified dataset."""
        if not self._unified_data:
            raise ValueError("Unified data not built yet")
        
        # Get analysis IDs for this view
        analysis_ids = self._get_analysis_ids_for_view(view_name)
        
        # Calculate portfolio performance
        portfolio_performance = self._calculate_portfolio_performance(analysis_ids)
        
        # Calculate series data with specified method
        series_all = self._calculate_series_for_analyses(analysis_ids, years=None, method=method)
        series_1y = self._calculate_series_for_analyses(analysis_ids, years=1, method=method)
        
        # Calculate sector statistics
        sector_stats = self._calculate_sector_stats(analysis_ids)
        
        # Calculate analyst rankings (these are global, not view-specific)
        analyst_rankings = self._calculate_analyst_rankings()
        
        # Calculate positive ratio
        positive_count = 0
        total_with_perf = 0
        
        for analysis_id in analysis_ids:
            analysis_data = self._unified_data['analyses'].get(analysis_id)
            if analysis_data and analysis_data.get('performance'):
                total_with_perf += 1
                if analysis_data['performance']['return_pct'] > 0:
                    positive_count += 1
        
        positive_ratio = (positive_count / total_with_perf * 100) if total_with_perf > 0 else 0
        
        return {
            'portfolio_performance': portfolio_performance,
            'series_all': series_all,
            'series_1y': series_1y,
            'sector_stats': sector_stats,
            'analyst_rankings': analyst_rankings,
            'positive_ratio': round(positive_ratio, 2),
            'total_positions': total_with_perf,
            'analysis_ids': analysis_ids,
            'calc_method': method
        }
    
    def _get_analysis_ids_for_view(self, view_name: str) -> List[int]:
        """Get analysis IDs for a specific view from unified data."""
        if not self._unified_data:
            return []
        
        if view_name == 'all':
            return list(self._unified_data['analyses'].keys())
        
        elif view_name == 'approved_neutral':
            return (self._unified_data['by_status'].get('On Watchlist', []) + 
                    self._unified_data['by_status'].get('Neutral', []))
        
        elif view_name == 'all_approved':
            return self._unified_data['by_status'].get('On Watchlist', [])
        
        elif view_name == 'board_approved':
            return self._unified_data['by_board_approval']
        
        elif view_name == 'purchased':
            return self._unified_data['by_purchase']
        
        return []
    
    def _calculate_portfolio_performance(self, analysis_ids: List[int]) -> Dict[str, Any]:
        """Calculate portfolio performance for a list of analysis IDs."""
        if not analysis_ids or not self._unified_data:
            return {
                'num_positions': 0,
                'total_return': None,
                'annualized_return': None,
                'start_date': None,
                'benchmark_spy': None,
                'benchmark_ftse': None,
                'benchmark_eems': None
            }
        
        total_return = 0.0
        annualized_return = 0.0
        count = 0
        earliest_date = None
        
        for analysis_id in analysis_ids:
            analysis_data = self._unified_data['analyses'].get(analysis_id)
            if not analysis_data:
                continue
            
            perf = analysis_data.get('performance')
            if perf:
                # Ensure values are float (not Decimal)
                ret = float(perf['return_pct'])
                annualized = float(perf['annualized_return'])
                total_return += ret
                annualized_return += annualized
                count += 1
                
                analysis_date = datetime.fromisoformat(analysis_data['analysis_date']).date() if analysis_data.get('analysis_date') else None
                if analysis_date and (earliest_date is None or analysis_date < earliest_date):
                    earliest_date = analysis_date
        
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
        
        # Get benchmark returns
        days = (date.today() - earliest_date).days if earliest_date else 365
        benchmark_spy = self._get_cached_benchmark_return('SPY', days)
        benchmark_ftse = self._get_cached_benchmark_return('VT', days)
        benchmark_eems = self._get_cached_benchmark_return('EEMS', days)
        
        return {
            'num_positions': count,
            'total_return': round(avg_return, 2),
            'annualized_return': round(avg_annualized, 2),
            'start_date': earliest_date.isoformat() if earliest_date else None,
            'benchmark_spy': round(benchmark_spy, 2),
            'benchmark_ftse': round(benchmark_ftse, 2),
            'benchmark_eems': round(benchmark_eems, 2)
        }
    
    def _calculate_series_for_analyses(self, analysis_ids: List[int], years: Optional[int] = None, method: str = 'incremental') -> Optional[Dict]:
        """Calculate time series for a list of analyses."""
        if not analysis_ids or not self._unified_data:
            return None
        
        # Get analyses with performance
        analyses_with_perf = []
        for analysis_id in analysis_ids:
            analysis_data = self._unified_data['analyses'].get(analysis_id)
            if analysis_data and analysis_data.get('performance'):
                analysis_date = datetime.fromisoformat(analysis_data['analysis_date']).date() if analysis_data.get('analysis_date') else None
                if analysis_date:
                    analyses_with_perf.append({
                        'analysis_id': analysis_id,
                        'analysis_date': analysis_date,
                        'company_id': analysis_data['company_id'],
                        'ticker': analysis_data['ticker'],
                        'return_pct': analysis_data['performance']['return_pct']
                    })
        
        if not analyses_with_perf:
            return None
        
        # Sort by analysis date
        analyses_with_perf.sort(key=lambda x: x['analysis_date'])
        end_date = date.today()
        
        # Determine date range based on years parameter
        # This ensures benchmark comparisons are consistent across views
        if years is not None:
            # Use fixed date range (e.g., last 12 months from today)
            earliest_date = end_date - timedelta(days=years * 365)
            # Filter analyses to only those within the date range
            analyses_with_perf = [a for a in analyses_with_perf if a['analysis_date'] >= earliest_date]
            if not analyses_with_perf:
                return None
        else:
            # For 'all' series, use the earliest analysis date
            earliest_date = analyses_with_perf[0]['analysis_date']
        
        # Generate monthly dates
        dates = []
        current = earliest_date
        while current <= end_date:
            dates.append(current.isoformat())
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                # Handle months with different days
                next_month = current.month + 1
                next_year = current.year
                if next_month > 12:
                    next_month = 1
                    next_year += 1
                try:
                    current = current.replace(year=next_year, month=next_month)
                except ValueError:
                    # Handle end of month (e.g., Jan 31 -> Feb 28)
                    current = current.replace(year=next_year, month=next_month, day=1)
                    # Go to last day of previous month
                    current = current - timedelta(days=1)
                    current = current.replace(day=min(current.day, 28))
        
        if not dates:
            dates = [earliest_date.isoformat(), end_date.isoformat()]
        
        # Calculate portfolio series based on method
        portfolio_series = []
        
        if method == 'equal':
            # Equal-weighted: simple average of all returns from entry date
            for date_str in dates:
                target_date = datetime.fromisoformat(date_str).date()
                active_analyses = [a for a in analyses_with_perf if a['analysis_date'] <= target_date]
                
                if not active_analyses:
                    portfolio_series.append(0.0)
                    continue
                
                total_ret = sum(a['return_pct'] for a in active_analyses)
                portfolio_series.append(round(total_ret / len(active_analyses), 2))
        
        else:  # incremental
            # Incremental rebalancing: simulate portfolio with rebalancing at each addition
            for date_str in dates:
                target_date = datetime.fromisoformat(date_str).date()
                active_analyses = [a for a in analyses_with_perf if a['analysis_date'] <= target_date]
                
                if not active_analyses:
                    portfolio_series.append(0.0)
                    continue
                
                # Calculate equal-weighted average return by fetching prices
                total_ret = 0.0
                count = 0
                
                for analysis in active_analyses:
                    company_id = analysis['company_id']
                    entry_price = get_price_on_date(company_id, analysis['analysis_date'])
                    current_price = get_price_on_date(company_id, target_date)
                    
                    if entry_price and current_price and entry_price > 0:
                        entry_price_f = float(entry_price)
                        current_price_f = float(current_price)
                        ret = ((current_price_f - entry_price_f) / entry_price_f) * 100
                        total_ret += ret
                        count += 1
                
                if count > 0:
                    portfolio_series.append(round(total_ret / count, 2))
                else:
                    portfolio_series.append(0.0)
        
        # Get benchmark series
        spy_series = self._get_benchmark_series('SPY', earliest_date, end_date, dates)
        vt_series = self._get_benchmark_series('VT', earliest_date, end_date, dates)
        eems_series = self._get_benchmark_series('EEMS', earliest_date, end_date, dates)
        
        return {
            'dates': dates,
            'portfolio_series': portfolio_series,
            'spy_series': spy_series,
            'vt_series': vt_series,
            'eems_series': eems_series
        }
    
    def _calculate_sector_stats(self, analysis_ids: List[int]) -> Dict[str, Any]:
        """Calculate sector statistics for a list of analyses."""
        from .sector_helper import get_company_sector_async
        
        sector_returns = {}
        sector_counts = {}
        
        for analysis_id in analysis_ids:
            analysis_data = self._unified_data['analyses'].get(analysis_id)
            if not analysis_data:
                continue
            
            company_id = analysis_data['company_id']
            company = Company.query.get(company_id)
            
            if not company:
                continue
            
            # Get sector (async version returns cached data)
            sector = get_company_sector_async(company)
            if not sector:
                sector = 'Unknown'
            
            perf = analysis_data.get('performance')
            if perf:
                # Ensure value is float (not Decimal)
                ret = float(perf['return_pct'])
                
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
        
        return {
            'all_sectors': sector_stats,
            'top_by_return': by_return,
            'top_by_risk': by_risk,
            'sector_counts': sector_counts
        }
    
    def _calculate_analyst_rankings(self) -> Dict[str, List]:
        """Calculate analyst rankings."""
        rankings = {
            'top_board_approved': [],
            'top_total': [],
            'top_win_rate': [],
            'top_performance': []
        }
        
        # Get all analysts
        analysts = db.session.query(User).join(
            analysis_analysts, User.id == analysis_analysts.c.user_id
        ).filter(
            analysis_analysts.c.role == 'analyst'
        ).distinct().all()
        
        # Board approved counts
        for user in analysts:
            count = db.session.query(Analysis).join(
                analysis_analysts, Analysis.id == analysis_analysts.c.analysis_id
            ).filter(
                analysis_analysts.c.user_id == user.id,
                analysis_analysts.c.role == 'analyst',
                Analysis.status == 'On Watchlist'
            ).count()
            
            rankings['top_board_approved'].append({
                'analyst_id': user.id,
                'analyst_name': user.full_name or user.email.split('@')[0],
                'count': count
            })
        
        rankings['top_board_approved'] = sorted(
            rankings['top_board_approved'], 
            key=lambda x: x['count'], 
            reverse=True
        )[:5]
        
        # Total counts
        for user in analysts:
            count = db.session.query(Analysis).join(
                analysis_analysts, Analysis.id == analysis_analysts.c.analysis_id
            ).filter(
                analysis_analysts.c.user_id == user.id,
                analysis_analysts.c.role == 'analyst',
                Analysis.status.in_(['On Watchlist', 'Neutral', 'Refused'])
            ).count()
            
            rankings['top_total'].append({
                'analyst_id': user.id,
                'analyst_name': user.full_name or user.email.split('@')[0],
                'count': count
            })
        
        rankings['top_total'] = sorted(
            rankings['top_total'], 
            key=lambda x: x['count'], 
            reverse=True
        )[:5]
        
        # Performance and win rate
        all_perfs = self.calculator.get_all_analysts_performance()
        
        # Win rate (min 3 analyses)
        win_rates = []
        for perf in all_perfs:
            if perf['num_analyses'] >= 3 and perf['win_rate'] is not None:
                win_rates.append({
                    'analyst_id': perf['analyst_id'],
                    'analyst_name': perf['analyst_name'],
                    'win_rate': perf['win_rate'],
                    'num_analyses': perf['num_analyses']
                })
        
        rankings['top_win_rate'] = sorted(
            win_rates, 
            key=lambda x: x['win_rate'], 
            reverse=True
        )[:5]
        
        # Performance
        rankings['top_performance'] = sorted(
            [p for p in all_perfs if p['avg_return'] is not None],
            key=lambda x: x['avg_return'],
            reverse=True
        )[:5]
        
        return rankings
    
    def _get_cached_benchmark_return(self, ticker: str, days: int) -> float:
        """Get benchmark return using cached data."""
        try:
            from ..models import BenchmarkPrice
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
        except Exception:
            pass
        
        # Fallback
        annual_returns = {'SPY': 10.0, 'VT': 9.0, 'EEMS': 7.0}
        annual = annual_returns.get(ticker, 8.0)
        years = days / 365.0
        return ((1 + annual/100) ** years - 1) * 100
    
    def _get_benchmark_series(self, ticker: str, start_date: date, end_date: date, dates: List[str]) -> List[float]:
        """Get benchmark series for given dates. Uses linear extrapolation for missing data."""
        try:
            from ..models import BenchmarkPrice
            
            # Get base price (price at or before start_date)
            base_price_rec = BenchmarkPrice.query.filter(
                BenchmarkPrice.ticker == ticker,
                BenchmarkPrice.date <= start_date
            ).order_by(BenchmarkPrice.date.desc()).first()
            
            if base_price_rec is None:
                base_price_rec = BenchmarkPrice.query.filter(
                    BenchmarkPrice.ticker == ticker,
                    BenchmarkPrice.date >= start_date
                ).order_by(BenchmarkPrice.date.asc()).first()
            
            if base_price_rec is None:
                # No data at all - use synthetic linear data
                approx_prices = {'SPY': 400.0, 'VT': 100.0, 'EEMS': 50.0}
                base_price_val = approx_prices.get(ticker, 100.0)
                
                series = []
                annual = {'SPY': 10.0, 'VT': 9.0, 'EEMS': 7.0}.get(ticker, 8.0)
                for d in dates:
                    current_date = datetime.fromisoformat(d).date() if isinstance(d, str) else d
                    days_from_start = (current_date - start_date).days
                    ret = (annual / 365.0) * days_from_start  # Linear, not compounded
                    series.append(round(ret, 2))
                return series
            
            base_price_val = float(base_price_rec.close_price)
            
            # Pre-load all available prices for efficiency
            all_prices = {}
            for bp in BenchmarkPrice.query.filter(
                BenchmarkPrice.ticker == ticker,
                BenchmarkPrice.date <= end_date
            ).all():
                all_prices[bp.date] = float(bp.close_price)
            
            if not all_prices:
                return [0.0] * len(dates)
            
            # Build series using most recent known price for each date
            series = []
            for d in dates:
                current_date = datetime.fromisoformat(d).date() if isinstance(d, str) else d
                
                if current_date in all_prices:
                    # Use actual price
                    price = all_prices[current_date]
                    ret = ((price - base_price_val) / base_price_val) * 100
                    series.append(round(ret, 2))
                else:
                    # Find most recent price before this date
                    most_recent_price = None
                    for price_date, price_val in sorted(all_prices.items()):
                        if price_date <= current_date:
                            most_recent_price = price_val
                        else:
                            break
                    
                    if most_recent_price is not None:
                        ret = ((most_recent_price - base_price_val) / base_price_val) * 100
                        series.append(round(ret, 2))
                    else:
                        # No data yet - use base price (0% return)
                        series.append(0.0)
            
            return series
            
        except Exception as e:
            logger.warning(f"Error getting benchmark series for {ticker}: {e}")
            return [0.0] * len(dates)


# Global progress tracker for SSE
current_progress = CalculationProgress()
_calculation_lock = False


def get_progress() -> CalculationProgress:
    """Get current calculation progress."""
    return current_progress


def reset_progress():
    """Reset progress tracker."""
    global current_progress
    current_progress = CalculationProgress()
    return current_progress


def is_calculation_running() -> bool:
    """Check if a calculation is currently running."""
    global _calculation_lock
    return _calculation_lock


def recalculate_all_unified(force: bool = False) -> Dict[str, Any]:
    """
    Convenience function to recalculate all data with unified calculator.
    
    Returns dict with all views data.
    """
    global _calculation_lock
    
    if _calculation_lock:
        raise RuntimeError("A recalculation is already in progress")
    
    try:
        _calculation_lock = True
        progress = reset_progress()
        progress.log("=== STARTING RECALCULATION ===")
        calculator = UnifiedDataCalculator(progress=progress)
        result = calculator.recalculate_all(force=force)
        return result
    finally:
        _calculation_lock = False
