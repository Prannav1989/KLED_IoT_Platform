from flask import Blueprint, render_template, jsonify, current_app
from flask_login import login_required, current_user
from models import Device, SensorData, DashboardSensor
from extensions import db
from datetime import datetime, timedelta
import json

user_bp = Blueprint("user", __name__, url_prefix="/user")

@user_bp.route('/dashboard')
@login_required
def dashboard():
    """User dashboard showing devices allocated to their dashboard"""
    # Get dashboard IDs for current user (you might need to adjust this based on your schema)
    # If dashboard_sensors has a direct user_id field, use that
    # Otherwise, we'll get devices that are in dashboard_sensors AND belong to current user
    
    # Method 1: If dashboard_sensors has user_id
    # dashboard_devices = DashboardSensor.query.filter_by(user_id=current_user.id).all()
    
    # Method 2: Join with devices to find dashboard allocations for current user's devices
    dashboard_allocations = db.session.query(DashboardSensor).join(
        Device, DashboardSensor.device_id == Device.id
    ).filter(Device.user_id == current_user.id).all()
    
    devices = [alloc.device for alloc in dashboard_allocations]
    
    return render_template('user_dashboard/dashboard.html', 
                          devices=devices,
                          user=current_user)

@user_bp.route('/api/sensor-data/<int:device_id>')
@login_required
def get_sensor_data(device_id):
    """API endpoint to get sensor data for a specific device allocated to user's dashboard"""
    # Check if device belongs to user AND is in dashboard_sensors
    device_allocation = db.session.query(DashboardSensor).join(
        Device, DashboardSensor.device_id == Device.id
    ).filter(
        DashboardSensor.device_id == device_id,
        Device.user_id == current_user.id
    ).first()
    
    if not device_allocation:
        return jsonify({'error': 'Device not found in your dashboard or access denied'}), 404

    device = Device.query.get(device_id)
    if not device:
        return jsonify({'error': 'Device not found'}), 404

    # Last 24 hours
    time_threshold = datetime.utcnow() - timedelta(hours=24)
    sensor_data = SensorData.query.filter(
        SensorData.device_id == device_id,
        SensorData.timestamp >= time_threshold
    ).order_by(SensorData.timestamp.desc()).limit(200).all()

    # Group by sensor_id
    data_by_sensor = {}
    for d in sensor_data:
        if d.sensor_id not in data_by_sensor:
            data_by_sensor[d.sensor_id] = {
                'values': [],
                'timestamps': []
            }
        data_by_sensor[d.sensor_id]['values'].append(d.value)
        data_by_sensor[d.sensor_id]['timestamps'].append(d.timestamp.isoformat())

    return jsonify({
        'device': {'id': device.id, 'name': device.name},
        'sensors': data_by_sensor
    })

@user_bp.route('/api/device-status')
@login_required
def get_device_status():
    """API endpoint to get status of devices allocated to user's dashboard"""
    try:
        # Get dashboard allocations for current user's devices
        dashboard_allocations = db.session.query(DashboardSensor).join(
            Device, DashboardSensor.device_id == Device.id
        ).filter(Device.user_id == current_user.id).all()
        
        print(f"Found {len(dashboard_allocations)} dashboard allocations for user {current_user.id}")
        
        devices_status = []
        for allocation in dashboard_allocations:
            device = allocation.device
            
            # Get the latest sensor data for this device
            latest_data = SensorData.query.filter_by(device_id=device.id)\
                .order_by(SensorData.timestamp.desc()).first()
            
            devices_status.append({
                'id': device.id,
                'name': device.name,
                'device_type': device.device_type,
                'status': device.status,
                'dashboard_id': allocation.dashboard_id,
                'last_updated': latest_data.timestamp.isoformat() if latest_data else None,
                'last_temperature': latest_data.temperature if latest_data else None,
                'last_humidity': latest_data.humidity if latest_data else None
            })
        
        return jsonify(devices_status)
    except Exception as e:
        print(f"Error in get_device_status: {str(e)}")
        return jsonify({'error': str(e)}), 500