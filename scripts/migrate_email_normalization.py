#!/usr/bin/env python3
"""
Migrate existing email addresses to normalized (diacritic‑stripped) form.
"""
import sys
sys.path.insert(0, '.')

from app import create_app
from app.extensions import db
from app.utils.email_normalization import normalize_email

def main():
    app = create_app()
    with app.app_context():
        from app.models import User
        # Get all users
        users = User.query.all()
        updates = []
        for user in users:
            normalized = normalize_email(user.email)
            if normalized != user.email:
                # Check for uniqueness conflict
                existing = User.query.filter_by(email=normalized).first()
                if existing and existing.id != user.id:
                    print(f"ERROR: Cannot update {user.email} -> {normalized}, already taken by user {existing.id}")
                    continue
                updates.append((user.email, normalized))
                user.email = normalized
        if updates:
            db.session.commit()
            print(f"Updated {len(updates)} email(s):")
            for old, new in updates:
                print(f"  {old} -> {new}")
        else:
            print("No emails needed updating.")
        # Verify uniqueness after migration
        from sqlalchemy import func
        duplicates = db.session.query(User.email, func.count(User.email)).group_by(User.email).having(func.count(User.email) > 1).all()
        if duplicates:
            print("WARNING: Duplicate emails after migration:", duplicates)
        else:
            print("All emails are unique.")

if __name__ == '__main__':
    main()