import os
from flask import Flask
from .config import config
from .extensions import db, login_manager, mail, csrf, cache
from .security import init_security, rate_limit

def _ensure_blog_columns(app):
    """Add columns to blog_posts that db.create_all() cannot add to an existing table."""
    try:
        from sqlalchemy import inspect, text
        inspector = inspect(db.engine)
        if 'blog_posts' not in inspector.get_table_names():
            return
        columns = {c['name'] for c in inspector.get_columns('blog_posts')}
        if 'doc_type' not in columns:
            app.logger.info("Adding blog_posts.doc_type column...")
            with db.engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE blog_posts ADD COLUMN doc_type VARCHAR(20) DEFAULT 'research'"
                ))
            app.logger.info("blog_posts.doc_type added")
    except Exception as e:
        app.logger.warning(f"Could not ensure blog_posts.doc_type: {e}")


def _ensure_email_outbox_table(app):
    """Create the outbox table on databases that predate it.

    Emails that no provider could deliver are parked here (Render blocks SMTP
    and API providers can run out of credit) and drained by the relay on the
    database host. Without the table we would fall back to losing the mail.
    """
    try:
        from sqlalchemy import inspect
        from .models import EmailOutbox
        if 'email_outbox' not in inspect(db.engine).get_table_names():
            app.logger.info("Creating email_outbox table...")
            EmailOutbox.__table__.create(db.engine)
            app.logger.info("email_outbox table created")
    except Exception as e:
        app.logger.warning(f"Could not ensure email_outbox: {e}")


def _ensure_benchmark_table(app):
    """Ensure benchmark_prices table exists and has seed data."""
    try:
        from sqlalchemy import inspect
        from .models import BenchmarkPrice
        
        inspector = inspect(db.engine)
        
        # Check if table exists
        if 'benchmark_prices' not in inspector.get_table_names():
            app.logger.info("Creating benchmark_prices table...")
            BenchmarkPrice.__table__.create(db.engine)
            app.logger.info("benchmark_prices table created successfully")
        
        # Check if we have any data
        count = BenchmarkPrice.query.count()
        if count == 0:
            app.logger.info("No benchmark data found. Creating seed data...")
            _create_seed_benchmark_data(app)
            
    except Exception as e:
        app.logger.warning(f"Could not verify benchmark table: {e}")


def _create_seed_benchmark_data(app):
    """Create synthetic seed data for benchmarks (SPY, VT, EEMS)."""
    from datetime import date, timedelta
    from .models import BenchmarkPrice
    import random
    
    try:
        tickers = {
            'SPY': 10.0,   # S&P 500 ~10% annual
            'VT': 9.0,     # FTSE All-World ~9% annual
            'EEMS': 7.0    # Emerging Markets ~7% annual
        }
        
        end_date = date.today()
        start_date = end_date - timedelta(days=730)  # 2 years back
        
        for ticker, annual_return in tickers.items():
            # Generate monthly data points
            current_date = start_date
            base_price = 100.0
            daily_return = annual_return / 365.0
            
            while current_date <= end_date:
                # Add some randomness to price
                days_from_start = (current_date - start_date).days
                trend = daily_return * days_from_start
                noise = random.uniform(-5, 5)
                price = base_price * (1 + trend/100) + noise
                
                bp = BenchmarkPrice(
                    ticker=ticker,
                    date=current_date,
                    close_price=round(price, 2)
                )
                db.session.add(bp)
                
                # Move to next month
                if current_date.month == 12:
                    current_date = current_date.replace(year=current_date.year + 1, month=1)
                else:
                    current_date = current_date.replace(month=current_date.month + 1)
        
        db.session.commit()
        app.logger.info("Seed benchmark data created successfully")
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error creating seed benchmark data: {e}")


def create_app(config_name=None):
    """Application factory."""
    if config_name is None:
        # FLASK_CONFIG wins, then FLASK_ENV, then the development default.
        # Reading ONLY FLASK_CONFIG was a real bug: the deployment sets
        # FLASK_ENV=production, so it silently ran DevelopmentConfig with
        # DEBUG=True. That in turn skipped the production-only security settings
        # in app/security.py (SESSION_COOKIE_SECURE and Strict-Transport-Security),
        # because those are gated on `not DEBUG`.
        config_name = (
            os.environ.get('FLASK_CONFIG')
            or os.environ.get('FLASK_ENV')
            or 'default'
        ).strip().lower()
        if config_name not in config:
            if config_name != 'default':
                import logging as _logging
                _logging.getLogger(__name__).warning(
                    "unknown FLASK_CONFIG/FLASK_ENV value %r - falling back to 'default'",
                    config_name,
                )
            config_name = 'default'

    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Trust exactly one proxy hop (Render terminates TLS in front of us).
    # Without this, request.remote_addr is the proxy's 127.0.0.1 for everyone,
    # which broke rate-limit keying and recorded bogus IPs in the activity log.
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # Configure logging before anything else so that extension/app init and
    # every module-level logger (app.utils.*, app.admin.*) is actually visible.
    from .logging_config import configure_logging, get_logger
    configure_logging(app)
    startup_logger = get_logger('startup')
    startup_logger.info(
        'creating app: config=%s debug=%s db=%s',
        config_name,
        app.config.get('DEBUG'),
        app.config.get('SQLALCHEMY_DATABASE_URI'),
    )

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)
    csrf.init_app(app)
    cache.init_app(app)

    # Set cache instance for neon_cache module
    from .utils.neon_cache import set_cache_instance
    set_cache_instance(cache)

    # Initialize WebFlow integration
    from .webflow_integration import webflow_integration
    webflow_integration.init_app(app)

    # Register blueprints
    from .auth import auth_bp
    from .admin import admin_bp
    from .analyst import analyst_bp
    from .main import main_bp
    from .admin.presentation_routes import presentation_bp
    from .blog import blog_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(analyst_bp, url_prefix='/analyst')
    app.register_blueprint(main_bp)
    app.register_blueprint(presentation_bp, url_prefix='/presentation')
    app.register_blueprint(blog_bp, url_prefix='/blog')

    # WebFlow integration routes
    from flask import render_template

    @app.route('/webflow-shell')
    def webflow_shell():
        """Serve the WebFlow shell template for testing."""
        return render_template('webflow_shell.html')

    # Create database tables
    with app.app_context():
        db.create_all()
        
        # Auto-migrate: check if benchmark_prices table exists and has data
        _ensure_benchmark_table(app)
        # Auto-migrate: add columns create_all() cannot add to an existing table
        _ensure_blog_columns(app)
        # Auto-migrate: outbox for emails no provider could deliver
        _ensure_email_outbox_table(app)
        
        # Warm caches for Neon.tech optimization (pre-populate in-memory cache)
        if (os.environ.get('NEON_OPTIMIZE', 'true').lower() == 'true'
                and os.environ.get('KI_SKIP_WARM') != '1'):
            try:
                from .utils.neon_cache import warm_public_caches
                warm_public_caches()
            except Exception as e:
                app.logger.warning(f"Cache warming failed (non-critical): {e}")
    
    # Initialize background scheduler for weekly updates
    from .scheduler import init_scheduler, shutdown_scheduler
    init_scheduler(app)
    
    # Register shutdown handler
    import atexit
    atexit.register(shutdown_scheduler)

    # Add global functions to Jinja2
    app.jinja_env.globals.update(abs=abs, min=min, max=max)

    # Context processors
    @app.context_processor
    def inject_now():
        from datetime import datetime
        return {'now': datetime.utcnow()}

    # Allow iframe embedding from personal website
    # IMPORTANT: Register BEFORE init_security so it runs AFTER (Flask runs after_request in reverse order)
    @app.after_request
    def allow_iframe(response):
        # Remove X-Frame-Options header to allow iframe embedding
        response.headers.pop('X-Frame-Options', None)
        # Also set CSP frame-ancestors for modern browsers
        # Preserve existing CSP and only modify frame-ancestors
        csp = response.headers.get('Content-Security-Policy', '')
        if csp:
            # Replace existing frame-ancestors directive or add it
            import re
            csp = re.sub(r"frame-ancestors[^;]*", "frame-ancestors *", csp)
            if 'frame-ancestors' not in csp:
                csp += " frame-ancestors *;"
            response.headers['Content-Security-Policy'] = csp
        else:
            response.headers['Content-Security-Policy'] = "frame-ancestors *;"
        return response

    # Initialize security features
    init_security(app)

    # Add CLI commands
    register_cli(app)

    return app

def register_cli(app):
    """Register CLI commands."""
    import click

    @app.cli.command('send-test-email')
    @click.argument('recipient')
    def send_test_email(recipient):
        """Send a test email to verify the outbound mail configuration.

        Example: flask send-test-email you@klubinvestoru.com
        """
        from .email_service import send_email
        ok = send_email(
            recipient,
            'KI Asset Management - mail test',
            'If you received this, outbound email works.',
            '<p>If you received this, <strong>outbound email works</strong>.</p>',
        )
        if ok:
            print(f'OK - test email accepted for {recipient}')
        else:
            from .email_service import outbox_pending_count
            print('FAILED - no provider accepted the message; see the provider error logged above')
            pending = outbox_pending_count()
            if pending:
                print(f'         queued in the outbox ({pending} pending) - the relay on the '
                      f'database host will deliver it')

    @app.cli.command('mail-status')
    def mail_status():
        """Show the mail configuration and how deep the outbox is.

        Example: flask mail-status
        """
        from .email_service import outbox_pending_count

        def show(label, value):
            print(f'  {label:<20} {value}')

        print('Mail configuration:')
        show('MAIL_PROVIDER', (app.config.get('MAIL_PROVIDER') or '').strip().lower() or '(auto)')
        show('GMAIL_CLIENT_ID', 'set' if app.config.get('GMAIL_CLIENT_ID') else '-')
        show('GMAIL_REFRESH_TOKEN', 'set' if app.config.get('GMAIL_REFRESH_TOKEN') else '-')
        show('BREVO_API_KEY', 'set' if app.config.get('BREVO_API_KEY') else '-')
        show('RESEND_API_KEY', 'set' if app.config.get('RESEND_API_KEY') else '-')
        show('SENDGRID_API_KEY', 'set' if app.config.get('SENDGRID_API_KEY') else '-')
        show('SMTP', f"{app.config.get('MAIL_SERVER')}:{app.config.get('MAIL_PORT')} "
                     f"user={app.config.get('MAIL_USERNAME')}")
        show('MAIL_DEFAULT_SENDER', app.config.get('MAIL_DEFAULT_SENDER'))
        pending = outbox_pending_count()
        show('outbox pending', pending if pending is not None else 'unavailable')
        from .email_service import _provider_chain
        show('provider order', ' -> '.join(_provider_chain()))

    @app.cli.command('send-outbox')
    @click.option('--limit', default=20, help='Maximum number of messages to retry.')
    def send_outbox(limit):
        """Retry emails parked in the outbox (sends that failed earlier).

        Example: flask send-outbox --limit 50
        """
        from .email_service import drain_outbox
        sent, failed = drain_outbox(limit=limit)
        print(f'{sent} sent, {failed} still failing')
        if failed and not sent:
            print('check the provider error logged above and run `flask mail-status`')

    @app.cli.command('create-admin')
    def create_admin():
        """Create an admin user."""
        from .models import User
        from .extensions import db
        import getpass
        email = input('Email: ').strip()
        if not email.endswith('@klubinvestoru.com'):
            print('Email must end with @klubinvestoru.com')
            return
        password = getpass.getpass('Password: ')
        if not password:
            print('Password cannot be empty')
            return
        user = User(email=email, is_admin=True)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        print(f'Admin user {email} created.')

    @app.cli.command('init-db')
    def init_db():
        """Initialize the database."""
        db.create_all()
        print('Database tables created.')
    
    @app.cli.command('warm-cache')
    def warm_cache():
        """Pre-populate all public-facing caches."""
        from .utils.neon_cache import warm_public_caches
        warmed = warm_public_caches()
        print(f'Warmed {len(warmed)} caches: {", ".join(warmed)}')
    
    @app.cli.command('clear-cache')
    def clear_cache():
        """Clear all public-facing caches."""
        from .utils.neon_cache import invalidate_all_public_cache
        invalidate_all_public_cache()
        print('All public caches cleared.')
    
    @app.cli.command('cache-stats')
    def cache_stats():
        """Show cache statistics."""
        from .utils.neon_cache import get_cache_stats
        import json
        stats = get_cache_stats()
        print(json.dumps(stats, indent=2))

    @app.cli.command('notion-test')
    def notion_test():
        """Test Notion API connection."""
        import os
        from .models import SystemSettings
        from .utils.notion_helper import NotionClient, NotionAPIError
        api_key = os.environ.get('NOTION_API_KEY', '') or SystemSettings.get('notion_api_key', '')
        database_id = os.environ.get('NOTION_DATABASE_ID', '') or SystemSettings.get('notion_database_id', '')
        if not api_key or not database_id:
            print('Notion API key or database ID not configured.')
            print('Set NOTION_API_KEY and NOTION_DATABASE_ID in .env.')
            return
        client = NotionClient(api_key)
        try:
            info = client.get_database_info(database_id)
            print(f"Connected to: {info['title']}")
            print(f"URL: {info['url']}")
            print(f"Properties: {[p['name'] for p in info['properties']]}")
            pages = client.query_database(database_id)
            print(f"Pages found: {len(pages)}")
        except NotionAPIError as e:
            print(f'Error: {e}')

    @app.cli.command('notion-import')
    def notion_import():
        """Import analysis schedule from Notion."""
        import os
        from .models import SystemSettings
        from .utils.notion_helper import NotionClient, NotionAPIError
        from .utils.csv_import import CsvImporter
        from datetime import datetime
        api_key = os.environ.get('NOTION_API_KEY', '') or SystemSettings.get('notion_api_key', '')
        database_id = os.environ.get('NOTION_DATABASE_ID', '') or SystemSettings.get('notion_database_id', '')
        if not api_key or not database_id:
            print('Notion API key or database ID not configured.')
            print('Set NOTION_API_KEY and NOTION_DATABASE_ID in .env.')
            return
        client = NotionClient(api_key)
        try:
            # Auto-detect the mapping from the database's real property names
            # rather than assuming a fixed schema: the live database's title
            # column is 'Name' (not 'Company') and its date column is 'Date '
            # with a trailing space, so an exact-match mapping silently produced
            # blank values that imported nothing.
            from .utils.notion_helper import build_notion_column_mapping
            properties = client.get_database_properties(database_id)
            column_mapping = build_notion_column_mapping(properties)
            resolved = {prop.strip() or prop: col for prop, col in column_mapping.items()}
            print(f'Mapped Notion columns: {resolved}')
            missing = [col for prop, col in column_mapping.items()
                       if prop.startswith('__missing__')]
            if missing:
                print(f'NOTE: no Notion property for {missing} - those will be empty')

            csv_content = client.export_database_as_csv(database_id, column_mapping)
            if not csv_content:
                print('No data found in Notion database.')
                return
            importer = CsvImporter(
                csv_content=csv_content,
                filename=f'notion_import_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv',
                uploaded_by=None
            )
            stats = importer.process()
            print(f"Created: {stats.get('created', 0)}")
            print(f"Updated: {stats.get('updated', 0)}")
            print(f"Skipped: {stats.get('skipped', 0)}"
                  f" (blank rows: {stats.get('blank', 0)}, already up to date: {stats.get('unchanged', 0)})")
            if stats.get('errors'):
                print(f"Errors: {len(stats['errors'])}")
                for err in stats['errors'][:5]:
                    print(f"  - {err}")
            if stats.get('created', 0) == 0 and stats.get('updated', 0) == 0:
                if stats.get('blank'):
                    print(
                        'WARNING: every row was blank, so the Notion properties were not '
                        'mapped to columns. Check the mapping printed above.'
                    )
                else:
                    print('Nothing to do: every row is already up to date.')
            if stats.get('errors'):
                print(f"Errors: {len(stats['errors'])}")
                for err in stats['errors'][:5]:
                    print(f'  - {err}')
        except NotionAPIError as e:
            print(f'Notion Error: {e}')
        except Exception as e:
            print(f'Error: {e}')

# Import models to ensure they are registered with SQLAlchemy
from . import models