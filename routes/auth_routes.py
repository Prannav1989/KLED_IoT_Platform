#auth_routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_user, logout_user, current_user, login_required
from sqlalchemy import func
import re

# Import within functions to avoid circular imports
def get_db():
    from extensions import db
    return db

def get_models():
    from models import User
    return User

def get_csrf():
    from extensions import csrf
    return csrf

auth_bp = Blueprint('auth', __name__)

def redirect_based_on_role():
    """
    Single source of truth:
    Let dashboard_list() decide what template to show
    """
    return redirect(url_for("dashboard.dashboard_list"))


def validate_email(email):
    """Basic email validation"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_password(password):
    """Password strength validation"""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"
    
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter"
    
    if not re.search(r"\d", password):
        return False, "Password must contain at least one digit"
    
    return True, "Password is strong"

def validate_username(username):
    """Username validation"""
    if len(username) < 3:
        return False, "Username must be at least 3 characters long"
    
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return False, "Username can only contain letters, numbers, and underscores"
    
    return True, "Username is valid"

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.dashboard_list"))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember_me = bool(request.form.get('remember_me'))

        if not username or not password:
            flash('Please enter both username and password', 'danger')
            return render_template('login.html')

        User = get_models()
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            if not user.is_active:
                flash('Your account has been deactivated.', 'warning')
                return render_template('login.html')

            login_user(user, remember=remember_me)

            next_page = request.args.get("next")
            if isinstance(next_page, str) and next_page.startswith("/"):
                return redirect(next_page)

            return redirect(url_for("dashboard.dashboard_list"))

        flash('Invalid username or password', 'danger')

    return render_template('login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """User registration"""
    if current_user.is_authenticated:
        return redirect_based_on_role()
        
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        try:
            User = get_models()
            db = get_db()
            
            # Validation checks
            if not all([username, email, password, confirm_password]):
                flash('Please fill in all fields', 'danger')
                return render_template('register.html')
            
            # Validate username
            is_valid_username, username_msg = validate_username(username)
            if not is_valid_username:
                flash(username_msg, 'danger')
                return render_template('register.html')
            
            # Validate email
            if not validate_email(email):
                flash('Please enter a valid email address', 'danger')
                return render_template('register.html')
            
            # Validate password
            if password != confirm_password:
                flash('Passwords do not match', 'danger')
                return render_template('register.html')
            
            is_valid_password, password_msg = validate_password(password)
            if not is_valid_password:
                flash(password_msg, 'danger')
                return render_template('register.html')
            
            # Check if username exists
            if User.query.filter(func.lower(User.username) == func.lower(username)).first():
                flash('Username already exists', 'danger')
                return render_template('register.html')
            
            # Check if email exists
            if User.query.filter_by(email=email).first():
                flash('Email already exists', 'danger')
                return render_template('register.html')
            
            # Create user
            role = 'user'  # Default role for new registrations
            user = User(
                username=username, 
                email=email, 
                role=role,
                is_active=True  # Auto-activate users, or set to False for email verification
            )
            user.set_password(password)
            
            db.session.add(user)
            db.session.commit()
            
            # Log registration
            current_app.logger.info(f"New user registered: {username} ({email})")
            
            flash('Registration successful. Please login.', 'success')
            return redirect(url_for('auth.login'))
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Registration error for {username}: {e}")
            flash('An error occurred during registration. Please try again.', 'danger')
    
    return render_template('register.html')

@auth_bp.route('/logout')
@login_required
def logout():
    """User logout"""
    try:
        username = current_user.username
        logout_user()
        current_app.logger.info(f"User {username} logged out")
        flash('You have been logged out successfully.', 'info')
    except Exception as e:
        current_app.logger.error(f"Logout error: {e}")
        flash('An error occurred during logout.', 'danger')
    
    return redirect(url_for('auth.login'))

# Optional: Add password reset routes if needed
@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Forgot password functionality"""
    if current_user.is_authenticated:
        return redirect_based_on_role()
        
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        
        if not email:
            flash('Please enter your email address', 'danger')
            return render_template('auth/forgot_password.html')
        
        if not validate_email(email):
            flash('Please enter a valid email address', 'danger')
            return render_template('auth/forgot_password.html')
        
        try:
            User = get_models()
            user = User.query.filter_by(email=email).first()
            
            if user:
                # In a real application, you would:
                # 1. Generate a reset token
                # 2. Send email with reset link
                # 3. Store token in database with expiration
                
                # For now, just show a message
                current_app.logger.info(f"Password reset requested for: {email}")
                flash('If an account with that email exists, a password reset link has been sent.', 'info')
            else:
                # Don't reveal whether email exists or not for security
                current_app.logger.info(f"Password reset attempted for non-existent email: {email}")
                flash('If an account with that email exists, a password reset link has been sent.', 'info')
            
            return redirect(url_for('auth.login'))
            
        except Exception as e:
            current_app.logger.error(f"Forgot password error for {email}: {e}")
            flash('An error occurred. Please try again.', 'danger')
    
    return render_template('auth/forgot_password.html')

# Error handlers specific to auth
@auth_bp.app_errorhandler(401)
def unauthorized(error):
    """Handle 401 Unauthorized errors"""
    flash('Please log in to access this page.', 'warning')
    return redirect(url_for('auth.login', next=request.url))