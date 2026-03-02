from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from models import User, Device, MQTTConfig, db,Company
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, SubmitField
from wtforms.validators import DataRequired
from datetime import datetime
from functools import wraps
from werkzeug.security import generate_password_hash
from sqlalchemy.orm import joinedload

# Create blueprint with proper prefix
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Helper function to check admin privileges
def requires_admin(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please login to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        if current_user.role not in ['admin', 'super_admin']:
            flash('Access denied. Admin privileges required.', 'danger')
            return redirect(url_for('device.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# Helper function to check super_admin privileges
def requires_super_admin(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please login to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        if current_user.role != 'super_admin':
            flash('Access denied. Super admin required.', 'danger')
            return redirect(url_for('device.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# forms.py
# forms.py - Make sure your form has the company_id field
class AddDeviceForm(FlaskForm):
    name = StringField('Device Name', validators=[DataRequired()])
    device_id = StringField('Device ID', validators=[DataRequired()])
    mqtt_topic = StringField('MQTT Topic', validators=[DataRequired()])
    mqtt_config_id = SelectField('MQTT Configuration', coerce=int, validators=[DataRequired()])
    user_id = SelectField('User', coerce=int, validators=[DataRequired()])
    company_id = SelectField('Company', coerce=int)  # Add this line
    submit = SubmitField('Add Device')

class UserRoleForm(FlaskForm):
    role = SelectField('Role', choices=[
        ('user', 'User'),
        ('admin', 'Admin'),
        ('super_admin', 'Super Admin')
    ], validators=[DataRequired()])
    submit = SubmitField('Update Role')

# Routes
@admin_bp.route('/dashboard')
@login_required
@requires_admin
def dashboard():
    """Admin Dashboard"""
    try:
        # Admin sees devices they own or manage
        if current_user.role == 'super_admin':
            devices = Device.query.all()  # Super admin sees all devices
        else:
            devices = Device.query.filter_by(user_id=current_user.id).all()
        
        users = User.query.filter_by(is_active=True).all()
        
        return render_template('admin/dashboard.html', 
                             devices=devices, 
                             users=users,
                             current_user=current_user)
    except Exception as e:
        flash('Error loading dashboard', 'danger')
        return redirect(url_for('device.dashboard'))

@admin_bp.route('/devices')
@login_required
@requires_admin
def manage_devices():
    """Device Management - Admin can see devices they manage"""
    try:
        if current_user.role == 'super_admin':
            devices = Device.query.all()  # Super admin sees all
        else:
            devices = Device.query.filter_by(user_id=current_user.id).all()
        
        return render_template('admin/devices.html', devices=devices)
    except Exception as e:
        flash('Error loading devices', 'danger')
        return redirect(url_for('admin.dashboard'))

@admin_bp.route('/devices/add', methods=['GET', 'POST'])
@login_required
@requires_super_admin
def add_device():
    """Add Device - Only super admin"""
    form = AddDeviceForm()
    
    # Dynamically add company_id field if it doesn't exist
    if not hasattr(form, 'company_id'):
        from wtforms import SelectField
        form.company_id = SelectField('Company', coerce=int)
    
    try:
        # Get active users
        active_users = User.query.filter_by(active_status=True).all()
        
        # print(f"DEBUG: Active users found: {len(active_users)}")
        
        # Populate dropdowns
        form.user_id.choices = [(user.id, f"{user.username} ({user.email})") 
                               for user in active_users]
        
        # MQTT Configs
        mqtt_configs = MQTTConfig.query.all()
        form.mqtt_config_id.choices = [(config.id, config.name) for config in mqtt_configs]
        
        # Check if Company model exists and has data
        try:
            companies = Company.query.all()
            print(f"DEBUG: Companies found: {len(companies)}")
            form.company_id.choices = [(0, "No Company")] + [(company.id, company.name) for company in companies]
        except Exception as e:
            print(f"DEBUG: Company model error: {e}")
            # If Company model doesn't exist, provide empty choices
            form.company_id.choices = [(0, "No Companies Available")]
        
        if form.validate_on_submit():
            # Handle company_id - set to None if no company selected or model doesn't exist
            company_id_value = None
            if hasattr(form, 'company_id') and form.company_id.data != 0:
                company_id_value = form.company_id.data
            
            device = Device(
                name=form.name.data,
                device_id=form.device_id.data,
                mqtt_topic=form.mqtt_topic.data,
                mqtt_config_id=form.mqtt_config_id.data,
                user_id=form.user_id.data,
                company_id=company_id_value,
                is_active=True,
                created_at=datetime.utcnow()
            )
            db.session.add(device)
            db.session.commit()
            flash('Device added successfully!', 'success')
            return redirect(url_for('admin.manage_devices'))
            
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding device: {str(e)}', 'danger')
        import traceback
        print(f"ERROR: {traceback.format_exc()}")
    
    return render_template('admin/add_device.html', form=form)


@admin_bp.route('/activate-users')
@login_required
@requires_super_admin
def activate_users():
    """Quick fix: Activate all users"""
    try:
        users = User.query.all()
        for user in users:
            user.is_active = True
            db.session.add(user)
        
        db.session.commit()
        flash(f'Activated {len(users)} users', 'success')
        return redirect(url_for('admin.add_device'))
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
        return redirect(url_for('admin.add_device'))




@admin_bp.route('/devices/edit/<int:device_id>', methods=['GET', 'POST'])
@login_required
@requires_admin
def edit_device(device_id):
    """Edit Device - Admin can edit devices they manage"""
    try:
        device = Device.query.get_or_404(device_id)
        
        # Check if user has permission to edit this device
        if current_user.role != 'super_admin' and device.user_id != current_user.id:
            flash('Access denied. You can only edit your own devices.', 'danger')
            return redirect(url_for('admin.manage_devices'))
        
        if request.method == 'POST':
            device.name = request.form.get('name')
            device.description = request.form.get('description')
            
            # Only super admin can change device ownership
            if current_user.role == 'super_admin':
                user_id = request.form.get('user_id')
                if user_id:
                    device.user_id = user_id
            
            db.session.commit()
            flash("Device updated successfully!", "success")
            return redirect(url_for('admin.manage_devices'))
        
        users = User.query.filter_by(is_active=True).all()
        return render_template('admin/edit_device.html', device=device, users=users)
        
    except Exception as e:
        flash('Error editing device', 'danger')
        return redirect(url_for('admin.manage_devices'))

@admin_bp.route('/devices/delete/<int:device_id>', methods=['POST'])
@login_required
@requires_super_admin  # Only super admin can delete devices
def delete_device(device_id):
    """Delete Device - Only super admin"""
    try:
        device = Device.query.get_or_404(device_id)
        db.session.delete(device)
        db.session.commit()
        flash("Device deleted successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash("Error deleting device", "danger")
    
    return redirect(url_for('admin.manage_devices'))

@admin_bp.route('/mqtt-configs', methods=['GET', 'POST'])
@login_required
@requires_admin
def mqtt_configs():
    """MQTT Configuration Management"""
    try:
        if request.method == 'POST':
            name = request.form['name']
            broker_url = request.form['broker_url']
            port = int(request.form['port'])
            username = request.form.get('username')
            password = request.form.get('password')
            ssl_enabled = 'ssl_enabled' in request.form
            
            config = MQTTConfig(
                name=name,
                broker_url=broker_url,
                port=port,
                username=username,
                password_hash=generate_password_hash(password) if password else None,
                ssl_enabled=ssl_enabled,
                user_id=current_user.id
            )
            
            db.session.add(config)
            db.session.commit()
            flash('MQTT configuration saved successfully!', 'success')
            return redirect(url_for('admin.mqtt_configs'))
        
        # Get configs - admin sees their own, super admin sees all
        if current_user.role == 'super_admin':
            configs = MQTTConfig.query.options(joinedload(MQTTConfig.owner)).all()
        else:
            configs = MQTTConfig.query.options(joinedload(MQTTConfig.owner))\
                .filter_by(user_id=current_user.id).all()
        
        return render_template('admin/mqtt_configs.html', configs=configs)
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('admin.mqtt_configs'))

@admin_bp.route('/users')
@login_required
@requires_super_admin  # Only super admin can manage users
def manage_users():
    """User Management - Only super admin"""
    try:
        users = User.query.order_by(User.created_at.desc()).all()
        return render_template('admin/users.html', users=users)
    except Exception as e:
        flash('Error loading users', 'danger')
        return redirect(url_for('admin.dashboard'))

# Error handlers
@admin_bp.errorhandler(403)
def forbidden(error):
    return render_template('errors/403.html'), 403

@admin_bp.errorhandler(404)
def not_found(error):
    return render_template('errors/404.html'), 404