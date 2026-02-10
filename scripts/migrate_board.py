#!/usr/bin/env python3
"""Add new columns and tables for board feature."""
import sys
sys.path.insert(0, '.')

from app import create_app
from app.extensions import db

app = create_app()
with app.app_context():
    insp = db.inspect(db.engine)
    # Check analyses table columns
    columns = [col['name'] for col in insp.get_columns('analyses')]
    if 'purchase_date' not in columns:
        db.engine.execute('ALTER TABLE analyses ADD COLUMN purchase_date DATE')
        print('Added purchase_date column')
    else:
        print('purchase_date column already exists')
    if 'is_in_portfolio' not in columns:
        db.engine.execute('ALTER TABLE analyses ADD COLUMN is_in_portfolio BOOLEAN DEFAULT 0')
        print('Added is_in_portfolio column')
    else:
        print('is_in_portfolio column already exists')
    
    # Ensure new tables are created (db.create_all will create missing tables)
    db.create_all()
    print('Migration completed.')