import os
from flask import Flask
from .config import config
from .extensions import db, login_manager, mail, csrf, cache
from .security import init_security, rate_limit

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
        config_name = os.environ.get('FLASK_CONFIG', 'default')

    app = Flask(__name__)
    app.config.from_object(config[config_name])

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
        
        # Warm caches for Neon.tech optimization (pre-populate in-memory cache)
        if os.environ.get('NEON_OPTIMIZE', 'true').lower() == 'true':
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

    # Initialize security features
    init_security(app)

    # Add CLI commands
    register_cli(app)

    return app

def register_cli(app):
    """Register CLI commands."""
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
        try:
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
            print(f"Skipped: {stats.get('skipped', 0)}")
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