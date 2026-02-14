#!/usr/bin/env python3
"""
Migrate existing PDF files from filesystem to database storage.

This script reads all PDFs currently stored in the filesystem and migrates them
to the database (pdf_binary column) for Render/Neon DB deployment compatibility.

Usage:
    python scripts/migrate_pdfs_to_db.py

Requirements:
    - Virtual environment activated
    - DATABASE_URL configured for production (or USE_LOCAL_SQLITE=True for testing)
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models import BlogPost


def migrate_pdfs_to_database():
    """Migrate all PDFs from filesystem to database storage."""
    app = create_app()
    
    with app.app_context():
        print("Starting PDF migration to database...")
        print(f"Database: {app.config['SQLALCHEMY_DATABASE_URI'][:50]}...")
        
        # Find all blog posts with PDF paths but no binary data
        posts_with_pdfs = BlogPost.query.filter(
            BlogPost.pdf_path.isnot(None),
            BlogPost.pdf_binary.is_(None)
        ).all()
        
        print(f"\nFound {len(posts_with_pdfs)} posts with PDFs to migrate")
        
        migrated = 0
        failed = 0
        skipped = 0
        
        for post in posts_with_pdfs:
            try:
                # Build full path to PDF file
                pdf_path = post.pdf_path
                full_path = os.path.join(app.root_path, 'static', pdf_path)
                
                print(f"\nProcessing post '{post.title}' (ID: {post.id})")
                print(f"  PDF path: {pdf_path}")
                
                # Check if file exists
                if not os.path.exists(full_path):
                    print(f"  ⚠️  File not found: {full_path}")
                    failed += 1
                    continue
                
                # Read file content
                with open(full_path, 'rb') as f:
                    pdf_content = f.read()
                
                file_size = len(pdf_content)
                print(f"  File size: {file_size:,} bytes ({file_size/1024/1024:.2f} MB)")
                
                # Skip if too large (> 20MB to be safe)
                if file_size > 20 * 1024 * 1024:
                    print(f"  ⚠️  Skipping - file too large (>20MB)")
                    skipped += 1
                    continue
                
                # Store in database
                post.pdf_binary = pdf_content
                post.pdf_content_type = 'application/pdf'
                post.pdf_filename_db = os.path.basename(pdf_path)
                
                db.session.commit()
                
                print(f"  ✓ Migrated successfully!")
                migrated += 1
                
            except Exception as e:
                print(f"  ✗ Error: {e}")
                failed += 1
                db.session.rollback()
        
        print("\n" + "="*60)
        print("Migration complete!")
        print(f"  Migrated: {migrated}")
        print(f"  Failed:   {failed}")
        print(f"  Skipped:  {skipped}")
        print(f"  Total:    {len(posts_with_pdfs)}")
        
        # Show database stats
        total_db_pdfs = BlogPost.query.filter(BlogPost.pdf_binary.isnot(None)).count()
        print(f"\nTotal PDFs in database: {total_db_pdfs}")
        
        return migrated, failed, skipped


def verify_migration():
    """Verify that PDFs can be served from database."""
    app = create_app()
    
    with app.app_context():
        print("\nVerifying database PDFs...")
        
        posts_with_binary = BlogPost.query.filter(
            BlogPost.pdf_binary.isnot(None)
        ).limit(5).all()
        
        for post in posts_with_binary:
            size = len(post.pdf_binary) if post.pdf_binary else 0
            print(f"  Post '{post.title[:40]}...': {size:,} bytes")
        
        print(f"\n✓ Verification complete - {len(posts_with_binary)} PDFs ready to serve")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Migrate PDFs to database storage')
    parser.add_argument('--verify', action='store_true', help='Only verify existing database PDFs')
    
    args = parser.parse_args()
    
    if args.verify:
        verify_migration()
    else:
        print("PDF Migration Tool")
        print("="*60)
        print("This will migrate PDFs from filesystem to database.")
        print("Make sure your database is backed up before running!\n")
        
        confirm = input("Continue? (yes/no): ")
        if confirm.lower() == 'yes':
            migrate_pdfs_to_database()
            verify_migration()
        else:
            print("Migration cancelled.")
