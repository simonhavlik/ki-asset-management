from datetime import datetime, date, timedelta
from typing import Dict
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from .extensions import db

# Association table for many-to-many between analyses and analysts (including opponents)
analysis_analysts = db.Table(
    'analysis_analysts',
    db.Column('analysis_id', db.Integer, db.ForeignKey('analyses.id', ondelete='CASCADE'), primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    db.Column('role', db.String(20), default='analyst', primary_key=True),  # 'analyst' or 'opponent'
    db.UniqueConstraint('analysis_id', 'user_id', 'role', name='unique_analysis_user_role')
)

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=True)  # null for inactive accounts
    full_name = db.Column(db.String(255))
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)
    email_verified = db.Column(db.Boolean, default=False)

    # Relationships
    analyses = db.relationship('Analysis', secondary=analysis_analysts,
                               backref=db.backref('analysts', lazy='dynamic'))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    def get_id(self):
        return str(self.id)

    def __repr__(self):
        return f'<User {self.email}>'

class Company(db.Model):
    __tablename__ = 'companies'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    ticker_symbol = db.Column(db.String(50), nullable=True)
    sector = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    analyses = db.relationship('Analysis', backref='company', lazy='dynamic')
    stock_prices = db.relationship('StockPrice', backref='company', lazy='dynamic')

    def __repr__(self):
        return f'<Company {self.name} ({self.ticker_symbol})>'


class CompanyTickerMapping(db.Model):
    __tablename__ = 'company_ticker_maps'
    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(255), unique=True, nullable=False)
    ticker_symbol = db.Column(db.String(50), nullable=True)
    source = db.Column(db.String(50))  # 'manual', 'deepseek', 'yfinance'
    is_other_event = db.Column(db.Boolean, default=False)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<CompanyTickerMapping {self.company_name} -> {self.ticker_symbol}>'

class Analysis(db.Model):
    __tablename__ = 'analyses'
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    analysis_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(50), nullable=False)  # 'On Watchlist', 'Refused', etc.
    comment = db.Column(db.Text)
    files_media = db.Column(db.Text)  # comma-separated file paths
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    csv_upload_id = db.Column(db.Integer, db.ForeignKey('csv_uploads.id'), nullable=True)
    purchase_date = db.Column(db.Date, nullable=True)
    is_in_portfolio = db.Column(db.Boolean, default=False)

    # Generated column for approval (SQLite does not support generated columns directly,
    # we'll compute it as a property)
    @property
    def is_approved(self):
        return self.status == 'On Watchlist'

    @property
    def analysts_list(self):
        """Return users with role 'analyst' for this analysis."""
        from .models import User
        return User.query.join(analysis_analysts).filter(
            analysis_analysts.c.analysis_id == self.id,
            analysis_analysts.c.role == 'analyst'
        ).all()

    @property
    def opponents_list(self):
        """Return users with role 'opponent' for this analysis."""
        from .models import User
        return User.query.join(analysis_analysts).filter(
            analysis_analysts.c.analysis_id == self.id,
            analysis_analysts.c.role == 'opponent'
        ).all()

    def __repr__(self):
        return f'<Analysis {self.company_id} {self.analysis_date}>'

class StockPrice(db.Model):
    __tablename__ = 'stock_prices'
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    close_price = db.Column(db.Numeric(10, 2), nullable=False)
    volume = db.Column(db.BigInteger, nullable=True)
    fetched_at = db.Column(db.DateTime, default=datetime.utcnow)

    db.UniqueConstraint('company_id', 'date', name='unique_company_date')

    def __repr__(self):
        return f'<StockPrice {self.company_id} {self.date} {self.close_price}>'

class PerformanceCalculation(db.Model):
    __tablename__ = 'performance_calculations'
    id = db.Column(db.Integer, primary_key=True)
    analysis_id = db.Column(db.Integer, db.ForeignKey('analyses.id'), nullable=False)
    calculation_date = db.Column(db.Date, nullable=False)
    price_at_analysis = db.Column(db.Numeric(10, 2), nullable=False)
    price_current = db.Column(db.Numeric(10, 2), nullable=False)
    return_pct = db.Column(db.Numeric(10, 2), nullable=False)
    calculated_at = db.Column(db.DateTime, default=datetime.utcnow)

    db.UniqueConstraint('analysis_id', 'calculation_date', name='unique_analysis_calculation')

    # Relationship
    analysis = db.relationship('Analysis', backref='performance_calculations')

    def __repr__(self):
        return f'<PerformanceCalculation {self.analysis_id} {self.calculation_date}>'

class ActivityLog(db.Model):
    __tablename__ = 'activity_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    action = db.Column(db.String(255), nullable=False)
    details = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(45), nullable=True)

    user = db.relationship('User', backref='activity_logs')

    def __repr__(self):
        return f'<ActivityLog {self.user_id} {self.action}>'

class CsvUpload(db.Model):
    __tablename__ = 'csv_uploads'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime, nullable=True)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    row_count = db.Column(db.Integer, default=0)

    uploader = db.relationship('User', backref='csv_uploads')
    analyses = db.relationship('Analysis', backref='csv_upload', lazy='dynamic')

    def __repr__(self):
        return f'<CsvUpload {self.filename}>'

class PasswordResetToken(db.Model):
    __tablename__ = 'password_reset_tokens'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    token_hash = db.Column(db.String(255), nullable=False)
    token_type = db.Column(db.String(20), nullable=False)  # 'registration' or 'reset'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)

    user = db.relationship('User', backref='tokens')

    def __repr__(self):
        return f'<PasswordResetToken {self.user_id} {self.token_type}>'


class AnalystMapping(db.Model):
    __tablename__ = 'analyst_mappings'
    id = db.Column(db.Integer, primary_key=True)
    analyst_name = db.Column(db.String(255), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='analyst_mappings')

    def __repr__(self):
        return f'<AnalystMapping {self.analyst_name} -> {self.user_id}>'


class Vote(db.Model):
    __tablename__ = 'votes'
    id = db.Column(db.Integer, primary_key=True)
    analysis_id = db.Column(db.Integer, db.ForeignKey('analyses.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    vote = db.Column(db.Boolean, nullable=False)  # True = yes/add, False = no/remove
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    analysis = db.relationship('Analysis', backref='votes')
    user = db.relationship('User', backref='votes')

    __table_args__ = (db.UniqueConstraint('analysis_id', 'user_id', name='unique_vote_per_analysis_user'),)

    def __repr__(self):
        return f'<Vote {self.analysis_id} {self.user_id} {self.vote}>'


class PortfolioPurchase(db.Model):
    __tablename__ = 'portfolio_purchases'
    id = db.Column(db.Integer, primary_key=True)
    analysis_id = db.Column(db.Integer, db.ForeignKey('analyses.id'), nullable=False)
    purchase_date = db.Column(db.Date, nullable=False)
    added_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)

    analysis = db.relationship('Analysis', backref='portfolio_purchases')
    user = db.relationship('User', backref='portfolio_purchases')

    __table_args__ = (db.UniqueConstraint('analysis_id', name='unique_purchase_per_analysis'),)

    def __repr__(self):
        return f'<PortfolioPurchase {self.analysis_id} {self.purchase_date}>'


class BenchmarkPrice(db.Model):
    """Cached benchmark/index prices (SPY, VT, EEMS, etc.) for performance comparison."""
    __tablename__ = 'benchmark_prices'
    id = db.Column(db.Integer, primary_key=True)
    ticker = db.Column(db.String(20), nullable=False)  # 'SPY', 'VT', 'EEMS'
    date = db.Column(db.Date, nullable=False)
    close_price = db.Column(db.Numeric(10, 2), nullable=False)
    fetched_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    db.UniqueConstraint('ticker', 'date', name='unique_ticker_date')
    
    def __repr__(self):
        return f'<BenchmarkPrice {self.ticker} {self.date} {self.close_price}>'


class Idea(db.Model):
    """Stock ideas shared on the public wall."""
    __tablename__ = 'ideas'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text, nullable=False)
    sentiment = db.Column(db.String(20), default='neutral')  # bullish, bearish, neutral
    ticker = db.Column(db.String(20), nullable=True)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    likes_count = db.Column(db.Integer, default=0)
    
    # Relationships
    author = db.relationship('User', backref='ideas')
    comments = db.relationship('IdeaComment', backref='idea', lazy='dynamic', cascade='all, delete-orphan')
    
    @property
    def author_name(self):
        return self.author.full_name or self.author.email.split('@')[0] if self.author else 'Unknown'
    
    @property
    def likes(self):
        return self.likes_count
    
    def __repr__(self):
        return f'<Idea {self.title}>'


class IdeaComment(db.Model):
    """Comments on stock ideas."""
    __tablename__ = 'idea_comments'
    id = db.Column(db.Integer, primary_key=True)
    idea_id = db.Column(db.Integer, db.ForeignKey('ideas.id'), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    author = db.relationship('User', backref='idea_comments')
    
    @property
    def author_name(self):
        return self.author.full_name or self.author.email.split('@')[0] if self.author else 'Unknown'
    
    def __repr__(self):
        return f'<IdeaComment {self.id}>'

class CompanySectorCache(db.Model):
    """Cached sector information for companies to avoid repeated API calls."""
    __tablename__ = 'company_sector_cache'
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, unique=True)
    sector = db.Column(db.String(100), nullable=True)
    industry = db.Column(db.String(100), nullable=True)
    fetched_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship
    company = db.relationship('Company', backref=db.backref('sector_cache', uselist=False))
    
    def __repr__(self):
        return f'<CompanySectorCache {self.company_id}: {self.sector}>'


class OverviewDataCache(db.Model):
    """
    Database-backed cache for overview page data.
    Persists across deployments on Render.
    """
    __tablename__ = 'overview_data_cache'
    
    id = db.Column(db.Integer, primary_key=True)
    filter_type = db.Column(db.String(50), nullable=False, unique=True, index=True)
    
    # JSON data
    portfolio_performance = db.Column(db.JSON, default=dict)
    series_all = db.Column(db.JSON, default=list)
    series_1y = db.Column(db.JSON, default=list)
    sector_stats = db.Column(db.JSON, default=list)
    analyst_rankings = db.Column(db.JSON, default=list)
    positive_ratio = db.Column(db.Float, default=0)
    total_positions = db.Column(db.Integer, default=0)
    
    # Metadata
    cached_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)
    
    def is_fresh(self, expiry_days=7):
        """Check if cache is still valid."""
        if self.expires_at:
            return datetime.utcnow() < self.expires_at
        # Default 7 days from cached_at
        return datetime.utcnow() < self.cached_at + timedelta(days=expiry_days)
    
    def to_dict(self):
        """Convert to dictionary for template use."""
        return {
            'portfolio_performance': self.portfolio_performance,
            'series_all': self.series_all,
            'series_1y': self.series_1y,
            'sector_stats': self.sector_stats,
            'analyst_rankings': self.analyst_rankings,
            'positive_ratio': self.positive_ratio,
            'total_positions': self.total_positions,
            'cached_at': self.cached_at.isoformat() if self.cached_at else None,
        }
    
    def __repr__(self):
        return f'<OverviewDataCache {self.filter_type}: {self.cached_at}>'


class BlogPost(db.Model):
    """Blog posts for KI Asset Management website."""
    __tablename__ = 'blog_posts'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    slug = db.Column(db.String(255), unique=True, nullable=False, index=True)
    
    # SEO fields
    meta_description = db.Column(db.String(300), nullable=True)
    meta_keywords = db.Column(db.String(255), nullable=True)
    og_image = db.Column(db.String(500), nullable=True)  # Open Graph image URL
    
    # Content
    excerpt = db.Column(db.Text, nullable=True)  # Short summary for previews
    content = db.Column(db.Text, nullable=False)  # Main content (HTML/Markdown)
    content_type = db.Column(db.String(20), default='html')  # 'html' or 'markdown'
    
    # Author & Publishing
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    published_at = db.Column(db.DateTime, nullable=True)  # Null = draft
    
    # Visibility & Status
    is_public = db.Column(db.Boolean, default=False)  # Publicly visible
    is_featured = db.Column(db.Boolean, default=False)  # Featured on homepage
    status = db.Column(db.String(20), default='draft')  # 'draft', 'published', 'archived'
    
    # Engagement
    view_count = db.Column(db.Integer, default=0)
    
    # Category/Tags
    category = db.Column(db.String(50), nullable=True)
    tags = db.Column(db.String(255), nullable=True)  # Comma-separated tags
    
    # Relationships
    author = db.relationship('User', backref='blog_posts')
    
    @property
    def author_name(self):
        """Get author display name."""
        if self.author:
            return self.author.full_name or self.author.email.split('@')[0]
        return 'Unknown'
    
    @property
    def is_published(self):
        """Check if post is published and public."""
        return self.status == 'published' and self.is_public and self.published_at
    
    @property
    def reading_time(self):
        """Estimate reading time in minutes."""
        if not self.content:
            return 1
        # Average reading speed: 200 words per minute
        word_count = len(self.content.split())
        return max(1, round(word_count / 200))
    
    @property
    def tag_list(self):
        """Get tags as a list."""
        if not self.tags:
            return []
        return [tag.strip() for tag in self.tags.split(',') if tag.strip()]
    
    @property
    def formatted_date(self):
        """Get formatted publish date."""
        if self.published_at:
            return self.published_at.strftime('%B %d, %Y')
        return self.created_at.strftime('%B %d, %Y')
    
    def get_excerpt(self, max_length=200):
        """Get excerpt or generate from content."""
        if self.excerpt:
            return self.excerpt
        # Strip HTML tags and truncate
        import re
        text = re.sub(r'<[^>]+>', '', self.content)
        if len(text) > max_length:
            return text[:max_length].rsplit(' ', 1)[0] + '...'
        return text
    
    def generate_slug(self):
        """Generate URL-friendly slug from title."""
        import re
        slug = re.sub(r'[^\w\s-]', '', self.title).strip().lower()
        slug = re.sub(r'[-\s]+', '-', slug)
        # Add timestamp for uniqueness
        from datetime import datetime
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
        return f"{slug}-{timestamp}"
    
    def __repr__(self):
        return f'<BlogPost {self.title}>'


class SystemSettings(db.Model):
    """System settings for automated recalculation and other configuration."""
    __tablename__ = 'system_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=True)
    value_type = db.Column(db.String(20), default='string')  # string, integer, boolean, json
    description = db.Column(db.String(255))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    @staticmethod
    def get(key: str, default=None):
        """Get a setting value by key."""
        setting = SystemSettings.query.filter_by(key=key).first()
        if not setting:
            return default
        
        if setting.value_type == 'boolean':
            return setting.value in ('true', 'True', '1', 'yes')
        elif setting.value_type == 'integer':
            try:
                return int(setting.value)
            except (ValueError, TypeError):
                return default
        elif setting.value_type == 'json':
            import json
            try:
                return json.loads(setting.value)
            except (json.JSONDecodeError, TypeError):
                return default
        return setting.value
    
    @staticmethod
    def set(key: str, value, value_type: str = 'string', description: str = None):
        """Set a setting value."""
        setting = SystemSettings.query.filter_by(key=key).first()
        if not setting:
            setting = SystemSettings(key=key, value_type=value_type, description=description)
            db.session.add(setting)
        
        if value_type == 'boolean':
            setting.value = 'true' if value else 'false'
        elif value_type == 'json':
            import json
            setting.value = json.dumps(value)
        else:
            setting.value = str(value)
        
        db.session.commit()
        return setting
    
    def __repr__(self):
        return f'<SystemSettings {self.key}: {self.value}>'


class RecalculationLog(db.Model):
    """Logs for automated recalculation runs."""
    __tablename__ = 'recalculation_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    run_type = db.Column(db.String(50), nullable=False)  # 'manual', 'scheduled', 'automated'
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default='running')  # 'running', 'completed', 'failed'
    duration_seconds = db.Column(db.Float, nullable=True)
    
    # Statistics
    analyses_processed = db.Column(db.Integer, default=0)
    prices_updated = db.Column(db.Integer, default=0)
    calculations_updated = db.Column(db.Integer, default=0)
    errors_count = db.Column(db.Integer, default=0)
    
    # Details
    error_message = db.Column(db.Text, nullable=True)
    details = db.Column(db.JSON, nullable=True)
    
    def mark_completed(self, stats: Dict = None):
        """Mark the log as completed with statistics."""
        from datetime import timedelta
        self.completed_at = datetime.utcnow()
        self.duration_seconds = (self.completed_at - self.started_at).total_seconds()
        self.status = 'completed'
        
        if stats:
            self.analyses_processed = stats.get('analyses_processed', 0)
            self.prices_updated = stats.get('prices_updated', 0)
            self.calculations_updated = stats.get('calculations_updated', 0)
            self.errors_count = stats.get('errors_count', 0)
        
        db.session.commit()
    
    def mark_failed(self, error_message: str):
        """Mark the log as failed with error message."""
        from datetime import timedelta
        self.completed_at = datetime.utcnow()
        self.duration_seconds = (self.completed_at - self.started_at).total_seconds()
        self.status = 'failed'
        self.error_message = error_message
        db.session.commit()
    
    def __repr__(self):
        return f'<RecalculationLog {self.run_type}: {self.status} at {self.started_at}>'
