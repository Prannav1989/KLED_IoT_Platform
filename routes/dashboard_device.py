from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from models import db, Device, SensorData, Dashboard, UserDashboard, DashboardSensor, User, Parameter
from types import SimpleNamespace
from sqlalchemy.orm import joinedload
from datetime import datetime, timedelta, timezone

dashboard_device_bp = Blueprint('dashboard_device', __name__)

def get_navigation_settings(dashboard_id):
    """Get navigation settings for the dashboard"""
    return SimpleNamespace(
        dashboard_management=True,
        reports=True,
        analytics=True,
        download=True,
        support=True,
        settings=True
    )



@dashboard_device_bp.route('/dashboard/<int:dashboard_id>/devices')
@login_required
def device_list(dashboard_id):
    """Show devices linked to user's dashboard via dashboard_sensors table"""
    
    # Check if user has access to this dashboard
    if current_user.role == 'super_admin':
        dashboard = Dashboard.query.get_or_404(dashboard_id)
    else:
        user_dashboard = UserDashboard.query.filter_by(
            user_id=current_user.id, 
            dashboard_id=dashboard_id
        ).first()
        
        if not user_dashboard:
            flash('You do not have access to this dashboard', 'error')
            return redirect(url_for('dashboard.dashboard_list'))
        
        dashboard = Dashboard.query.get_or_404(dashboard_id)
    
    # Get devices allocated to this dashboard via dashboard_sensors table
    devices = Device.query\
        .join(DashboardSensor, Device.id == DashboardSensor.device_id)\
        .filter(DashboardSensor.dashboard_id == dashboard_id)\
        .all()
    
    # Use UTC-aware time for consistency
    online_threshold = datetime.now(timezone.utc) - timedelta(minutes=15)
    
    # Create a list of device data with computed properties
    device_data = []
    
    for device in devices:
        latest_reading = SensorData.query.filter_by(device_id=device.id)\
            .order_by(SensorData.timestamp.desc())\
            .first()
        
        # Compute status
        computed_status = 'offline'
        last_reading_time = None
        
        if latest_reading:
            # Ensure DB timestamp is also timezone-aware
            ts = latest_reading.timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            
            if ts >= online_threshold:
                computed_status = 'online'
            else:
                computed_status = 'offline'
            
            last_reading_time = ts
        
        # Handle location - check what location fields are available
        current_location = "Unknown"
        if latest_reading and (latest_reading.latitude or latest_reading.longitude):
            current_location = f"{latest_reading.latitude:.4f}, {latest_reading.longitude:.4f}"
        else:
            # Check for different possible location attributes in Device model
            if hasattr(device, 'location') and device.location:
                current_location = device.location
            elif hasattr(device, 'device_location') and device.device_location:
                current_location = device.device_location
            elif hasattr(device, 'gps_location') and device.gps_location:
                current_location = device.gps_location
            elif hasattr(device, 'install_location') and device.install_location:
                current_location = device.install_location
            # Add more possible location attribute names as needed
        
        # Get parameters
        parameters = Parameter.query.filter_by(device_id=device.id).all()
        
        # Create device data dictionary
        device_data.append({
            'device': device,
            'computed_status': computed_status,
            'last_reading_time': last_reading_time,
            'current_location': current_location,
            'parameters': parameters
        })
    
    navigation_settings = get_navigation_settings(dashboard_id)
    
    return render_template(
        'dashboard/device_list.html',
        dashboard=dashboard,
        device_data=device_data,
        navigation_settings=navigation_settings,
        current_time=datetime.now(timezone.utc)
    )


@dashboard_device_bp.route('/dashboard/<int:dashboard_id>/devices/<int:device_id>')
@login_required
def device_detail(dashboard_id, device_id):
    """Show detailed view of a specific device in a dashboard"""

    # ================= ACCESS CHECK =================
    if current_user.role != 'super_admin':
        user_dashboard = UserDashboard.query.filter_by(
            user_id=current_user.id,
            dashboard_id=dashboard_id
        ).first()

        if not user_dashboard:
            flash('You do not have access to this dashboard', 'error')
            return redirect(url_for('dashboard.dashboard_list'))

    # ================= DASHBOARD DEVICE CHECK =================
    dashboard_sensor = DashboardSensor.query.filter_by(
        dashboard_id=dashboard_id,
        device_id=device_id
    ).first()

    if not dashboard_sensor:
        flash('This device is not allocated to the selected dashboard', 'error')
        return redirect(
            url_for('dashboard_device.device_list', dashboard_id=dashboard_id)
        )

    # ================= DEVICE =================
    device = Device.query.get_or_404(device_id)

    # ================= SENSOR DATA =================
    sensor_data = (
        SensorData.query
        .filter_by(device_id=device_id)
        .order_by(SensorData.timestamp.desc())
        .limit(50)
        .all()
    )

    # ================= PARAMETERS =================
    parameters = Parameter.query.filter_by(device_id=device_id).all()

    # ================= ONLINE STATUS (FIXED) =================
    online_threshold = datetime.now(timezone.utc) - timedelta(minutes=15)

    latest_reading = (
        SensorData.query
        .filter_by(device_id=device_id)
        .order_by(SensorData.timestamp.desc())
        .first()
    )

    latest_ts = latest_reading.timestamp if latest_reading else None

    # 🔐 Normalize timestamp to UTC if DB returned naive datetime
    if latest_ts and latest_ts.tzinfo is None:
        latest_ts = latest_ts.replace(tzinfo=timezone.utc)

    computed_status = (
        'online'
        if latest_ts and latest_ts >= online_threshold
        else 'offline'
    )

    last_reading_time = latest_ts

    # ================= NAVIGATION =================
    navigation_settings = get_navigation_settings(dashboard_id)

    # ================= RENDER =================
    return render_template(
        'dashboard/device_detail.html',
        dashboard_id=dashboard_id,
        device=device,
        sensor_data=sensor_data,
        parameters=parameters,
        computed_status=computed_status,
        last_reading_time=last_reading_time,
        navigation_settings=navigation_settings
    )

# API endpoint to get device data
@dashboard_device_bp.route('/api/dashboard/<int:dashboard_id>/devices/<int:device_id>/data')
@login_required
def device_data(dashboard_id, device_id):
    """API endpoint to get device sensor data"""
    
    # Check access
    if current_user.role != 'super_admin':
        user_dashboard = UserDashboard.query.filter_by(
            user_id=current_user.id, 
            dashboard_id=dashboard_id
        ).first()
        if not user_dashboard:
            return jsonify({'error': 'Access denied'}), 403
    
    # Check if device is in dashboard
    dashboard_sensor = DashboardSensor.query.filter_by(
        dashboard_id=dashboard_id,
        device_id=device_id
    ).first()
    
    if not dashboard_sensor:
        return jsonify({'error': 'Device not found in dashboard'}), 404
    
    # Get sensor data with optional time range
    limit = request.args.get('limit', 100, type=int)
    hours = request.args.get('hours', 24, type=int)
    
    time_threshold = datetime.now(timezone.utc) - timedelta(hours=hours)
    
    sensor_data = SensorData.query.filter(
        SensorData.device_id == device_id,
        SensorData.timestamp >= time_threshold
    ).order_by(SensorData.timestamp.desc())\
     .limit(limit)\
     .all()
    
    data = [{
        'id': sd.id,
        'parameter_type': sd.parameter_type,
        'value': sd.value,
        'unit': sd.unit,
        'timestamp': sd.timestamp.isoformat(),
        'latitude': sd.latitude,
        'longitude': sd.longitude
    } for sd in sensor_data]
    
    return jsonify(data)

# Add device to dashboard (Admin only)
@dashboard_device_bp.route('/dashboard/<int:dashboard_id>/devices/add', methods=['POST'])
@login_required
def add_device_to_dashboard(dashboard_id):
    """Add a device to dashboard (Admin/Super Admin only)"""
    
    if current_user.role not in ['admin', 'super_admin']:
        flash('Access denied', 'error')
        return redirect(url_for('dashboard_device.device_list', dashboard_id=dashboard_id))
    
    device_id = request.form.get('device_id')
    
    if not device_id:
        flash('Device ID is required', 'error')
        return redirect(url_for('dashboard_settings.dashboard_settings', dashboard_id=dashboard_id))
    
    # Check if device exists
    device = Device.query.get(device_id)
    if not device:
        flash('Device not found', 'error')
        return redirect(url_for('dashboard_settings.dashboard_settings', dashboard_id=dashboard_id))
    
    # Check if device is already in dashboard
    existing = DashboardSensor.query.filter_by(
        dashboard_id=dashboard_id,
        device_id=device_id
    ).first()
    
    if existing:
        flash('Device is already in this dashboard', 'warning')
    else:
        # Add device to dashboard
        dashboard_sensor = DashboardSensor(
            dashboard_id=dashboard_id,
            device_id=device_id
        )
        db.session.add(dashboard_sensor)
        db.session.commit()
        flash(f'Device {device.name} added to dashboard successfully', 'success')
    
    return redirect(url_for('dashboard_settings.dashboard_settings', dashboard_id=dashboard_id))

# Remove device from dashboard (Admin only)
@dashboard_device_bp.route('/dashboard/<int:dashboard_id>/devices/<int:device_id>/remove', methods=['POST'])
@login_required
def remove_device_from_dashboard(dashboard_id, device_id):
    """Remove a device from dashboard (Admin/Super Admin only)"""
    
    if current_user.role not in ['admin', 'super_admin']:
        flash('Access denied', 'error')
        return redirect(url_for('dashboard_device.device_list', dashboard_id=dashboard_id))
    
    # Find the dashboard_sensor entry
    dashboard_sensor = DashboardSensor.query.filter_by(
        dashboard_id=dashboard_id,
        device_id=device_id
    ).first()
    
    if dashboard_sensor:
        db.session.delete(dashboard_sensor)
        db.session.commit()
        flash('Device removed from dashboard successfully', 'success')
    else:
        flash('Device not found in dashboard', 'error')
    
    return redirect(url_for('dashboard_settings.dashboard_settings', dashboard_id=dashboard_id))