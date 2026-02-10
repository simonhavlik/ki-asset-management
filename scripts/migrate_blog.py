#!/usr/bin/env python
"""
Migration script to create blog_posts table.
Run this script to add the blog functionality to your database.

Usage:
    python migrate_blog.py
"""

import os
import sys

# Add the parent directory to the path so we can import the app
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import BlogPost
from sqlalchemy import inspect

def migrate():
    """Create blog_posts table if it doesn't exist."""
    app = create_app()
    
    with app.app_context():
        inspector = inspect(db.engine)
        
        # Check if table already exists
        if 'blog_posts' in inspector.get_table_names():
            print("✓ blog_posts table already exists.")
            return
        
        print("Creating blog_posts table...")
        
        try:
            # Create the table
            BlogPost.__table__.create(db.engine)
            print("✓ blog_posts table created successfully!")
            print("\nBlog feature is now ready to use.")
            print("- Visit /blog to see the blog homepage")
            print("- Visit /blog/new to create a new post (authenticated users)")
            print("- Visit /blog/my-posts to manage your posts")
            
        except Exception as e:
            print(f"✗ Error creating blog_posts table: {e}")
            sys.exit(1)

if __name__ == '__main__':
    migrate()
