from flask import Blueprint, render_template, redirect, url_for, flash, jsonify, request
from flask_login import login_required, current_user
from models import db, Device, SensorData, User, UserDevice, MQTTConfig, Dashboard, UserDashboard
from datetime import datetime, timedelta
from types import SimpleNamespace

device_bp = Blueprint('device', __name__)

def get_user_devices(user_id):
    """Get all devices accessible to a user"""
    user = db.session.get(User, int(user_id))
    if not user:
        return []

    if user.role in ['super_admin', 'admin']:
        # Admins can see all devices
        return Device.query.all()
    else:
        # Regular users can see their own devices and shared devices
        owned_devices = Device.query.filter_by(user_id=user_id).all()
        shared_devices = db.session.query(Device).join(UserDevice).filter(
            UserDevice.user_id == user_id
        ).all()
        return list(set(owned_devices + shared_devices))

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

# @device_bp.route('/dashboard')
# @login_required
# def dashboard():
#     # Get devices for the current user
#     devices = Device.query.filter_by(user_id=current_user.id).all()
#     mqtt_configs = MQTTConfig.query.all()
#     return render_template('dashboard.html', devices=devices, mqtt_configs=mqtt_configs)



@device_bp.route('/<int:device_id>')
@login_required
def device_detail(device_id):
    device = Device.query.get_or_404(device_id)
    
    # Check if user has access to this device
    user_devices = [d.id for d in get_user_devices(current_user.id)]
    if device.id not in user_devices:
        flash('You do not have access to this device', 'error')
        return redirect(url_for('device.devices'))
    
    # Get recent sensor data
    sensor_data = SensorData.query.filter_by(device_id=device_id)\
        .order_by(SensorData.timestamp.desc())\
        .limit(100)\
        .all()
    
    return render_template('device_detail.html', device=device, sensor_data=sensor_data)

# Add API endpoint for device data
@device_bp.route('/api/<int:device_id>/data')
@login_required
def device_data(device_id):
    device = Device.query.get_or_404(device_id)
    
    # Check access
    user_devices = [d.id for d in get_user_devices(current_user.id)]
    if device.id not in user_devices:
        return jsonify({'error': 'Access denied'}), 403
    
    # Get sensor data with optional filters
    limit = request.args.get('limit', 100, type=int)
    sensor_data = SensorData.query.filter_by(device_id=device_id)\
        .order_by(SensorData.timestamp.desc())\
        .limit(limit)\
        .all()
    
    data = [{
        'id': sd.id,
        'sensor_type': sd.sensor_type,
        'value': sd.value,
        'unit': sd.unit,
        'timestamp': sd.timestamp.isoformat(),
        'latitude': sd.latitude,
        'longitude': sd.longitude
    } for sd in sensor_data]
    
    return jsonify(data)