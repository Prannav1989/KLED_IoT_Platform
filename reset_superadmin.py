#!/usr/bin/env python3
"""
One-time script to reset and create super admin for testing
"""

import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import User
from werkzeug.security import generate_password_hash

def reset_superadmin():
    with app.app_context():
        print("🔧 Resetting super admin...")
        
        # Remove ALL existing super admins
        super_admins = User.query.filter_by(role='super_admin').all()
        for admin in super_admins:
            db.session.delete(admin)
            print(f"🗑️  Removed super admin: {admin.username}")
        
        # Also remove any existing user with username 'superadmin'
        existing_user = User.query.filter_by(username='superadmin').first()
        if existing_user:
            db.session.delete(existing_user)
            print(f"🗑️  Removed existing user: {existing_user.username}")
        
        db.session.commit()
        
        # Create new super admin
        new_super_admin = User(
            username='superadmin',
            email='superadmin@example.com',
            role='super_admin',
            password_hash=generate_password_hash('admin123')
        )
        
        db.session.add(new_super_admin)
        db.session.commit()
        
        print("=" * 50)
        print("✅ SUPER ADMIN RESET SUCCESSFUL!")
        print("=" * 50)
        print("📋 Login Credentials:")
        print(f"   Username: superadmin")
        print(f"   Password: admin123")
        print(f"   Email: superadmin@example.com")
        print(f"   Role: super_admin")
        print("=" * 50)
        print("⚠️  Use these credentials for testing only!")
        print("=" * 50)

if __name__ == '__main__':
    reset_superadmin()


"""
📋 Login Credentials:
   Username: superadmin
   Password: admin123
   Email: superadmin@example.com
   Role: super_admin
"""