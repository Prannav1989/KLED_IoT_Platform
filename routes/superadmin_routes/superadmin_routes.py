from flask import Blueprint, render_template, redirect, url_for, flash, jsonify, request, current_app
from flask_login import login_required, current_user
from datetime import datetime, timedelta, timezone
import json
import traceback
from sqlalchemy import func

# Import all models at once
from models import (
    Device, User, SensorData, AuditLog, db, 
    MQTTConfig, Parameter, Company, SensorModel, DashboardSensor
)

from werkzeug.security import generate_password_hash

superadmin_bp = Blueprint('superadmin', __name__, url_prefix='/superadmin')
print("🔍 DEBUG: Superadmin blueprint loaded!")

# ============ HELPER FUNCTIONS ============

def calculate_device_status(device):
    """Calculate device status based on is_active and last_seen"""
    if not device or not device.is_active:
        return "inactive"
    elif device.last_seen:
        time_diff = (datetime.utcnow() - device.last_seen).total_seconds()
        return "online" if time_diff < 300 else "offline"  # 5 minutes
    else:
        return "offline"

# Register as template global
@superadmin_bp.app_template_global()
def calculate_device_status_global(device):
    """Template global version of calculate_device_status"""
    return calculate_device_status(device)

def normalize_datetime(dt):
    """Normalize datetime for comparison"""
    if dt is None:
        return None
    if hasattr(dt, 'tzinfo') and dt.tzinfo is not None:
        # Convert to naive UTC
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    else:
        # Already naive, assume UTC
        return dt

def attach_model_parameters_to_device(device_id, sensor_model_id, created_by_user_id=None):
    """
    Create Parameter rows for a device based on the SensorModel.parameters JSON.
    Returns number of parameters created or raises an exception.
    """
    device = Device.query.get(device_id)
    model = SensorModel.query.get(sensor_model_id)
    
    if not device:
        raise ValueError("Device not found")
    if not model:
        raise ValueError("Sensor model not found")

    params = model.parameters or []
    created_count = 0
    
    for p in params:
        # each p should be a dict with keys: parameter_name, parameter_type, unit, etc.
        param_name = p.get('parameter_name') or p.get('name') or 'Unnamed'
        param_type = p.get('parameter_type') or p.get('type') or 'numeric'
        unit = p.get('unit') or ''

        # Create Parameter
        parameter = Parameter(
            name=param_name,
            sensor_type=param_type,
            unit=unit,
            device_id=device.id,
            user_id=created_by_user_id or device.user_id,
            created_at=datetime.utcnow()
        )
        db.session.add(parameter)
        created_count += 1

    db.session.commit()
    return created_count

def get_device_status_summary():
    """Get device status counts"""
    devices = Device.query.all()
    status_counts = {
        'online': 0,
        'offline': 0,
        'inactive': 0,
        'total': len(devices)
    }
    
    for device in devices:
        status = calculate_device_status(device)
        status_counts[status] += 1
    
    return status_counts

def get_grouped_sensor_data():
    """Get parameters grouped by device - simplified version"""
    try:
        devices = Device.query.all()
        grouped_data = []

        for device in devices:
            parameters = Parameter.query.filter_by(device_id=device.id).all()
            param_list = []
            has_data = False

            for param in parameters:
                # Get latest sensor data for this parameter
                latest_data = SensorData.query.filter_by(
                    device_id=device.id,
                    parameter_id=param.id  # Use param.id directly
                ).order_by(SensorData.timestamp.desc()).first()

                if latest_data:
                    has_data = True
                    param_list.append({
                        "name": param.name or "Unnamed",
                        "value": latest_data.value,
                        "unit": latest_data.unit or param.unit or "",
                        "timestamp": latest_data.timestamp.isoformat() if latest_data.timestamp else None,
                        "parameter_id": param.id
                    })
                else:
                    param_list.append({
                        "name": param.name or "Unnamed",
                        "value": None,
                        "unit": param.unit or "",
                        "timestamp": None,
                        "parameter_id": param.id
                    })

            grouped_data.append({
                "device_id": device.id,
                "device_name": device.name,
                "parameters": param_list,
                "has_data": has_data,
                "status": calculate_device_status(device)
            })

        return grouped_data

    except Exception as e:
        current_app.logger.error(f"ERROR in get_grouped_sensor_data: {str(e)}", exc_info=True)
        return []

# ============ DASHBOARD ROUTES ============

@superadmin_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.role != 'super_admin':
        flash('Access denied. Super admin privileges required.', 'danger')
        return redirect(url_for('auth.login'))

    try:
        # Get device status summary
        status_counts = get_device_status_summary()
        
        # Other stats
        total_users = User.query.count()
        total_sensors = Parameter.query.count()
        total_readings = SensorData.query.count()
        total_companies = Company.query.count()
        
        # Active counts
        active_users = User.query.filter_by(active_status=True).count() if hasattr(User, 'active_status') else 0
        
        # Recent readings (last 24 hours)
        twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
        recent_readings_count = SensorData.query.filter(
            SensorData.timestamp >= twenty_four_hours_ago
        ).count()

        # Grouped sensors
        grouped_sensors = get_grouped_sensor_data()

        # Recent data for tables
        recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
        recent_devices = Device.query.order_by(Device.created_at.desc()).limit(5).all()
        
        # Sensor data with names
        recent_sensor_data = db.session.query(
            SensorData,
            Parameter.name.label('sensor_name'),
            Parameter.unit.label('unit'),
            Device.device_id.label('device_id'),
            Device.name.label('device_name')
        ).join(
            Parameter, SensorData.parameter_id == Parameter.id
        ).join(
            Device, Parameter.device_id == Device.id
        ).order_by(
            SensorData.timestamp.desc()
        ).limit(10).all()

        # Users by role (for Chart)
        users_by_role = (
            db.session.query(User.role, func.count(User.id).label('count'))
            .group_by(User.role)
            .all()
        )

        # Device status for chart
        device_status = {"active": status_counts['online'], "inactive": status_counts['inactive'] + status_counts['offline']}

        # Stats dictionary
        stats = {
            "total_users": total_users,
            "active_users": active_users,
            "total_devices": status_counts['total'],
            "active_devices": status_counts['online'],
            "total_companies": total_companies,
            "total_sensor_data": total_readings,
            "recent_readings_count": recent_readings_count,
            "total_sensors": total_sensors,
            "offline_devices": status_counts['offline'],
            "inactive_devices": status_counts['inactive']
        }

        # Debug print
        current_app.logger.debug(f"DASHBOARD STATS: {stats}")

        # Render template
        return render_template(
            "superadmin_dashboard/dashboard.html",
            stats=stats,
            recent_users=recent_users,
            recent_devices=recent_devices,
            recent_sensor_data=recent_sensor_data,
            users_by_role=users_by_role,
            device_status=device_status,
            grouped_sensors=grouped_sensors,
            active_page='dashboard',
            now=datetime.utcnow()
        )

    except Exception as e:
        current_app.logger.error(f"ERROR in dashboard: {str(e)}", exc_info=True)
        flash("Error loading dashboard data", "danger")
        
        # Safe fallback
        stats = {
            "total_users": 0,
            "active_users": 0,
            "total_devices": 0,
            "active_devices": 0,
            "total_companies": 0,
            "total_sensor_data": 0,
            "recent_readings_count": 0,
            "total_sensors": 0,
            "offline_devices": 0,
            "inactive_devices": 0
        }

        return render_template(
            "superadmin_dashboard/dashboard.html",
            stats=stats,
            recent_users=[],
            recent_devices=[],
            recent_sensor_data=[],
            users_by_role=[],
            device_status={"active": 0, "inactive": 0},
            grouped_sensors=[],
            active_page='dashboard',
            now=datetime.utcnow()
        )

@superadmin_bp.route('/api/dashboard-data')
@login_required
def dashboard_data():
    if current_user.role != 'super_admin':
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        status_counts = get_device_status_summary()
        
        total_users = User.query.count()
        total_sensors = Parameter.query.count()
        total_readings = SensorData.query.count()
        
        twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
        recent_readings_count = SensorData.query.filter(
            SensorData.timestamp >= twenty_four_hours_ago
        ).count()
        
        grouped_sensors = get_grouped_sensor_data()
        
        return jsonify({
            'total_devices': status_counts['total'],
            'online_devices_count': status_counts['online'],
            'offline_devices_count': status_counts['offline'],
            'inactive_devices_count': status_counts['inactive'],
            'total_users': total_users,
            'total_sensors': total_sensors,
            'total_readings': total_readings,
            'recent_readings_count': recent_readings_count,
            'grouped_sensors': grouped_sensors
        })
        
    except Exception as e:
        current_app.logger.error(f"ERROR in dashboard_data API: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

# ============ USER MANAGEMENT ============

@superadmin_bp.route('/users', methods=['GET', 'POST'])
@login_required
def manage_users():
    if current_user.role != 'super_admin':
        flash('Access denied. Super admin privileges required.', 'danger')
        return redirect(url_for('auth.login'))
    
    # Get all users
    users = User.query.all()
    companies = Company.query.all()
    admins = User.query.filter(User.role.in_(['admin', 'super_admin'])).all()
    
    # Handle form submission for adding a new user
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        role = request.form.get('role', 'user')
        company_id = request.form.get('company_id') or None
        parent_admin_id = request.form.get('parent_admin_id') or None
        
        # Validation
        if not username or not email or not password:
            flash('Username, email and password are required', 'danger')
            return redirect(url_for('superadmin.manage_users'))
            
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'danger')
            return redirect(url_for('superadmin.manage_users'))
            
        if User.query.filter_by(email=email).first():
            flash('Email already exists', 'danger')
            return redirect(url_for('superadmin.manage_users'))
        
        # Create new user
        new_user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            role=role,
            company_id=company_id,
            parent_admin_id=parent_admin_id,
            active_status=True,
            created_at=datetime.utcnow()
        )
        
        db.session.add(new_user)
        db.session.commit()
        
        flash('User created successfully', 'success')
        return redirect(url_for('superadmin.manage_users'))
    
    return render_template('superadmin_dashboard/users.html', 
                         users=users, 
                         admins=admins,
                         companies=companies)

@superadmin_bp.route('/edit_user/<int:user_id>', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    if current_user.role != 'super_admin':
        flash('Access denied. Super admin privileges required.', 'danger')
        return redirect(url_for('auth.login'))
    
    user = User.query.get_or_404(user_id)
    admins = User.query.filter(User.role.in_(['admin', 'super_admin'])).all()
    companies = Company.query.order_by(Company.name.asc()).all()

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        role = request.form.get('role')
        company_id = request.form.get('company_id') or None
        parent_admin_id = request.form.get('parent_admin_id') or None
        is_active = 'is_active' in request.form

        # Validation
        if User.query.filter(User.username == username, User.id != user.id).first():
            flash('Username already exists', 'danger')
            return redirect(url_for('superadmin.edit_user', user_id=user.id))
            
        if User.query.filter(User.email == email, User.id != user.id).first():
            flash('Email already exists', 'danger')
            return redirect(url_for('superadmin.edit_user', user_id=user.id))
        
        user.username = username
        user.email = email
        user.role = role
        user.company_id = company_id
        user.parent_admin_id = parent_admin_id
        user.active_status = is_active
        
        password = request.form.get('password', '').strip()
        if password:
            user.password_hash = generate_password_hash(password)
        
        db.session.commit()
        flash('User updated successfully', 'success')
        return redirect(url_for('superadmin.manage_users'))
    
    return render_template(
        'superadmin_dashboard/edit_user.html',
        user=user,
        admins=admins,
        companies=companies
    )

@superadmin_bp.route('/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if current_user.role != 'super_admin':
        flash('Access denied. Super admin privileges required.', 'danger')
        return redirect(url_for('auth.login'))
    
    user = User.query.get_or_404(user_id)
    
    # Prevent self-deletion
    if user.id == current_user.id:
        flash('You cannot delete your own account', 'danger')
        return redirect(url_for('superadmin.manage_users'))
    
    db.session.delete(user)
    db.session.commit()
    
    flash('User deleted successfully', 'success')
    return redirect(url_for('superadmin.manage_users'))

# ============ DEVICE MANAGEMENT ============

@superadmin_bp.route('/devices')
@login_required
def device_management():
    if current_user.role != 'super_admin':
        flash('Access denied', 'danger')
        return redirect(url_for('auth.login'))

    try:
        # Get comprehensive device data with sensor model info
        devices_data = db.session.query(
            Device,
            User.username.label('owner'),
            Company.name.label('company_name'),
            MQTTConfig.name.label('mqtt_config_name'),
            SensorModel.name.label('sensor_model_name'),
            func.count(func.distinct(Parameter.id)).label('parameter_count'),
            func.count(func.distinct(SensorData.id)).label('data_count')
        ).select_from(Device)\
         .outerjoin(User, Device.user_id == User.id)\
         .outerjoin(Company, Device.company_id == Company.id)\
         .outerjoin(MQTTConfig, Device.mqtt_config_id == MQTTConfig.id)\
         .outerjoin(SensorModel, Device.sensor_model_id == SensorModel.id)\
         .outerjoin(Parameter, Parameter.device_id == Device.id)\
         .outerjoin(SensorData, SensorData.device_id == Device.id)\
         .group_by(Device.id, User.username, Company.name, MQTTConfig.name, SensorModel.name)\
         .order_by(Device.created_at.desc())\
         .all()

        # Get sensor models for the add device dropdown
        sensor_models = SensorModel.query.all()
        
        # Calculate stats
        status_counts = get_device_status_summary()
        total_users = User.query.count()
        total_companies = Company.query.count()
        total_readings = SensorData.query.count()

        stats = {
            "total_users": total_users,
            "active_users": User.query.filter_by(active_status=True).count() if hasattr(User, 'active_status') else total_users,
            "total_devices": status_counts['total'],
            "active_devices": status_counts['online'],
            "non_active_devices": status_counts['offline'] + status_counts['inactive'],
            "total_companies": total_companies,
            "total_sensor_data": total_readings,
        }

        return render_template('superadmin_dashboard/devices.html', 
                             devices=devices_data, 
                             stats=stats,
                             sensor_models=sensor_models,
                             now=datetime.utcnow()
                             )
                             
    except Exception as e:
        current_app.logger.error(f"ERROR in device_management: {str(e)}", exc_info=True)
        flash("Error loading devices", "danger")
        
        # Fallback
        stats = {
            "total_users": 0,
            "active_users": 0,
            "total_devices": 0,
            "active_devices": 0,
            "non_active_devices": 0,
            "total_companies": 0,
            "total_sensor_data": 0,
        }
        sensor_models = SensorModel.query.all()
        return render_template('superadmin_dashboard/devices.html', 
                             devices=[], 
                             stats=stats,
                             sensor_models=sensor_models,
                             now=datetime.utcnow()
                             )

@superadmin_bp.route('/devices/add', methods=['GET'])
@login_required
def add_device_form():
    if current_user.role != 'super_admin':
        flash('Access denied', 'danger')
        return redirect(url_for('auth.login'))
    
    try:
        # Get all sensor models
        sensor_models = SensorModel.query.all()
        # Get all MQTT configs
        mqtt_configs = MQTTConfig.query.all()
        # Get all companies for dropdown
        companies = Company.query.all()
        # Get all users for owner dropdown
        users = User.query.all()
        
        return render_template('superadmin_dashboard/add_device.html',
                             sensor_models=sensor_models,
                             mqtt_configs=mqtt_configs,
                             companies=companies,
                             users=users)
    except Exception as e:
        current_app.logger.error(f"ERROR in add_device_form: {str(e)}", exc_info=True)
        flash("Error loading add device form", "danger")
        return redirect(url_for('superadmin.device_management'))

@superadmin_bp.route('/devices', methods=['POST'])
@login_required
def create_device():
    if current_user.role != 'super_admin':
        flash('Access denied', 'danger')
        return redirect(url_for('auth.login'))
    
    try:
        # Get form data
        name = request.form.get('name', '').strip()
        device_id = request.form.get('device_id', '').strip()  # Device EUI
        mqtt_topic = request.form.get('mqtt_topic', '').strip()
        description = request.form.get('description', '').strip()
        mqtt_config_id = request.form.get('mqtt_config_id') or None
        company_id = request.form.get('company_id') or None
        user_id = request.form.get('user_id') or None
        sensor_model_id = request.form.get('sensor_model_id') or None
        
        # Validate required fields
        if not name or not device_id:
            flash('Device name and Device ID are required', 'danger')
            return redirect(url_for('superadmin.add_device_form'))
        
        # Check if device_id already exists
        existing_device = Device.query.filter_by(device_id=device_id).first()
        if existing_device:
            flash('Device ID already exists', 'danger')
            return redirect(url_for('superadmin.add_device_form'))
        
        # Create new device
        new_device = Device(
            name=name,
            device_id=device_id,
            mqtt_topic=mqtt_topic,
            description=description,
            mqtt_config_id=mqtt_config_id,
            company_id=company_id,
            user_id=user_id,
            sensor_model_id=sensor_model_id,
            is_active=True,
            created_at=datetime.utcnow(),
            last_seen=datetime.utcnow()
        )
        
        db.session.add(new_device)
        db.session.commit()
        
        # If sensor model is selected, create parameters from the model
        if sensor_model_id:
            try:
                parameters_created = attach_model_parameters_to_device(new_device.id, sensor_model_id, current_user.id)
                flash(f'Device "{name}" created successfully with {parameters_created} parameters from sensor model', 'success')
            except Exception as e:
                current_app.logger.error(f"Warning: Could not create parameters from sensor model: {e}")
                flash(f'Device "{name}" created but failed to create parameters from sensor model: {e}', 'warning')
        else:
            flash(f'Device "{name}" created successfully without sensor model', 'success')
        
        return redirect(url_for('superadmin.device_management'))
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"ERROR creating device: {str(e)}", exc_info=True)
        flash(f'Error creating device: {str(e)}', 'danger')
        return redirect(url_for('superadmin.add_device_form'))

@superadmin_bp.route('/devices/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_device(id):
    if current_user.role != 'super_admin':
        flash('Access denied', 'danger')
        return redirect(url_for('auth.login'))

    device = Device.query.get_or_404(id)

    # Get dropdown data
    mqtt_configs = MQTTConfig.query.all()
    sensor_models = SensorModel.query.all()
    users = User.query.all()
    companies = Company.query.all()

    # Get related data
    device_mqtt_config = MQTTConfig.query.get(device.mqtt_config_id) if device.mqtt_config_id else None
    device_sensor_model = SensorModel.query.get(device.sensor_model_id) if device.sensor_model_id else None

    # Get counts
    sensor_data_count = SensorData.query.filter_by(device_id=device.id).count()
    last_reading = SensorData.query.filter_by(device_id=device.id) \
        .order_by(SensorData.timestamp.desc()) \
        .first()

    # Time normalization
    now = datetime.utcnow()

    if device.last_seen:
        last_seen = normalize_datetime(device.last_seen)
    else:
        last_seen = None

    if last_reading and last_reading.timestamp:
        last_reading_time = normalize_datetime(last_reading.timestamp)
    else:
        last_reading_time = None

    # Parameter details for this device
    parameters = Parameter.query.filter_by(device_id=device.id).all()

    # Last reading per parameter
    parameter_last_readings = {}
    for parameter in parameters:
        latest = SensorData.query.filter_by(
            device_id=device.id, 
            parameter_id=parameter.id
        ).order_by(SensorData.timestamp.desc()).first()

        if latest and latest.timestamp:
            ts = normalize_datetime(latest.timestamp)
        else:
            ts = None

        parameter_last_readings[parameter.id] = {
            'value': latest.value if latest else None,
            'unit': latest.unit if latest else None,
            'timestamp': ts,
            'parameter_name': parameter.name,
            'parameter_type': parameter.sensor_type
        }

    # ----------------------------------------
    # POST: UPDATE DEVICE
    # ----------------------------------------
    if request.method == 'POST':
        # Get the original sensor model ID before update
        original_model_id = device.sensor_model_id
        
        # Update device fields
        device.name = request.form.get('name', '').strip()
        device.device_id = request.form.get('device_id', '').strip()
        device.mqtt_topic = request.form.get('mqtt_topic', '').strip()
        device.description = request.form.get('description', '').strip()
        device.mqtt_config_id = request.form.get('mqtt_config_id') or None
        device.company_id = request.form.get('company_id') or None
        device.user_id = request.form.get('user_id') or None
        new_sensor_model_id = request.form.get('sensor_model_id') or None
        device.sensor_model_id = new_sensor_model_id
        device.is_active = 'is_active' in request.form
        
        # Check if sensor model changed
        model_changed = (
            (original_model_id is None and new_sensor_model_id is not None) or
            (original_model_id is not None and new_sensor_model_id is None) or
            (original_model_id and new_sensor_model_id and str(original_model_id) != str(new_sensor_model_id))
        )
        
        if model_changed:
            # Delete existing parameters for this device
            Parameter.query.filter_by(device_id=device.id).delete()
            
            # If new model selected, create parameters from it
            if new_sensor_model_id:
                try:
                    parameters_created = attach_model_parameters_to_device(
                        device.id, 
                        new_sensor_model_id, 
                        current_user.id
                    )
                    flash(f'Device updated successfully. {parameters_created} parameters created from new model.', 'success')
                except Exception as e:
                    flash(f'Device updated but failed to create parameters from model: {e}', 'warning')
            else:
                flash('Device updated. Sensor model removed and all parameters deleted.', 'success')
        else:
            flash('Device updated successfully', 'success')
        
        db.session.commit()
        return redirect(url_for('superadmin.device_management'))
    
    # ----------------------------------------
    # RENDER TEMPLATE
    # ----------------------------------------
    return render_template(
        'superadmin_dashboard/edit_device.html',
        device=device,
        mqtt_configs=mqtt_configs,
        sensor_models=sensor_models,
        users=users,
        companies=companies,
        device_mqtt_config=device_mqtt_config,
        device_sensor_model=device_sensor_model,
        sensor_data_count=sensor_data_count,
        last_seen=last_seen,
        last_reading=last_reading,
        last_reading_time=last_reading_time,
        now=now,
        parameters=parameters,
        parameter_last_readings=parameter_last_readings
    )

@superadmin_bp.route('/devices/<int:id>/delete', methods=['POST'])
@login_required
def delete_device(id):
    if current_user.role != 'super_admin':
        flash('Access denied', 'danger')
        return redirect(url_for('auth.login'))

    device = Device.query.get_or_404(id)

    try:
        # Delete dashboard mappings
        DashboardSensor.query.filter(
            DashboardSensor.device_id == device.id
        ).delete(synchronize_session=False)

        # Delete parameters linked to device
        Parameter.query.filter(
            Parameter.device_id == device.id
        ).delete(synchronize_session=False)

        # Delete sensor data
        SensorData.query.filter(
            SensorData.device_id == device.id
        ).delete(synchronize_session=False)

        # Now delete device
        db.session.delete(device)
        db.session.commit()

        flash('Device deleted successfully', 'success')
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"ERROR deleting device: {str(e)}", exc_info=True)
        flash('Error deleting device', 'danger')

    return redirect(url_for('superadmin.device_management'))

# ============ SENSOR MODEL MANAGEMENT ============

@superadmin_bp.route('/sensor-models')
@login_required
def manage_sensor_models():
    if current_user.role != 'super_admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('auth.login'))
    
    search = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 20

    query = SensorModel.query

    if search:
        query = query.filter(
            db.or_(
                SensorModel.name.ilike(f'%{search}%'),
                SensorModel.manufacturer.ilike(f'%{search}%'),
                SensorModel.description.ilike(f'%{search}%')
            )
        )

    query = query.order_by(SensorModel.created_at.desc())
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    # Build JSON-serializable list
    sensor_models_json = []
    for m in paginated.items:
        sensor_models_json.append({
            'id': m.id,
            'name': m.name,
            'manufacturer': m.manufacturer,
            'description': m.description,
            'parameters': m.parameters or [],
            'created_at': m.created_at.isoformat() if m.created_at else None
        })

    stats = {
        'total_models': SensorModel.query.count(),
        'total_manufacturers': db.session.query(SensorModel.manufacturer).distinct().count(),
        'total_sensors': 0
    }

    return render_template(
        'superadmin_dashboard/sensor_model.html',
        sensor_models=paginated.items,
        sensor_models_json=sensor_models_json,
        pagination=paginated,
        stats=stats,
        search=search
    )

@superadmin_bp.route('/sensor-models/add', methods=['POST'])
@login_required
def add_sensor_model():
    if current_user.role != 'super_admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('auth.login'))
    
    try:
        name = request.form.get('name', '').strip()
        manufacturer = request.form.get('manufacturer', '').strip()
        description = request.form.get('description', '').strip()
        parameters_raw = request.form.get('parameters', '[]')  # JSON text from form

        if not name:
            flash("Model name is required", "error")
            return redirect(url_for('superadmin.manage_sensor_models'))

        # Check duplicate model
        existing = SensorModel.query.filter_by(name=name).first()
        if existing:
            flash(f'Model "{name}" already exists.', 'error')
            return redirect(url_for('superadmin.manage_sensor_models'))

        # Parse parameters JSON
        try:
            parameters = json.loads(parameters_raw)
            if not isinstance(parameters, list):
                parameters = []
        except json.JSONDecodeError:
            parameters = []

        new_model = SensorModel(
            name=name,
            manufacturer=manufacturer,
            description=description,
            parameters=parameters,
            created_at=datetime.utcnow()
        )

        db.session.add(new_model)
        db.session.commit()
        flash(f'Sensor model "{name}" added successfully.', 'success')

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"ERROR adding sensor model: {str(e)}", exc_info=True)
        flash(f"Error: {e}", "error")

    return redirect(url_for('superadmin.manage_sensor_models'))

@superadmin_bp.route('/sensor-models/edit/<int:model_id>', methods=['POST'])
@login_required
def edit_sensor_model(model_id):
    if current_user.role != 'super_admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('auth.login'))

    sensor_model = SensorModel.query.get_or_404(model_id)

    try:
        sensor_model.name = request.form.get('name', sensor_model.name).strip()
        sensor_model.manufacturer = request.form.get('manufacturer', sensor_model.manufacturer).strip()
        sensor_model.description = request.form.get('description', sensor_model.description).strip()

        # Update parameters JSON
        parameters_raw = request.form.get('parameters')
        if parameters_raw:
            try:
                sensor_model.parameters = json.loads(parameters_raw)
            except json.JSONDecodeError:
                pass

        db.session.commit()
        flash("Sensor model updated successfully.", "success")

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"ERROR updating sensor model: {str(e)}", exc_info=True)
        flash(f"Error updating model: {e}", "error")

    return redirect(url_for('superadmin.manage_sensor_models'))

@superadmin_bp.route('/sensor-models/delete/<int:model_id>', methods=['DELETE'])
@login_required
def delete_sensor_model(model_id):
    if current_user.role != 'super_admin':
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        sensor_model = SensorModel.query.get_or_404(model_id)

        db.session.delete(sensor_model)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Model deleted successfully'})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"ERROR deleting sensor model: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500

@superadmin_bp.route('/api/sensor-model/<int:model_id>/parameters')
@login_required
def get_sensor_model_parameters(model_id):
    if current_user.role != 'super_admin':
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        model = SensorModel.query.get_or_404(model_id)
        
        # Parse parameters from sensor model
        parameters_list = []
        if model.parameters:
            if isinstance(model.parameters, list):
                parameters_list = model.parameters
            elif isinstance(model.parameters, str):
                try:
                    parameters_list = json.loads(model.parameters)
                except json.JSONDecodeError:
                    # Handle comma-separated format
                    parameters_list = [
                        {"name": p.strip(), "type": "generic", "unit": ""} 
                        for p in model.parameters.split(',') if p.strip()
                    ]
        
        return jsonify({
            'success': True,
            'model_name': model.name,
            'manufacturer': model.manufacturer,
            'parameters': parameters_list,
            'parameter_count': len(parameters_list),
            'description': model.description
        })
    except Exception as e:
        current_app.logger.error(f"ERROR fetching sensor model parameters: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

# ============ PARAMETER LIBRARY ============

@superadmin_bp.route('/parameters/api', methods=['GET'])
@login_required
def get_parameter_library():
    """Get all unique parameters from existing sensor models"""
    if current_user.role != 'super_admin':
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        # Get all sensor models
        sensor_models = SensorModel.query.all()
        
        # Extract unique parameters from all models
        unique_params = {}
        
        for model in sensor_models:
            if model.parameters and isinstance(model.parameters, list):
                for param in model.parameters:
                    if isinstance(param, dict):
                        # Get parameter name - try different possible keys
                        param_name = None
                        for key in ['parameter_name', 'name', 'parameter', 'param_name']:
                            if key in param and param[key]:
                                param_name = str(param[key]).strip()
                                break
                        
                        if param_name:
                            # Use as unique key
                            if param_name not in unique_params:
                                # Extract other fields with fallbacks
                                sensor_type = None
                                for key in ['parameter_type', 'sensor_type', 'type', 'data_type']:
                                    if key in param and param[key]:
                                        sensor_type = str(param[key]).strip()
                                        break
                                
                                unit = param.get('unit', '') or param.get('units', '')
                                mqtt_field = param.get('mqtt_field_name', '') or param.get('mqtt_field', '') or param.get('field_name', '')
                                
                                unique_params[param_name] = {
                                    'name': param_name,
                                    'sensor_type': sensor_type or '',
                                    'unit': str(unit).strip() if unit else '',
                                    'mqtt_field_name': str(mqtt_field).strip() if mqtt_field else ''
                                }
        
        # Convert to list
        parameters_list = list(unique_params.values())
        
        # Sort by name
        parameters_list.sort(key=lambda x: x['name'].lower())
        
        return jsonify({
            'parameters': parameters_list
        })
        
    except Exception as e:
        current_app.logger.error(f"ERROR in get_parameter_library: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@superadmin_bp.route('/parameters/api/add', methods=['POST'])
@login_required
def create_parameter_library():
    """Create a new parameter (just returns it - not saved to database)"""
    if current_user.role != 'super_admin':
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        sensor_type = data.get('sensor_type', '').strip()
        unit = data.get('unit', '').strip()
        mqtt_field_name = data.get('mqtt_field_name', '').strip()
        
        if not name:
            return jsonify({'error': 'Parameter name is required'}), 400
        
        # Don't save to database - just return for frontend use
        return jsonify({
            'message': 'Parameter ready to use',
            'parameter': {
                'name': name,
                'sensor_type': sensor_type,
                'unit': unit,
                'mqtt_field_name': mqtt_field_name
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"ERROR in create_parameter_library: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

# ============ OTHER ROUTES ============

@superadmin_bp.route('/settings')
@login_required
def settings():
    if current_user.role != 'super_admin':
        flash('Access denied. Super admin privileges required.', 'danger')
        return redirect(url_for('auth.login'))
    
    return render_template('superadmin_dashboard/settings.html')

@superadmin_bp.route('/sensors')
@login_required
def sensor_management():
    if current_user.role != 'super_admin':
        flash('Access denied. Super admin privileges required.', 'danger')
        return redirect(url_for('auth.login'))

    # Fetch all parameters (replacing sensors)
    parameters = Parameter.query.all()

    return render_template('superadmin_dashboard/sensors_dashboard.html', sensors=parameters)

@superadmin_bp.route('/audit-logs')
@login_required
def audit_logs():
    if current_user.role != 'super_admin':
        flash('Access denied. Super admin privileges required.', 'danger')
        return redirect(url_for('auth.login'))

    # Fetch all audit logs
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).all()

    return render_template('superadmin_dashboard/audit_logs.html', logs=logs)

@superadmin_bp.route('/companies')
@login_required
def companies_list():
    companies = Company.query.all()
    return render_template(
        'superadmin_dashboard/companies.html',
        companies=companies
    )

@superadmin_bp.route('/sensor-models/stats')
@login_required
def sensor_model_stats():
    if current_user.role != 'super_admin':
        return jsonify({'error': 'Access denied'}), 403
    
    stats = {
        'total_models': SensorModel.query.count(),
        'total_manufacturers': db.session.query(SensorModel.manufacturer).distinct().count(),
        'total_sensors': 0  # Update this if you have a Sensor model
    }
    return jsonify(stats)

@superadmin_bp.route('/sensor-models/<int:model_id>/parameters', methods=['GET'])
@login_required
def sensor_model_parameters_api(model_id):
    if current_user.role != 'super_admin':
        return jsonify({'error': 'Access denied'}), 403

    model = SensorModel.query.get_or_404(model_id)
    params = model.parameters if model.parameters else []
    return jsonify({'model_id': model.id, 'name': model.name, 'parameters': params})