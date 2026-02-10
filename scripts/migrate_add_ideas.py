#!/usr/bin/env python3
"""
Migration script to add Idea and IdeaComment tables for the public wall feature.
Run this after deploying the new code to create the necessary database tables.
"""

import sys
sys.path.insert(0, '/home/simon/py/nmy/analyst_website 2.0')

from app import create_app
from app.extensions import db
from app.models import Idea, IdeaComment

def migrate():
    app = create_app()
    with app.app_context():
        print("Creating Idea and IdeaComment tables...")
        
        # Create tables
        db.create_all()
        
        print("Migration completed successfully!")
        print("- ideas table created")
        print("- idea_comments table created")

if __name__ == '__main__':
    migrate()
