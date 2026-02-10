"""
CSV Import module for Analysis Schedule with robust ticker resolution and progress tracking.

Features:
- Smart duplicate detection (skips existing, updates changed status)
- Real-time progress reporting via callback
- Robust ticker resolution with AI/search/Yahoo Finance fallback
- Automatic "Other" event detection
- Proper transaction handling (per-row commits with rollback recovery)
"""

import csv
import io
import logging
from datetime import datetime, date
from typing import List, Dict, Optional, Tuple, Callable
from sqlalchemy.exc import IntegrityError
from ..extensions import db
from ..models import User, Company, Analysis, CsvUpload, CompanyTickerMapping, analysis_analysts, AnalystMapping
from .ticker_resolver import resolve_ticker, is_other_event
from .email_normalization import normalize_name_for_email

logger = logging.getLogger(__name__)


class CsvImportProgress:
    """Track and report CSV import progress."""
    
    def __init__(self):
        self.total_rows = 0
        self.current_row = 0
        self.created = 0
        self.updated = 0
        self.skipped = 0
        self.errors = []
        self.current_company = None
        self.ticker_resolutions = {}  # Track ticker lookup results
    
    def to_dict(self) -> Dict:
        return {
            'total': self.total_rows,
            'current': self.current_row,
            'percent': int((self.current_row / self.total_rows * 100)) if self.total_rows > 0 else 0,
            'created': self.created,
            'updated': self.updated,
            'skipped': self.skipped,
            'errors': len(self.errors),
            'current_company': self.current_company,
            'ticker_resolutions': self.ticker_resolutions
        }


class CsvImporter:
    """Handle CSV import for Notion-exported analysis schedule."""
    
    EXPECTED_COLUMNS = [
        'Company',
        'Date',
        'Sector',
        'Analyst',
        'Opponent',
        'Comment',
        'Status',
        'Files & media'
    ]
    
    def __init__(self, csv_content: str, filename: str, uploaded_by: Optional[int] = None,
                 progress_callback: Optional[Callable[[Dict], None]] = None):
        """
        Args:
            csv_content: Raw CSV content as string.
            filename: Original filename.
            uploaded_by: User ID who uploaded the file.
            progress_callback: Function called with progress updates.
        """
        self.csv_content = csv_content
        self.filename = filename
        self.uploaded_by = uploaded_by
        self.progress_callback = progress_callback
        self.progress = CsvImportProgress()
        self.csv_upload = None
        # Cache for companies to avoid repeated lookups
        self._company_cache = {}
        self._mapping_cache = {}
    
    @staticmethod
    def _normalize_column_name(col: str) -> str:
        """Remove BOM and strip whitespace from column name."""
        if col.startswith('\ufeff'):
            col = col.lstrip('\ufeff')
        return col.strip()
    
    def _report_progress(self):
        """Call progress callback if set."""
        if self.progress_callback:
            try:
                self.progress_callback(self.progress.to_dict())
            except Exception as e:
                logger.warning(f"Progress callback failed: {e}")
    
    def process(self) -> Dict:
        """Parse CSV and insert/update database with progress tracking."""
        # Create upload record in a separate transaction
        try:
            self.csv_upload = CsvUpload(
                filename=self.filename,
                uploaded_by=self.uploaded_by,
                processed_at=None
            )
            db.session.add(self.csv_upload)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.exception("Failed to create upload record")
            return {
                'success': False,
                'error': f"Failed to create upload record: {str(e)}",
                'errors': []
            }
        
        try:
            reader = csv.DictReader(io.StringIO(self.csv_content))
            
            # Normalize column names
            column_map = {}
            normalized_fieldnames = []
            for col in (reader.fieldnames or []):
                normalized = self._normalize_column_name(col)
                column_map[normalized] = col
                normalized_fieldnames.append(normalized)
            
            # Validate header
            missing = set(self.EXPECTED_COLUMNS) - set(normalized_fieldnames)
            if missing:
                logger.info('Normalized fieldnames: %s', normalized_fieldnames)
                logger.info('Expected columns: %s', self.EXPECTED_COLUMNS)
                raise ValueError(f"Missing columns: {missing}")
            
            rows = []
            for raw_row in reader:
                norm_row = {}
                for norm, orig in column_map.items():
                    norm_row[norm] = raw_row.get(orig, '')
                rows.append(norm_row)
            
            self.progress.total_rows = len(rows)
            logger.info(f"CSV import starting: {len(rows)} rows to process")
            
            # Process each row independently
            for i, row in enumerate(rows, start=1):
                self.progress.current_row = i
                self.progress.current_company = row.get('Company', 'Unknown')
                
                # CRITICAL: Always rollback before processing a new row to ensure clean state
                try:
                    db.session.rollback()
                except Exception:
                    pass
                
                success = False
                try:
                    success = self._process_row(row, i)
                except IntegrityError as e:
                    # Database constraint violation - rollback and continue
                    try:
                        db.session.rollback()
                    except Exception:
                        pass
                    error_msg = f"Row {i} ({row.get('Company', 'Unknown')}): Duplicate or constraint error"
                    logger.warning(error_msg)
                    self.progress.errors.append(error_msg)
                except Exception as e:
                    # Any other error - rollback and continue
                    try:
                        db.session.rollback()
                    except Exception:
                        pass
                    error_msg = f"Row {i} ({row.get('Company', 'Unknown')}): {str(e)}"
                    logger.error(error_msg)
                    self.progress.errors.append(error_msg)
                
                # Report progress every 5 rows or on last row
                if i % 5 == 0 or i == len(rows):
                    self._report_progress()
            
            # Final rollback to ensure clean state before marking processed
            try:
                db.session.rollback()
            except Exception:
                pass
            
            # Mark upload as processed in a fresh transaction
            try:
                self.csv_upload.row_count = self.progress.total_rows
                self.csv_upload.processed_at = datetime.utcnow()
                db.session.add(self.csv_upload)
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                logger.exception("Failed to mark upload as processed")
            
            return {
                'success': True,
                'upload_id': self.csv_upload.id,
                'total': self.progress.total_rows,
                'created': self.progress.created,
                'updated': self.progress.updated,
                'skipped': self.progress.skipped,
                'errors': self.progress.errors,
                'ticker_resolutions': self.progress.ticker_resolutions
            }
            
        except Exception as e:
            try:
                db.session.rollback()
            except Exception:
                pass
            logger.exception("CSV import failed")
            return {
                'success': False,
                'error': str(e),
                'errors': self.progress.errors
            }
    
    def _process_row(self, row: Dict, row_num: int) -> bool:
        """Process a single CSV row - create or update analysis. Returns True on success."""
        company_name = row['Company'].strip()
        if not company_name:
            self.progress.skipped += 1
            return True
        
        # Parse date
        analysis_date = self._parse_date(row['Date'])
        if not analysis_date:
            raise ValueError(f"Invalid date: {row['Date']}")
        
        # Get or create company with ticker resolution
        company = self._get_or_create_company(company_name, row.get('Sector', '').strip())
        
        # Determine status
        status = self._parse_status(row.get('Status', ''))
        
        # Check if analysis already exists (same company + date)
        existing = Analysis.query.filter_by(
            company_id=company.id,
            analysis_date=analysis_date
        ).first()
        
        if existing:
            # Update existing analysis if status changed
            if existing.status != status:
                existing.status = status
                existing.comment = row.get('Comment', '').strip()
                existing.files_media = row.get('Files & media', '').strip()
                existing.updated_at = datetime.utcnow()
                db.session.flush()
                self.progress.updated += 1
                logger.info(f"Updated analysis: {company_name} ({status})")
            else:
                self.progress.skipped += 1
            
            # Update analyst/opponent assignments even if status unchanged
            self._assign_analysts(existing, row.get('Analyst', ''), row.get('Opponent', ''))
            db.session.commit()
            return True
        
        # Create new analysis
        analysis = Analysis(
            company_id=company.id,
            analysis_date=analysis_date,
            status=status,
            comment=row.get('Comment', '').strip(),
            files_media= row.get('Files & media', '').strip(),
            csv_upload_id=self.csv_upload.id
        )
        db.session.add(analysis)
        db.session.flush()  # Get ID without committing
        
        # Assign analysts and opponents
        self._assign_analysts(analysis, row.get('Analyst', ''), row.get('Opponent', ''))
        
        # Commit this row
        db.session.commit()
        
        self.progress.created += 1
        logger.info(f"Created analysis: {company_name} ({status})")
        return True
    
    def _get_or_create_company(self, name: str, sector: str) -> Company:
        """Get existing company or create new with ticker resolution."""
        # Check cache first
        if name in self._company_cache:
            company = self._company_cache[name]
            # Update sector if provided and company exists
            if sector and not company.sector:
                company.sector = sector
                db.session.flush()
            return company
        
        # Check for existing company in database
        company = Company.query.filter_by(name=name).first()
        if company:
            # Update sector if provided
            if sector and not company.sector:
                company.sector = sector
                db.session.flush()
            self._company_cache[name] = company
            return company
        
        # Create new company
        company = Company(name=name, sector=sector or None)
        db.session.add(company)
        db.session.flush()  # Get ID
        
        # Try to resolve ticker
        self._resolve_company_ticker(company)
        
        self._company_cache[name] = company
        return company
    
    def _resolve_company_ticker(self, company: Company):
        """Resolve ticker for a company using multiple methods."""
        # Check cache first
        if company.name in self._mapping_cache:
            mapping = self._mapping_cache[company.name]
            self._apply_mapping_to_company(company, mapping)
            return
        
        # Check if mapping already exists in database
        existing_mapping = CompanyTickerMapping.query.filter_by(company_name=company.name).first()
        if existing_mapping:
            self._mapping_cache[company.name] = existing_mapping
            self._apply_mapping_to_company(company, existing_mapping)
            return
        
        # Check if it's an "Other" event first
        if is_other_event(company.name):
            # Mark as Other in ticker mapping
            mapping = CompanyTickerMapping(
                company_name=company.name,
                ticker_symbol=None,
                is_other_event=True,
                source='auto_detected'
            )
            db.session.add(mapping)
            db.session.flush()
            self._mapping_cache[company.name] = mapping
            self.progress.ticker_resolutions[company.name] = {'status': 'other', 'ticker': None}
            logger.info(f"Company '{company.name}' auto-detected as Other event")
            return
        
        # Try to resolve ticker
        ticker, is_other, source = resolve_ticker(company.name)
        
        try:
            if is_other:
                company.ticker_symbol = None
                mapping = CompanyTickerMapping(
                    company_name=company.name,
                    ticker_symbol=None,
                    is_other_event=True,
                    source=source
                )
                db.session.add(mapping)
                db.session.flush()
                self._mapping_cache[company.name] = mapping
                self.progress.ticker_resolutions[company.name] = {'status': 'other', 'ticker': None}
                logger.info(f"Company '{company.name}' resolved as Other")
            elif ticker:
                company.ticker_symbol = ticker
                mapping = CompanyTickerMapping(
                    company_name=company.name,
                    ticker_symbol=ticker,
                    is_other_event=False,
                    source=source
                )
                db.session.add(mapping)
                db.session.flush()
                self._mapping_cache[company.name] = mapping
                self.progress.ticker_resolutions[company.name] = {
                    'status': 'resolved',
                    'ticker': ticker,
                    'source': source
                }
                logger.info(f"Company '{company.name}' resolved to ticker {ticker} ({source})")
            else:
                # No ticker found - create pending mapping
                mapping = CompanyTickerMapping(
                    company_name=company.name,
                    ticker_symbol=None,
                    is_other_event=False,
                    source='pending'
                )
                db.session.add(mapping)
                db.session.flush()
                self._mapping_cache[company.name] = mapping
                self.progress.ticker_resolutions[company.name] = {
                    'status': 'pending',
                    'ticker': None
                }
                logger.info(f"Company '{company.name}' ticker resolution pending")
        except IntegrityError:
            # Another process may have created the mapping - rollback and retry lookup
            db.session.rollback()
            existing_mapping = CompanyTickerMapping.query.filter_by(company_name=company.name).first()
            if existing_mapping:
                self._mapping_cache[company.name] = existing_mapping
                self._apply_mapping_to_company(company, existing_mapping)
    
    def _apply_mapping_to_company(self, company: Company, mapping: CompanyTickerMapping):
        """Apply an existing ticker mapping to a company."""
        if mapping.is_other_event:
            company.ticker_symbol = None
            self.progress.ticker_resolutions[company.name] = {'status': 'other', 'ticker': None}
            logger.info(f"Company '{company.name}' using existing Other mapping")
        elif mapping.ticker_symbol:
            company.ticker_symbol = mapping.ticker_symbol
            self.progress.ticker_resolutions[company.name] = {
                'status': 'resolved',
                'ticker': mapping.ticker_symbol,
                'source': mapping.source or 'cached'
            }
            logger.info(f"Company '{company.name}' using cached ticker {mapping.ticker_symbol}")
        else:
            self.progress.ticker_resolutions[company.name] = {
                'status': 'pending',
                'ticker': None
            }
            logger.info(f"Company '{company.name}' has pending mapping")
    
    def _assign_analysts(self, analysis: Analysis, analyst_str: str, opponent_str: str):
        """Assign analysts and opponents to an analysis."""
        # Clear existing assignments first
        db.session.execute(
            analysis_analysts.delete().where(
                analysis_analysts.c.analysis_id == analysis.id
            )
        )
        
        # Parse and assign analysts
        analysts = self._parse_people(analyst_str)
        for name in analysts:
            user = self._get_or_create_analyst(name)
            if user:
                db.session.execute(
                    analysis_analysts.insert().values(
                        analysis_id=analysis.id,
                        user_id=user.id,
                        role='analyst'
                    )
                )
        
        # Parse and assign opponents
        opponents = self._parse_people(opponent_str)
        for name in opponents:
            user = self._get_or_create_analyst(name)
            if user:
                db.session.execute(
                    analysis_analysts.insert().values(
                        analysis_id=analysis.id,
                        user_id=user.id,
                        role='opponent'
                    )
                )
        
        db.session.flush()
    
    def _get_or_create_analyst(self, name: str) -> Optional[User]:
        """Get existing user or create inactive placeholder."""
        if not name or name.strip() in ['', '-', 'TBD', 'N/A']:
            return None
        
        name = name.strip()
        normalized_name = normalize_name_for_email(name)
        email = f"{normalized_name}@klubinvestoru.com"
        
        # Check for existing user
        user = User.query.filter_by(email=email).first()
        if user:
            return user
        
        # Check for existing mapping
        mapping = AnalystMapping.query.filter_by(analyst_name=name).first()
        if mapping and mapping.user_id:
            return User.query.get(mapping.user_id)
        
        # Create placeholder user (inactive until they register)
        user = User(
            email=email,
            full_name=name,
            is_active=False,  # Will activate when they register
            email_verified=False
        )
        db.session.add(user)
        db.session.flush()
        
        # Create mapping
        mapping = AnalystMapping(analyst_name=name, user_id=user.id)
        db.session.add(mapping)
        db.session.flush()
        
        return user
    
    def _parse_date(self, date_str: str) -> Optional[date]:
        """Parse date from various formats."""
        if not date_str:
            return None
        
        date_str = date_str.strip()
        formats = [
            '%Y-%m-%d',
            '%d/%m/%Y',
            '%m/%d/%Y',
            '%d.%m.%Y',
            '%Y/%m/%d',
            '%d-%m-%Y'
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        
        # Try to parse with dateutil if available
        try:
            from dateutil import parser
            return parser.parse(date_str).date()
        except:
            pass
        
        return None
    
    def _parse_status(self, status_str: str) -> str:
        """Parse and normalize status string."""
        if not status_str:
            return 'To Be Announced'
        
        status_map = {
            'on watchlist': 'On Watchlist',
            'watchlist': 'On Watchlist',
            'approved': 'On Watchlist',
            'refused': 'Refused',
            'rejected': 'Refused',
            'neutral': 'Neutral',
            'tba': 'To Be Announced',
            'tbd': 'To Be Announced',
            'to be announced': 'To Be Announced',
            'to-be-analyzed': 'To Be Announced',
            'to be analyzed': 'To Be Announced',
            'other': 'Other',
            'event': 'Other',
            'workshop': 'Other',
            'learning': 'Other',
            'na': 'Other',
            'n/a': 'Other'
        }
        
        normalized = status_str.strip().lower()
        return status_map.get(normalized, status_str.strip())
    
    def _parse_people(self, people_str: str) -> List[str]:
        """Parse comma or newline separated list of people."""
        if not people_str:
            return []
        
        # Split by comma or newline
        names = []
        for sep in [',', '\n', ';']:
            if sep in people_str:
                names = people_str.split(sep)
                break
        else:
            names = [people_str]
        
        # Clean up names
        return [name.strip() for name in names if name.strip() and name.strip() not in ['', '-', 'TBD', 'N/A']]
