#!/usr/bin/env python3
"""
One-time script to reset and create super admin (SQLite)
"""

import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import User
from werkzeug.security import generate_password_hash

def reset_superadmin():
    with app.app_context():
        print("🔧 Resetting super admin (SQLite)...")

        # DEBUG: confirm DB being used
        print("📂 Database in use:", app.config.get("SQLALCHEMY_DATABASE_URI"))

        # Remove all existing super admins
        super_admins = User.query.filter_by(role='super_admin').all()
        for admin in super_admins:
            db.session.delete(admin)
            print(f"🗑️ Removed super admin: {admin.username}")

        # Remove any leftover 'superadmin' user
        existing_user = User.query.filter_by(username='superadmin').first()
        if existing_user:
            db.session.delete(existing_user)
            print(f"🗑️ Removed existing user: {existing_user.username}")

        db.session.commit()

        # Create new super admin
        new_super_admin = User(
            username='superadmin',
            email='superadmin@example.com',
            role='super_admin',
            password_hash=generate_password_hash('Admin@123'),
            active_status=True   # 🔥 THIS IS CRITICAL
        )

        db.session.add(new_super_admin)
        db.session.commit()

        print("=" * 60)
        print("✅ SUPER ADMIN RESET SUCCESSFUL (SQLite)")
        print("=" * 60)
        print("📋 Login Credentials:")
        print("   Username : superadmin")
        print("   Password : Admin@123")
        print("   Email    : superadmin@example.com")
        print("   Role     : super_admin")
        print("   Active   : YES")
        print("=" * 60)

if __name__ == '__main__':
    reset_superadmin()
