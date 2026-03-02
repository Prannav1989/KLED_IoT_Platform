#sensor_routes.py
from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from models import Device, SensorData, User, AlertRule,NavigationSettings
from extensions import db
from datetime import datetime, timedelta
import json
from sqlalchemy import func
from collections import defaultdict
from sqlalchemy import func
from types import SimpleNamespace

sensor_bp = Blueprint('sensor', __name__, url_prefix='/sensor')

@sensor_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.role in ['admin', 'super_admin']:
        # Admins see everything
        all_devices = Device.query.all()
        recent_data = SensorData.query.order_by(SensorData.timestamp.desc()).limit(50).all()

        # Get the latest reading for each unique sensor per device
        subquery = (
            db.session.query(
                SensorData.device_id,
                SensorData.sensor_id,
                func.max(SensorData.timestamp).label("max_time")
            )
            .group_by(SensorData.device_id, SensorData.sensor_id)
            .subquery()
        )

        latest_sensor_data = (
            db.session.query(SensorData)
            .join(
                subquery,
                (SensorData.device_id == subquery.c.device_id) &
                (SensorData.sensor_id == subquery.c.sensor_id) &
                (SensorData.timestamp == subquery.c.max_time)
            )
            .all()
        )
        
        # Get device IDs that actually have sensor data
        device_ids_with_data = list(set([data.device_id for data in latest_sensor_data]))
        devices_with_data = Device.query.filter(Device.id.in_(device_ids_with_data)).all()

    else:
        # Normal users see only their allocated devices
        all_devices = current_user.allocated_devices.all()
        device_ids = [d.id for d in all_devices]

        recent_data = (
            SensorData.query.filter(SensorData.device_id.in_(device_ids))
            .order_by(SensorData.timestamp.desc())
            .limit(50)
            .all()
        )

        # Get the latest reading for each unique sensor per device
        subquery = (
            db.session.query(
                SensorData.device_id,
                SensorData.sensor_id,
                func.max(SensorData.timestamp).label("max_time")
            )
            .filter(SensorData.device_id.in_(device_ids))
            .group_by(SensorData.device_id, SensorData.sensor_id)
            .subquery()
        )

        latest_sensor_data = (
            db.session.query(SensorData)
            .join(
                subquery,
                (SensorData.device_id == subquery.c.device_id) &
                (SensorData.sensor_id == subquery.c.sensor_id) &
                (SensorData.timestamp == subquery.c.max_time)
            )
            .all()
        )
        
        # For regular users, show all allocated devices (even if they have no data yet)
        devices_with_data = all_devices

    # Group by device
    sensor_groups = defaultdict(list)
    devices_to_show = []  # Devices that will actually be displayed
    
    for d in latest_sensor_data:
        if d.device:
            sensor_groups[d.device.name].append(d)
            if d.device not in devices_to_show:
                devices_to_show.append(d.device)
    
    # Add devices that have no sensor data but should be shown
    for device in devices_with_data:
        if device not in devices_to_show:
            devices_to_show.append(device)

    grouped_sensors = []
    for device_name, data in sensor_groups.items():
        # Get the latest timestamp among all sensors for this device
        latest_timestamp = max(d.timestamp for d in data) if data else None
        
        # Create unique parameters by sensor type (access via sensor relationship)
        unique_parameters = {}
        for d in data:
            # Access sensor type through the relationship to Sensor model
            sensor_type = d.sensor.sensor_type if d.sensor and hasattr(d.sensor, 'sensor_type') else "Unknown"
            if sensor_type not in unique_parameters:
                unique_parameters[sensor_type] = {
                    "name": sensor_type, 
                    "value": d.value, 
                    "unit": d.unit
                }
        
        grouped_sensors.append({
            "device_name": device_name,
            "timestamp": latest_timestamp,
            "parameters": list(unique_parameters.values())
        })
    
    # Create empty widgets for devices with no sensor data
    for device in devices_with_data:
        if device.name not in sensor_groups:
            grouped_sensors.append({
                "device_name": device.name,
                "timestamp": None,
                "parameters": []
            })

    # Device status counts - only for devices we're supposed to show
    total_devices = len(devices_with_data)
    online_devices = [d for d in devices_with_data if d.status == 'online']
    offline_devices = [d for d in devices_with_data if d.status == 'offline']
    inactive_devices = [d for d in devices_with_data if d.status == 'inactive']

    return render_template(
        'sensor_dashboard/dashboard.html',
        devices=devices_with_data,  # Show all devices that should be visible
        recent_data=recent_data,
        grouped_sensors=grouped_sensors,
        total_devices=total_devices,
        online_devices=online_devices,
        online_devices_count=len(online_devices),
        offline_devices=offline_devices,
        offline_devices_count=len(offline_devices),
        inactive_devices=inactive_devices,
        inactive_devices_count=len(inactive_devices),
        total_users=User.query.count()
    )
                         
@sensor_bp.route('/rules')
@login_required
def rules():
    """Rules engine for alert management"""
    if current_user.role not in ['admin', 'super_admin']:
        return "Access denied", 403
    
    rules = AlertRule.query.all()
    return render_template('sensor_dashboard/rules.html', rules=rules)



# Add placeholder routes for other admin functions
@sensor_bp.route('/api/sensor-data')
@login_required
def api_sensor_data():
    """API endpoint for sensor data"""
    if current_user.role not in ['admin', 'super_admin']:
        return jsonify({'error': 'Access denied'}), 403
    
    # This would return actual sensor data in a real implementation
    return jsonify({'message': 'Sensor data endpoint'})

# Optional: Add API endpoint for device status
@sensor_bp.route('/api/device-status')
@login_required
def api_device_status():
    """API endpoint for device status (admin only)"""
    if current_user.role not in ['admin', 'super_admin']:
        return jsonify({'error': 'Access denied'}), 403

    devices = Device.query.all()
    now = datetime.utcnow()

    status_data = []
    for device in devices:
        # Compute status
        if not device.is_active:
            status = "inactive"
        elif device.last_seen and (now - device.last_seen) < timedelta(minutes=5):
            status = "online"
        else:
            status = "offline"

        status_data.append({
            'id': device.id,
            'name': device.name,
            'device_id': device.device_id,
            'status': status,
            'is_active': device.is_active,
            'last_seen': device.last_seen.isoformat() if device.last_seen else None
        })

    return jsonify({
        'devices': status_data,
        'counts': {
            'total': len(devices),
            'online': len([d for d in status_data if d['status'] == 'online']),
            'offline': len([d for d in status_data if d['status'] == 'offline']),
            'inactive': len([d for d in status_data if d['status'] == 'inactive'])
        }
    })
@sensor_bp.route('/api/dashboard-data')
@login_required
def api_dashboard_data():
    # Same logic as your dashboard function but return JSON
    if current_user.role in ['admin', 'super_admin']:
        devices = Device.query.all()
    else:
        devices = current_user.allocated_devices.all()
    
    device_ids = [d.id for d in devices]
    
    # Get latest sensor data (similar to your existing query)
    subquery = (
        db.session.query(
            SensorData.sensor_id,
            func.max(SensorData.timestamp).label("max_time")
        )
        .filter(SensorData.device_id.in_(device_ids))
        .group_by(SensorData.sensor_id)
        .subquery()
    )

    latest_sensor_data = (
        db.session.query(SensorData)
        .join(subquery, (SensorData.sensor_id == subquery.c.sensor_id) & 
              (SensorData.timestamp == subquery.c.max_time))
        .all()
    )
    
    # Convert to JSON-serializable format
    sensor_data_json = []
    for sensor in latest_sensor_data:
        sensor_data_json.append({
            'id': sensor.id,
            'name': sensor.name,
            'sensor_type': sensor.sensor_type,
            'value': sensor.value,
            'unit': sensor.unit,
            'device_name': sensor.device.name if sensor.device else 'Unknown',
            'timestamp': sensor.timestamp.isoformat() if sensor.timestamp else None
        })
    
    # Convert devices to JSON
    devices_json = []
    for device in devices:
        devices_json.append({
            'id': device.id,
            'name': device.name,
            'device_id': device.device_id,
            'status': device.status,
            'last_seen': device.last_seen.isoformat() if device.last_seen else None
        })
    
    return jsonify({
        'total_devices': len(devices),
        'online_count': len([d for d in devices if d.status == 'online']),
        'offline_count': len([d for d in devices if d.status == 'offline']),
        'inactive_count': len([d for d in devices if d.status == 'inactive']),
        'latest_sensor_data': sensor_data_json,
        'devices': devices_json
    })