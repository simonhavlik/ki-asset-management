#!/usr/bin/env python3
"""
Migration script to create benchmark_prices table.
Run this after deploying the new code to create the necessary table.
"""

import sys
import os

# Add the parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import BenchmarkPrice

def migrate():
    """Create benchmark_prices table."""
    app = create_app()
    
    with app.app_context():
        # Check if table already exists
        inspector = db.inspect(db.engine)
        if 'benchmark_prices' in inspector.get_table_names():
            print("Table 'benchmark_prices' already exists.")
            return
        
        # Create the table
        BenchmarkPrice.__table__.create(db.engine)
        print("Created table 'benchmark_prices' successfully!")
        
        # Show table schema
        print("\nTable schema:")
        for column in BenchmarkPrice.__table__.columns:
            print(f"  - {column.name}: {column.type}")

if __name__ == '__main__':
    migrate()
