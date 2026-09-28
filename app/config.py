"""
Configuration module for KI Asset Management.

This module handles all application configuration including:
- Database settings (SQLite for dev, PostgreSQL for production)
- Email configuration
- Security settings
- API keys

Environment variables are loaded from .env file.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables from .env file
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '..', '.env'))


def get_database_url():
    """
    Determine the database URL based on environment settings.
    
    Priority:
    1. If USE_LOCAL_SQLITE=True, use local SQLite
    2. If DATABASE_URL is set, use that (for Render/neon.tech)
    3. Default to local SQLite for development
    
    Returns:
        str: Database connection URI
    """
    use_local = os.environ.get('USE_LOCAL_SQLITE', 'True').lower() == 'true'
    
    if use_local:
        # Local SQLite database
        db_path = os.path.abspath(os.path.join(basedir, '..', 'instance', 'analyst.db'))
        # Ensure instance directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        return f'sqlite:///{db_path}'
    
    # Production PostgreSQL (neon.tech or other provider)
    database_url = os.environ.get('DATABASE_URL')
    
    if database_url:
        # Handle Render's postgres:// vs postgresql:// issue
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        return database_url
    
    # Fallback to SQLite if nothing configured
    print("WARNING: No DATABASE_URL set and USE_LOCAL_SQLITE=False. Falling back to SQLite.", 
          file=sys.stderr)
    db_path = os.path.abspath(os.path.join(basedir, '..', 'instance', 'analyst.db'))
    return f'sqlite:///{db_path}'


def _engine_options(uri: str) -> dict:
    """Connection-pool tuning, but only for a real client/server database.

    SQLite (tests, run-local.sh) rejects pool_size/max_overflow and raises with
    the StaticPool it uses for in-memory databases. Applying the PostgreSQL
    options unconditionally meant ``create_app()`` blew up whenever a test
    module was run on its own.
    """
    if not uri or uri.startswith('sqlite'):
        return {'pool_pre_ping': True}
    # PostgreSQL: keep 5 connections ready, allow 10 more under load, recycle
    # hourly to reduce connection churn.
    return {
        'pool_size': 5,
        'max_overflow': 10,
        'pool_recycle': 3600,
        'pool_pre_ping': True,
        'pool_timeout': 30,
    }


class Config:
    """Base configuration shared across all environments."""
    
    # Flask core settings
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # Database configuration
    SQLALCHEMY_DATABASE_URI = get_database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = _engine_options(SQLALCHEMY_DATABASE_URI)
    
    # Email configuration
    # Option 1: SendGrid API (RECOMMENDED for Render - SMTP is blocked on free tier)
    # Sign up at https://sendgrid.com (100 emails/day free)
    SENDGRID_API_KEY = os.environ.get('SENDGRID_API_KEY')
    
    # Option 2: SMTP (for local development only)
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ('true', '1', 't')
    # Never let a broken/unreachable SMTP host hang a request: without this,
    # the fallback path blocked a worker for >2 minutes when SendGrid failed.
    MAIL_TIMEOUT = int(os.environ.get('MAIL_TIMEOUT', 10))

    # Outbound mail providers (HTTPS APIs - Render blocks SMTP):
    #   MAIL_PROVIDER forces one ('brevo' | 'resend' | 'sendgrid' | 'smtp');
    #   otherwise whichever API key is configured is used, SMTP last.
    MAIL_PROVIDER = os.environ.get('MAIL_PROVIDER', '').strip().lower()
    RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '')
    BREVO_API_KEY = os.environ.get('BREVO_API_KEY', '')
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', MAIL_USERNAME)
    
    # External API keys (optional)
    DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')
    BRAVE_SEARCH_API_KEY = os.environ.get('BRAVE_SEARCH_API_KEY', '')
    UNSPLASH_API_KEY = os.environ.get('UNSPLASH_API_KEY', '')
    
    # Security settings
    ALLOWED_EMAIL_DOMAIN = os.environ.get('ALLOWED_EMAIL_DOMAIN', 'klubinvestoru.com')
    ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', '')
    
    # Token expiration times (in seconds)
    PASSWORD_RESET_EXPIRATION = 86400  # 24 hours
    REGISTRATION_EXPIRATION = 86400    # 24 hours
    
    # File upload settings
    MAX_CONTENT_LENGTH = 32 * 1024 * 1024  # 32MB max file size (for PDF research reports)
    
    # Session security settings
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 86400  # 24 hours
    
    # CSRF settings
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600  # 1 hour
    WTF_CSRF_SSL_STRICT = True
    
    # Security headers (managed by security.py middleware)
    SECURITY_HEADERS_ENABLED = True


class DevelopmentConfig(Config):
    """Development configuration - local testing."""
    DEBUG = True
    SQLALCHEMY_ECHO = False  # Set to True to see SQL queries in logs
    
    # Always use SQLite for development unless explicitly configured
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        f'sqlite:///{os.path.abspath(os.path.join(basedir, "..", "instance", "analyst.db"))}'


class ProductionConfig(Config):
    """Production configuration - Render/neon.tech deployment."""
    DEBUG = False
    
    # Ensure secret key is set in production
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise ValueError(
            "SECRET_KEY must be set in production environment. "
            "Generate one with: python -c 'import secrets; print(secrets.token_hex(32))'"
        )
    
    # Ensure database is configured in production
    _database_url = os.environ.get('DATABASE_URL')
    _use_local = os.environ.get('USE_LOCAL_SQLITE', 'False').lower() == 'true'
    
    if not _database_url and _use_local:
        print("WARNING: Using local SQLite in production is not recommended.", file=sys.stderr)
    elif not _database_url and not _use_local:
        raise ValueError(
            "DATABASE_URL must be set in production when USE_LOCAL_SQLITE=False. "
            "Get your connection string from neon.tech dashboard."
        )


class TestingConfig(Config):
    """Testing configuration - for automated tests."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'  # In-memory database
    WTF_CSRF_ENABLED = False  # Disable CSRF for testing
    MAIL_SUPPRESS_SEND = True  # Don't send emails during tests


# Configuration mapping
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}


def print_config():
    """Print current configuration (for debugging)."""
    env = os.environ.get('FLASK_ENV', 'development')
    cfg = config.get(env, config['default'])
    
    print(f"\n{'='*60}")
    print(f"Configuration: {env.upper()}")
    print(f"{'='*60}")
    print(f"Database: {'SQLite' if 'sqlite' in cfg.SQLALCHEMY_DATABASE_URI else 'PostgreSQL'}")
    print(f"Debug: {cfg.DEBUG}")
    print(f"Email configured: {bool(cfg.MAIL_USERNAME)}")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    print_config()
