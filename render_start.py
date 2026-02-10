#!/usr/bin/env python3
"""
Render Startup Script

This script automatically initializes the database on first deploy
and then starts the Gunicorn server. No manual Shell access needed!

Usage in Render:
    Build Command: pip install -r requirements.txt
    Start Command: python render_start.py
"""

import os
import sys
import subprocess

# Add the app directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def init_database():
    """Initialize database tables if they don't exist."""
    try:
        from app import create_app
        from app.extensions import db
        from sqlalchemy import inspect
        
        app = create_app()
        
        with app.app_context():
            inspector = inspect(db.engine)
            existing_tables = inspector.get_table_names()
            
            # Check if essential tables exist
            required_tables = ['users', 'analyses', 'companies']
            
            if not all(table in existing_tables for table in required_tables):
                print("=" * 60)
                print("DATABASE INITIALIZATION")
                print("=" * 60)
                print("Creating database tables...")
                db.create_all()
                print("✓ Database tables created successfully!")
                
                # Check if admin user exists
                from app.models import User
                admin_exists = User.query.filter_by(is_admin=True).first()
                
                if not admin_exists:
                    print("\n" + "=" * 60)
                    print("ADMIN USER SETUP REQUIRED")
                    print("=" * 60)
                    print("No admin user found. To create one, temporarily change")
                    print("your Render start command to: flask create-admin")
                    print("Run it once, then change back to: python render_start.py")
                    print("=" * 60)
                else:
                    print("✓ Admin user already exists")
                
                print("=" * 60)
            else:
                print("✓ Database already initialized")
                
    except Exception as e:
        print(f"ERROR during database initialization: {e}")
        print("Continuing to start server anyway...")
        import traceback
        traceback.print_exc()

def create_default_admin():
    """
    Create a default admin user from environment variables.
    Set ADMIN_EMAIL and ADMIN_PASSWORD in Render environment variables.
    
    Only creates admin if BOTH ADMIN_EMAIL and ADMIN_PASSWORD are explicitly set.
    Otherwise, the first user to register with ADMIN_EMAIL becomes admin automatically
    through the registration flow.
    """
    admin_email = os.environ.get('ADMIN_EMAIL')
    admin_password = os.environ.get('ADMIN_PASSWORD')
    
    # Only auto-create admin if BOTH email and password are explicitly set
    # Otherwise, let the registration flow handle admin assignment
    if not admin_email or not admin_password:
        print("ℹ Admin auto-creation skipped (ADMIN_EMAIL and/or ADMIN_PASSWORD not set)")
        print("ℹ The first user to register with ADMIN_EMAIL will become admin automatically")
        return
    
    try:
        from app import create_app
        from app.extensions import db
        from app.models import User
        
        app = create_app()
        
        with app.app_context():
            # Check if admin already exists
            existing = User.query.filter_by(email=admin_email).first()
            if existing:
                print(f"✓ Admin user {admin_email} already exists")
                return
            
            # Create admin user
            user = User(
                email=admin_email,
                is_admin=True,
                is_active=True,
                email_verified=True,
                full_name='System Administrator'
            )
            user.set_password(admin_password)
            db.session.add(user)
            db.session.commit()
            
            print("=" * 60)
            print("AUTO-ADMIN CREATED")
            print("=" * 60)
            print(f"Admin user created: {admin_email}")
            print("You can now log in with this account.")
            print("=" * 60)
            
    except Exception as e:
        print(f"Warning: Could not create auto-admin: {e}")

def main():
    """Main startup sequence."""
    print("\n" + "=" * 60)
    print("KI ASSET MANAGEMENT - STARTING UP")
    print("=" * 60)
    
    # Initialize database
    init_database()
    
    # Create auto-admin if configured
    create_default_admin()
    
    # Get port from environment (Render sets this)
    port = os.environ.get('PORT', '10000')
    
    print("\n" + "=" * 60)
    print("STARTING GUNICORN SERVER")
    print("=" * 60)
    print(f"Port: {port}")
    print(f"Database: {'SQLite' if os.environ.get('USE_LOCAL_SQLITE', 'True').lower() == 'true' else 'PostgreSQL'}")
    print("=" * 60 + "\n")
    
    # Start Gunicorn with the app
    # Using app:create_app() as the WSGI entry point
    cmd = [
        'gunicorn',
        '--bind', f'0.0.0.0:{port}',
        '--workers', '2',  # 2 workers for free tier (adjust based on plan)
        '--threads', '4',  # 4 threads per worker
        '--timeout', '120',  # 2 minute timeout for long operations
        '--access-logfile', '-',  # Log to stdout
        '--error-logfile', '-',   # Log errors to stdout
        '--capture-output',        # Capture print statements
        '--enable-stdio-inheritance',  # Allow stdout/stderr in logs
        'app:create_app()'
    ]
    
    # Run Gunicorn
    sys.exit(subprocess.call(cmd))

if __name__ == '__main__':
    main()
