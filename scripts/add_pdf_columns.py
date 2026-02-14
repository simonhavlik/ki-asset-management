#!/usr/bin/env python3
"""
Add pdf_binary columns to existing blog_posts table.

This migration adds the necessary columns for database PDF storage.
Run this on production to migrate the schema without losing data.

Usage:
    python scripts/add_pdf_columns.py
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from sqlalchemy import text


def add_pdf_columns():
    """Add pdf_binary columns to blog_posts table."""
    app = create_app()
    
    with app.app_context():
        print("Adding PDF columns to blog_posts table...")
        print(f"Database: {app.config['SQLALCHEMY_DATABASE_URI'][:50]}...")
        
        # Check if columns already exist
        with db.engine.connect() as conn:
            # PostgreSQL specific - check if column exists
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'blog_posts' 
                AND column_name = 'pdf_binary'
            """))
            
            if result.fetchone():
                print("\n✓ Columns already exist! No migration needed.")
                return
            
            print("\nColumns not found. Adding them now...")
            
            # Add pdf_binary column (BYTEA in PostgreSQL)
            conn.execute(text("""
                ALTER TABLE blog_posts 
                ADD COLUMN pdf_binary BYTEA
            """))
            print("  ✓ Added pdf_binary column")
            
            # Add pdf_content_type column
            conn.execute(text("""
                ALTER TABLE blog_posts 
                ADD COLUMN pdf_content_type VARCHAR(100)
            """))
            print("  ✓ Added pdf_content_type column")
            
            # Add pdf_filename_db column
            conn.execute(text("""
                ALTER TABLE blog_posts 
                ADD COLUMN pdf_filename_db VARCHAR(255)
            """))
            print("  ✓ Added pdf_filename_db column")
            
            conn.commit()
        
        print("\n" + "="*60)
        print("Migration complete!")
        print("New columns added to blog_posts table:")
        print("  - pdf_binary (BYTEA)")
        print("  - pdf_content_type (VARCHAR 100)")
        print("  - pdf_filename_db (VARCHAR 255)")
        print("\nYou can now migrate existing PDFs using:")
        print("  python scripts/migrate_pdfs_to_db.py")


if __name__ == '__main__':
    add_pdf_columns()
