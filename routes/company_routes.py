# routes/company_routes.py

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from models import db, Company, User, Device, Dashboard
from datetime import datetime

company_bp = Blueprint('company', __name__, url_prefix='/company')


# =========================
# Company Index/Dashboard
# =========================
@company_bp.route('/')
@company_bp.route('/index')
@login_required
def company_index():
    if current_user.role != 'super_admin':
        flash("Access denied.", "danger")
        return redirect(url_for('dashboard.dashboard_list'))
    
    companies = Company.query.all()
    
    # Calculate statistics
    total_users = User.query.count()
    total_devices = Device.query.count()
    total_dashboards = Dashboard.query.count()
    
    # Get counts per company
    company_users = {}
    company_devices = {}
    company_dashboards = {}
    
    for company in companies:
        company_users[company.id] = User.query.filter_by(company_id=company.id).count()
        company_devices[company.id] = Device.query.filter_by(company_id=company.id).count()
        company_dashboards[company.id] = Dashboard.query.filter_by(company_id=company.id).count()
    
    # Get recent companies (last 5 created)
    recent_companies = Company.query.order_by(Company.created_at.desc()).limit(5).all()
    
    return render_template('company/company_index.html',
                         companies=companies,
                         total_users=total_users,
                         total_devices=total_devices,
                         total_dashboards=total_dashboards,
                         company_users=company_users,
                         company_devices=company_devices,
                         company_dashboards=company_dashboards,
                         recent_companies=recent_companies)


# =========================
# List All Companies
# =========================
@company_bp.route('/list')
@login_required
def list_companies():
    if current_user.role != 'super_admin':
        flash("Access denied.", "danger")
        return redirect(url_for('dashboard.dashboard_list'))

    companies = Company.query.all()
    return render_template('company/list_companies.html', companies=companies)


# =========================
# Create Company
# =========================
@company_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_company():
    if current_user.role != 'super_admin':
        flash("Only super admins can create companies.", "danger")
        return redirect(url_for('dashboard.dashboard_list'))

    if request.method == 'POST':
        name = request.form['name']

        existing = Company.query.filter_by(name=name).first()
        if existing:
            flash("Company already exists!", "warning")
            return redirect(url_for('company.create_company'))

        new_company = Company(
            name=name,
            created_at=datetime.utcnow()
        )

        db.session.add(new_company)
        db.session.commit()

        flash(f"Company '{name}' created successfully!", "success")
        return redirect(url_for('company.list_companies'))

    return render_template('company/create_company.html')


# =========================
# View Company Details
# =========================
@company_bp.route('/<int:company_id>')
@login_required
def view_company(company_id):
    if current_user.role != 'super_admin':
        flash("Access denied.", "danger")
        return redirect(url_for('dashboard.dashboard_list'))

    company = Company.query.get_or_404(company_id)

    users = User.query.filter_by(company_id=company_id).all()
    devices = Device.query.filter_by(company_id=company_id).all()
    dashboards = Dashboard.query.filter_by(company_id=company_id).all()

    return render_template(
        'company/view_company.html',
        company=company,
        users=users,
        devices=devices,
        dashboards=dashboards
    )


# =========================
# Edit Company
# =========================
@company_bp.route('/<int:company_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_company(company_id):
    if current_user.role != 'super_admin':
        flash("Access denied.", "danger")
        return redirect(url_for('dashboard.dashboard_list'))

    company = Company.query.get_or_404(company_id)

    if request.method == 'POST':
        company.name = request.form['name']
        db.session.commit()

        flash("Company updated successfully!", "success")
        return redirect(url_for('company.list_companies'))

    return render_template('company/edit_company.html', company=company)


# =========================
# Delete Company
# =========================
@company_bp.route('/<int:company_id>/delete')
@login_required
def delete_company(company_id):
    if current_user.role != 'super_admin':
        flash("Access denied.", "danger")
        return redirect(url_for('dashboard.dashboard_list'))

    company = Company.query.get_or_404(company_id)

    db.session.delete(company)
    db.session.commit()

    flash("Company deleted successfully!", "success")
    return redirect(url_for('company.list_companies'))


# =========================
# Manage Company Admins
# =========================
@company_bp.route('/<int:company_id>/admins', methods=['GET'])
@login_required
def manage_admins(company_id):
    if current_user.role != 'super_admin':
        flash("Access denied.", "danger")
        return redirect(url_for('dashboard.dashboard_list'))
    
    company = Company.query.get_or_404(company_id)
    admins = User.query.filter_by(company_id=company_id, role='admin').all()
    regular_users = User.query.filter_by(company_id=company_id, role='user').all()
    
    return render_template('company/manage_admins.html', 
                         company=company, 
                         admins=admins, 
                         regular_users=regular_users)


# =========================
# Add Company Admin
# =========================
@company_bp.route('/<int:company_id>/admins/add', methods=['POST'])
@login_required
def add_admin(company_id):
    if current_user.role != 'super_admin':
        flash("Access denied.", "danger")
        return redirect(url_for('dashboard.dashboard_list'))
    
    company = Company.query.get_or_404(company_id)
    email = request.form.get('email')
    
    if not email:
        flash("Please provide an email address.", "danger")
        return redirect(url_for('company.manage_admins', company_id=company_id))
    
    user = User.query.filter_by(email=email).first()
    if not user:
        flash(f"User with email '{email}' not found.", "danger")
        return redirect(url_for('company.manage_admins', company_id=company_id))
    
    if user.company_id != company_id:
        flash(f"User '{email}' does not belong to this company.", "danger")
        return redirect(url_for('company.manage_admins', company_id=company_id))
    
    if user.role == 'admin':
        flash(f"User '{email}' is already an admin.", "warning")
        return redirect(url_for('company.manage_admins', company_id=company_id))
    
    user.role = 'admin'
    db.session.commit()
    
    flash(f"{user.email} is now an admin for {company.name}.", "success")
    return redirect(url_for('company.manage_admins', company_id=company_id))


# =========================
# Remove Company Admin
# =========================
@company_bp.route('/<int:company_id>/admins/<int:user_id>/remove', methods=['POST'])
@login_required
def remove_admin(company_id, user_id):
    if current_user.role != 'super_admin':
        flash("Access denied.", "danger")
        return redirect(url_for('dashboard.dashboard_list'))
    
    company = Company.query.get_or_404(company_id)
    user = User.query.get_or_404(user_id)
    
    if user.company_id != company_id:
        flash("User does not belong to this company.", "danger")
        return redirect(url_for('company.manage_admins', company_id=company_id))
    
    if user.id == current_user.id:
        flash("You cannot remove yourself as admin.", "danger")
        return redirect(url_for('company.manage_admins', company_id=company_id))
    
    if user.role != 'admin':
        flash(f"User '{user.email}' is not an admin.", "warning")
        return redirect(url_for('company.manage_admins', company_id=company_id))
    
    user.role = 'user'
    db.session.commit()
    
    flash(f"{user.email} is no longer an admin for {company.name}.", "success")
    return redirect(url_for('company.manage_admins', company_id=company_id))