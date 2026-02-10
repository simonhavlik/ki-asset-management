"""
Performance calculation utilities for the Analyst Performance Tracker.

This module provides comprehensive performance calculation capabilities including:
- Individual analysis return calculations
- Analyst portfolio performance aggregation
- Benchmark comparisons (S&P 500, FTSE All-World)
- Cumulative series generation for charting

All returns are calculated as percentage returns and can be annualized
for holding periods longer than one year.
"""

import logging
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional, Tuple
from sqlalchemy import func
from ..extensions import db
from ..models import Analysis, PerformanceCalculation, Company, CompanyTickerMapping, StockPrice, User, analysis_analysts
from .yahooquery_helper import get_price_on_date, get_latest_price, update_prices_for_company, fetch_benchmark_prices

logger = logging.getLogger(__name__)


class PerformanceCalculator:
    """
    Calculate performance metrics for approved analyses.
    
    This class provides methods to calculate individual analysis returns,
    aggregate analyst performance, and generate benchmark comparisons.
    
    Attributes:
        calculation_date: The date for which to calculate performance (defaults to today)
        STATUS_CATEGORIES: Mapping of filter categories to status lists
    """
    
    # Mapping of filter categories to status lists
    STATUS_CATEGORIES = {
        'approved_only': ['On Watchlist'],
        'neutral_approved': ['On Watchlist', 'Neutral'],
        'all_stock': ['On Watchlist', 'Neutral', 'Refused'],
    }
    
    def _statuses_for_filter(self, status_filter):
        """
        Convert a status filter to a list of statuses.
        
        Accepts either a single status string or a category key.
        Returns a list of status strings.
        
        Args:
            status_filter: A status string, category key, or list of statuses
            
        Returns:
            List of status strings
        """
        if isinstance(status_filter, list):
            return status_filter
        if status_filter in self.STATUS_CATEGORIES:
            return self.STATUS_CATEGORIES[status_filter]
        # Assume it's a single status string
        return [status_filter]
    
    def _is_other_event(self, company):
        """
        Return True if the company is marked as an other (non‑stock) event.
        
        Args:
            company: Company model instance
            
        Returns:
            True if company is marked as other event, False otherwise
        """
        mapping = CompanyTickerMapping.query.filter_by(
            company_name=company.name,
            is_other_event=True
        ).first()
        return mapping is not None

    def _annualize_return(self, raw_return_pct, start_date, end_date):
        """
        Convert a raw return percentage to annualized equivalent if holding period > 1 year.
        
        Args:
            raw_return_pct: float, percentage return (e.g., 10 for 10%)
            start_date: datetime.date object for purchase/analysis date
            end_date: datetime.date object for current/calculation date
            
        Returns:
            float: Annualized percentage (or raw_return_pct if holding period <= 365 days)
        """
        days = (end_date - start_date).days
        if days <= 365:
            return float(raw_return_pct)
        # Avoid division by zero
        if days == 0:
            return float(raw_return_pct)
        # If raw return is -100% or less, cannot annualize (loss of entire investment)
        if raw_return_pct <= -100:
            return -100.0
        try:
            total_return = 1.0 + raw_return_pct / 100.0
            years = days / 365.0
            annualized_total = total_return ** (1.0 / years)
            annualized_pct = (annualized_total - 1.0) * 100.0
            return annualized_pct
        except (ValueError, ZeroDivisionError):
            # Fallback to raw return
            return float(raw_return_pct)

    def __init__(self, calculation_date: Optional[date] = None):
        """
        Initialize the PerformanceCalculator.
        
        Args:
            calculation_date: The date for which to calculate performance.
                            Defaults to today if not provided.
        """
        self.calculation_date = calculation_date or date.today()
    
    def recalculate_all(self) -> Dict:
        """
        Recalculate performance for all approved analyses.
        
        This method iterates through all analyses with stock-related statuses
        and calculates current performance based on latest prices.
        
        Returns:
            Dict containing statistics:
                - total_analyses: Total number of analyses processed
                - calculated: Number successfully calculated
                - skipped_no_ticker: Number skipped due to missing ticker
                - skipped_no_price: Number skipped due to missing price data
                - skipped_other_event: Number skipped as non-stock events
                - errors: List of error messages
        """
        stats = {
            'total_analyses': 0,
            'calculated': 0,
            'skipped_no_ticker': 0,
            'skipped_no_price': 0,
            'skipped_other_event': 0,
            'errors': []
        }
        
        # Get all stock analyses (approved, neutral, refused)
        stock_statuses = self._statuses_for_filter('all_stock')
        analyses = Analysis.query.filter(Analysis.status.in_(stock_statuses)).all()
        stats['total_analyses'] = len(analyses)
        
        for analysis in analyses:
            try:
                success = self.calculate_for_analysis(analysis)
                if success:
                    stats['calculated'] += 1
                else:
                    # Determine reason
                    company = Company.query.get(analysis.company_id)
                    if not company:
                        stats['skipped_no_ticker'] += 1
                    elif self._is_other_event(company):
                        # Remove any existing performance calculations for this analysis
                        PerformanceCalculation.query.filter_by(analysis_id=analysis.id).delete()
                        db.session.commit()
                        stats['skipped_other_event'] += 1
                    elif not company.ticker_symbol:
                        stats['skipped_no_ticker'] += 1
                    else:
                        stats['skipped_no_price'] += 1
            except Exception as e:
                stats['errors'].append(f"Analysis {analysis.id}: {str(e)}")
                logger.exception(f"Error calculating performance for analysis {analysis.id}")
        
        logger.info(f"Performance calculation completed: {stats}")
        return stats
    
    def calculate_for_analysis(self, analysis: Analysis) -> bool:
        """
        Calculate performance for a single analysis and store result.
        
        Args:
            analysis: Analysis model instance
            
        Returns:
            True if calculation succeeded, False otherwise
        """
        company = Company.query.get(analysis.company_id)
        if not company:
            logger.warning(f"Company {analysis.company_id} not found, skipping")
            return False
        if self._is_other_event(company):
            logger.warning(f"Company {company.name} marked as other event, skipping")
            return False
        if not company.ticker_symbol:
            logger.warning(f"Company {company.id} missing ticker, skipping")
            return False
        
        # Ensure we have price data
        update_prices_for_company(company)
        
        price_at_analysis = get_price_on_date(company.id, analysis.analysis_date)
        price_current = get_latest_price(company.id)
        
        if price_at_analysis is None or price_current is None:
            logger.warning(f"Missing price data for company {company.name}")
            return False
        
        # Compute return percentage
        return_pct = ((price_current - price_at_analysis) / price_at_analysis) * 100
        
        # Store or update performance calculation
        existing = PerformanceCalculation.query.filter_by(
            analysis_id=analysis.id,
            calculation_date=self.calculation_date
        ).first()
        
        if existing:
            existing.price_at_analysis = price_at_analysis
            existing.price_current = price_current
            existing.return_pct = return_pct
            existing.calculated_at = datetime.utcnow()
        else:
            pc = PerformanceCalculation(
                analysis_id=analysis.id,
                calculation_date=self.calculation_date,
                price_at_analysis=price_at_analysis,
                price_current=price_current,
                return_pct=return_pct
            )
            db.session.add(pc)
        
        db.session.commit()
        return True
    
    def get_analyst_performance(self, analyst_id: int, status_filter: str = 'approved_only', annualized: bool = False) -> Dict:
        """
        Compute aggregated performance metrics for a specific analyst.
        
        Args:
            analyst_id: The ID of the analyst user
            status_filter: Filter by status category ('approved_only', 'neutral_approved', 'all_stock')
            annualized: If True, annualize returns for holdings > 1 year
            
        Returns:
            Dict with performance metrics:
                - num_analyses: Number of analyses
                - avg_return: Average return percentage
                - median_return: Median return percentage
                - win_rate: Percentage of positive returns
                - best_return: Highest return
                - worst_return: Lowest return
        """
        status_list = self._statuses_for_filter(status_filter)
        today = date.today()
        
        # Build query for analyses where the user is an analyst (role 'analyst')
        # Exclude future analyses (analysis_date > today) - these haven't happened yet
        query = db.session.query(Analysis).join(
            analysis_analysts, Analysis.id == analysis_analysts.c.analysis_id
        ).filter(
            analysis_analysts.c.user_id == analyst_id,
            analysis_analysts.c.role == 'analyst',
            Analysis.status.in_(status_list),
            Analysis.analysis_date <= today  # Only past/present analyses
        )
        
        analyses = query.all()
        
        # Get latest performance calculations for each analysis
        # Filter out: 1) Other events, 2) Analyses without price data
        returns = []
        for analysis in analyses:
            # Skip "Other" events (non-stock analyses)
            if analysis.company and self._is_other_event(analysis.company):
                continue
            
            pc = PerformanceCalculation.query.filter_by(
                analysis_id=analysis.id
            ).order_by(PerformanceCalculation.calculation_date.desc()).first()
            
            # Only include if there's a valid performance calculation
            if pc and pc.return_pct is not None:
                if annualized:
                    ret = self._annualize_return(float(pc.return_pct),
                                                 analysis.analysis_date,
                                                 pc.calculation_date)
                else:
                    ret = float(pc.return_pct)
                returns.append(ret)
        
        if not returns:
            return {
                'num_analyses': 0,
                'avg_return': None,
                'median_return': None,
                'win_rate': None,
                'best_return': None,
                'worst_return': None
            }
    
        returns_sorted = sorted(returns)
        avg = sum(returns) / len(returns)
        median = returns_sorted[len(returns) // 2] if len(returns) % 2 == 1 else \
                 (returns_sorted[len(returns) // 2 - 1] + returns_sorted[len(returns) // 2]) / 2
        wins = sum(1 for r in returns if r > 0)
        win_rate = wins / len(returns) * 100
        
        return {
            'num_analyses': len(returns),
            'avg_return': round(avg, 2),
            'median_return': round(median, 2),
            'win_rate': round(win_rate, 2),
            'best_return': round(max(returns), 2),
            'worst_return': round(min(returns), 2)
        }
    
    def get_all_analysts_performance(self, status_filter: str = 'approved_only', annualized: bool = False) -> List[Dict]:
        """
        Compute performance for all analysts.
        
        Args:
            status_filter: Filter by status category
            annualized: If True, annualize returns for holdings > 1 year
            
        Returns:
            List of dicts containing analyst performance metrics,
            sorted by average return (descending)
        """
        # Get all users who have at least one analysis as analyst
        analysts = db.session.query(User).join(
            analysis_analysts, User.id == analysis_analysts.c.user_id
        ).filter(
            analysis_analysts.c.role == 'analyst'
        ).distinct().all()
        
        results = []
        for analyst in analysts:
            perf = self.get_analyst_performance(analyst.id, status_filter, annualized)
            results.append({
                'analyst_id': analyst.id,
                'analyst_name': analyst.full_name or analyst.email,
                **perf
            })
        # Sort by avg_return descending (ignore None)
        results.sort(key=lambda x: x['avg_return'] if x['avg_return'] is not None else -float('inf'), reverse=True)
        return results

    def _get_benchmark_series(self, ticker: str, start_date: date, end_date: date, dates: List[str]) -> List[float]:
        """
        Compute cumulative return series for a benchmark ticker aligned with given dates.
        
        The series is normalized to start at 0% on the first date, making it directly
        comparable to analyst performance charts.
        
        Args:
            ticker: Benchmark ticker symbol (e.g., 'SPY', 'VT')
            start_date: Start date for data
            end_date: End date for data
            dates: List of date strings (YYYY-MM-DD) to align with
            
        Returns:
            List of cumulative return percentages aligned with dates
        """
        try:
            df = fetch_benchmark_prices(ticker, start_date, end_date)
            if df.empty:
                return []
            # Convert df to dict date->close
            # Handle both datetime and date objects from yahooquery
            def get_date_key(d):
                return d.date() if hasattr(d, 'date') else d
            price_map = {get_date_key(row['Date']): row['close_price'] for _, row in df.iterrows()}
            
            # Get start price - use first available price on or after start_date
            start_price = None
            for d in sorted(price_map.keys()):
                if d >= start_date:
                    start_price = price_map[d]
                    break
            # If no price on or after start_date, use earliest available
            if start_price is None and price_map:
                start_price = price_map[min(price_map.keys())]
            
            if start_price is None:
                return []
            
            series = []
            for date_str in dates:
                target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                # Find price on or before target_date
                price = None
                for d in sorted(price_map.keys()):
                    if d <= target_date:
                        price = price_map[d]
                    else:
                        break
                if price is None:
                    series.append(0.0)
                else:
                    ret = (price - start_price) / start_price * 100
                    series.append(round(ret, 2))
            return series
        except Exception as e:
            logger.warning(f"Failed to fetch benchmark {ticker}: {e}")
            return []

    def get_cumulative_series(self, analyst_id: int, status_filter: str = 'approved_only', annualized: bool = False) -> Dict:
        """
        Return cumulative performance series for analyst, club average, and benchmarks.
        
        ALL series are normalized to start at 0% on the first date, making them
        directly comparable on the same chart. This is crucial for understanding
        whether an analyst is outperforming or underperforming the benchmarks.
        
        Returns a dict with keys:
        - dates: list of date strings (YYYY-MM-DD)
        - analyst_series: list of cumulative returns (%) for analyst, starting at 0
        - club_series: list of cumulative average returns (%) for club, starting at 0
        - spy_series: list of cumulative returns for SPY benchmark, starting at 0
        - ftse_series: list of cumulative returns for FTSE All World benchmark, starting at 0
        
        Args:
            analyst_id: The ID of the analyst to get series for
            status_filter: Filter by status category
            annualized: If True, annualize returns for holdings > 1 year
            
        Returns:
            Dict containing aligned date series for all metrics
        """
        status_list = self._statuses_for_filter(status_filter)
        
        # Get the earliest date across all analyses for this analyst
        # This will be our normalization point (all series start at 0 here)
        earliest_analysis = db.session.query(Analysis).join(
            analysis_analysts, Analysis.id == analysis_analysts.c.analysis_id
        ).filter(
            analysis_analysts.c.user_id == analyst_id,
            analysis_analysts.c.role == 'analyst',
            Analysis.status.in_(status_list)
        ).order_by(Analysis.analysis_date.asc()).first()
        
        if earliest_analysis:
            normalization_date = earliest_analysis.analysis_date
        else:
            normalization_date = date.today() - timedelta(days=365)
        
        # 1. Analyst series
        analyst_analyses = db.session.query(Analysis, PerformanceCalculation).join(
            PerformanceCalculation, Analysis.id == PerformanceCalculation.analysis_id
        ).join(
            analysis_analysts, Analysis.id == analysis_analysts.c.analysis_id
        ).filter(
            analysis_analysts.c.user_id == analyst_id,
            analysis_analysts.c.role == 'analyst',
            Analysis.status.in_(status_list)
        ).all()
        
        analyst_data = []
        for analysis, perf in analyst_analyses:
            ret = float(perf.return_pct)
            if annualized:
                ret = self._annualize_return(ret, analysis.analysis_date, perf.calculation_date)
            analyst_data.append({
                'date': analysis.analysis_date,
                'return': ret
            })
        analyst_data.sort(key=lambda x: x['date'])
        
        # Build cumulative series showing RUNNING AVERAGE of returns
        # This represents an equal-weighted portfolio of all picks up to each date
        dates = []
        analyst_series = []
        running_total = 0.0
        count = 0
        
        for item in analyst_data:
            dates.append(item['date'].isoformat())
            running_total += item['return']
            count += 1
            # Show average return of all positions so far
            avg_return = running_total / count
            analyst_series.append(round(avg_return, 2))
        
        # 2. Club series - align to the same dates
        club_analyses = db.session.query(Analysis, PerformanceCalculation).join(
            PerformanceCalculation, Analysis.id == PerformanceCalculation.analysis_id
        ).join(
            analysis_analysts, Analysis.id == analysis_analysts.c.analysis_id
        ).filter(
            analysis_analysts.c.role == 'analyst',
            Analysis.status.in_(status_list)
        ).all()
        
        club_data = []
        for analysis, perf in club_analyses:
            ret = float(perf.return_pct)
            if annualized:
                ret = self._annualize_return(ret, analysis.analysis_date, perf.calculation_date)
            club_data.append({
                'date': analysis.analysis_date,
                'return': ret
            })
        club_data.sort(key=lambda x: x['date'])
        
        # Build club cumulative series aligned to analyst dates
        # This shows running average of ALL club picks up to each date
        club_series = []
        club_running_total = 0.0
        club_count = 0
        club_index = 0
        
        for date_str in dates:
            current_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            # Add all club returns up to this date
            while club_index < len(club_data) and club_data[club_index]['date'] <= current_date:
                club_running_total += club_data[club_index]['return']
                club_count += 1
                club_index += 1
            # Show average return
            if club_count > 0:
                club_series.append(round(club_running_total / club_count, 2))
            else:
                club_series.append(0.0)
        
        # 3. Benchmark series (SPY, FTSE)
        # These are already normalized in _get_benchmark_series to start at 0
        if dates:
            end_date = date.today()
            spy_series = self._get_benchmark_series('SPY', normalization_date, end_date, dates)
            ftse_series = self._get_benchmark_series('VT', normalization_date, end_date, dates)
        else:
            spy_series = []
            ftse_series = []
        
        return {
            'dates': dates,
            'analyst_series': analyst_series,
            'club_series': club_series,
            'spy_series': spy_series,
            'ftse_series': ftse_series,
            'normalization_date': normalization_date.isoformat()
        }

    def get_portfolio_performance(self, analysis_ids: List[int]) -> Dict:
        """
        Calculate performance for a portfolio of analyses.
        
        This is used by the Board page to calculate the performance of
        Board-approved portfolio positions.
        
        Args:
            analysis_ids: List of analysis IDs in the portfolio
            
        Returns:
            Dict with portfolio metrics:
                - total_return: Weighted average return
                - annualized_return: Annualized weighted return
                - num_positions: Number of positions
                - start_date: Earliest purchase date
                - benchmark_spy: SPY return over same period
                - benchmark_ftse: FTSE return over same period
        """
        if not analysis_ids:
            return {
                'total_return': None,
                'annualized_return': None,
                'num_positions': 0,
                'start_date': None,
                'benchmark_spy': None,
                'benchmark_ftse': None
            }
        
        analyses = db.session.query(Analysis).filter(
            Analysis.id.in_(analysis_ids)
        ).all()
        
        total_return = 0.0
        annualized_return = 0.0
        count = 0
        earliest_date = None
        
        for analysis in analyses:
            # Use purchase_date if set, otherwise analysis_date
            start_date = analysis.purchase_date or analysis.analysis_date
            
            if earliest_date is None or start_date < earliest_date:
                earliest_date = start_date
            
            perf = PerformanceCalculation.query.filter_by(
                analysis_id=analysis.id
            ).order_by(PerformanceCalculation.calculation_date.desc()).first()
            
            if perf:
                ret = float(perf.return_pct)
                total_return += ret
                annualized = self._annualize_return(ret, start_date, perf.calculation_date)
                annualized_return += annualized
                count += 1
        
        if count == 0:
            return {
                'total_return': None,
                'annualized_return': None,
                'num_positions': 0,
                'start_date': earliest_date.isoformat() if earliest_date else None,
                'benchmark_spy': None,
                'benchmark_ftse': None
            }
        
        avg_return = total_return / count
        avg_annualized = annualized_return / count
        
        # Get benchmark returns for comparison
        end_date = self.calculation_date
        spy_series = self._get_benchmark_series('SPY', earliest_date, end_date, [earliest_date.isoformat(), end_date.isoformat()])
        ftse_series = self._get_benchmark_series('VT', earliest_date, end_date, [earliest_date.isoformat(), end_date.isoformat()])
        
        return {
            'total_return': round(avg_return, 2),
            'annualized_return': round(avg_annualized, 2),
            'num_positions': count,
            'start_date': earliest_date.isoformat() if earliest_date else None,
            'benchmark_spy': spy_series[-1] if spy_series else None,
            'benchmark_ftse': ftse_series[-1] if ftse_series else None
        }

    def get_portfolio_cumulative_series(self, analysis_ids: List[int]) -> Dict:
        """
        Get cumulative performance series for a portfolio with benchmark comparison.
        
        Calculates the actual portfolio performance as an equal-weighted portfolio
        where each stock contributes from its entry date (analysis_date or purchase_date).
        
        The portfolio line shows:
        - From first stock entry: That stock's performance
        - From second stock entry: Average of both stocks' performances  
        - From third stock entry: Average of all three, etc.
        
        Args:
            analysis_ids: List of analysis IDs in the portfolio
            
        Returns:
            Dict with keys:
                - dates: List of date strings
                - portfolio_series: Cumulative portfolio returns
                - spy_series: Cumulative SPY returns
                - ftse_series: Cumulative FTSE returns
                - start_date: Portfolio inception date
        """
        if not analysis_ids:
            return {
                'dates': [],
                'portfolio_series': [],
                'spy_series': [],
                'ftse_series': [],
                'start_date': None
            }
        
        # Get all analyses with their entry dates
        analyses = Analysis.query.filter(Analysis.id.in_(analysis_ids)).all()
        
        if not analyses:
            return {
                'dates': [],
                'portfolio_series': [],
                'spy_series': [],
                'ftse_series': [],
                'start_date': None
            }
        
        # Build list of entries with their start dates
        analysis_entries = []
        for analysis in analyses:
            start_date = analysis.purchase_date or analysis.analysis_date
            analysis_entries.append({
                'analysis': analysis,
                'start_date': start_date
            })
        
        # Sort by entry date
        analysis_entries.sort(key=lambda x: x['start_date'])
        earliest_date = analysis_entries[0]['start_date']
        end_date = self.calculation_date
        
        # Generate monthly dates from start to end
        dates = []
        current = earliest_date
        while current <= end_date:
            dates.append(current.isoformat())
            # Move to next month
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)
        
        if not dates:
            dates = [earliest_date.isoformat(), end_date.isoformat()]
        
        # Calculate portfolio value at each date
        portfolio_series = []
        
        for date_str in dates:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            
            # Get all stocks that have entered by this date
            active_entries = [e for e in analysis_entries if e['start_date'] <= target_date]
            
            if not active_entries:
                portfolio_series.append(0.0)
                continue
            
            # Calculate equal-weighted average return of all active stocks
            total_ret = 0.0
            count = 0
            
            for entry in active_entries:
                analysis = entry['analysis']
                start_date = entry['start_date']
                company = Company.query.get(analysis.company_id)
                
                if not company or not company.ticker_symbol:
                    continue
                
                # Get price at entry date
                entry_price = get_price_on_date(company.id, start_date)
                # Get price at current chart date
                current_price = get_price_on_date(company.id, target_date)
                
                if entry_price and current_price and entry_price > 0:
                    ret = ((current_price - entry_price) / entry_price) * 100
                    total_ret += ret
                    count += 1
            
            if count > 0:
                avg_return = total_ret / count
                portfolio_series.append(round(avg_return, 2))
            else:
                portfolio_series.append(0.0)
        
        # Get benchmark series (normalized to start at 0 on earliest_date)
        spy_series = self._get_benchmark_series('SPY', earliest_date, end_date, dates)
        ftse_series = self._get_benchmark_series('VT', earliest_date, end_date, dates)
        
        return {
            'dates': dates,
            'portfolio_series': portfolio_series,
            'spy_series': spy_series,
            'ftse_series': ftse_series,
            'start_date': earliest_date.isoformat()
        }
