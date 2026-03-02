from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from sqlalchemy import func, desc, and_
from datetime import datetime, timedelta
from collections import defaultdict
from functools import wraps
import logging

# Import within functions to avoid circular imports
def get_db():
    from extensions import db
    return db

def get_models():
    from models import User, Device, Sensor, SensorData, AuditLog
    return User, Device, Sensor, SensorData, AuditLog

# Create blueprint
user_bp = Blueprint('user', __name__, url_prefix='/user')

# Helper functions
def get_user_devices_with_data(user_id):
    """Get devices belonging to user with their latest sensor data"""
    try:
        User, Device, Sensor, SensorData, AuditLog = get_models()
        db = get_db()
        
        # Get user's devices
        devices = Device.query.filter_by(user_id=user_id, is_active=True).all()
        
        if not devices:
            return []
        
        device_ids = [device.id for device in devices]
        
        # Get latest sensor data for these devices - more efficient query
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

        latest_data = (
            db.session.query(SensorData)
            .join(
                subquery,
                and_(
                    SensorData.device_id == subquery.c.device_id,
                    SensorData.sensor_id == subquery.c.sensor_id,
                    SensorData.timestamp == subquery.c.max_time
                )
            )
            .filter(SensorData.device_id.in_(device_ids))
            .all()
        )
        
        # Group data by device
        device_data = defaultdict(list)
        for data in latest_data:
            device_data[data.device_id].append(data)
        
        # Prepare response
        result = []
        for device in devices:
            data_list = device_data.get(device.id, [])
            
            # Get latest timestamp safely
            latest_timestamp = None
            if data_list:
                try:
                    latest_timestamp = max(d.timestamp for d in data_list)
                except ValueError:
                    latest_timestamp = None
            
            # Get unique parameters
            parameters = {}
            for data in data_list:
                sensor_type = "Unknown"
                if data.sensor:
                    sensor_type = data.sensor.sensor_type
                parameters[sensor_type] = {
                    "value": data.value,
                    "unit": data.unit,
                    "timestamp": data.timestamp
                }
            
            result.append({
                "device": device,
                "latest_timestamp": latest_timestamp,
                "parameters": parameters,
                "has_data": bool(data_list),
                "status": device.status
            })
        
        return result
        
    except Exception as e:
        current_app.logger.error(f"Error getting user devices with data: {e}")
        return []

def get_user_statistics(user_id):
    """Get statistics for user dashboard"""
    try:
        User, Device, Sensor, SensorData, AuditLog = get_models()
        db = get_db()
        
        total_devices = Device.query.filter_by(user_id=user_id, is_active=True).count()
        
        online_devices = Device.query.filter_by(
            user_id=user_id, 
            status='online', 
            is_active=True
        ).count()
        
        # Get 24h data count for user's devices
        twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
        user_device_ids = [d.id for d in Device.query.filter_by(user_id=user_id, is_active=True).all()]
        
        recent_readings = 0
        if user_device_ids:
            recent_readings = SensorData.query.filter(
                SensorData.timestamp >= twenty_four_hours_ago,
                SensorData.device_id.in_(user_device_ids)
            ).count()
        
        # Get sensor count
        total_sensors = Sensor.query.join(Device).filter(
            Device.user_id == user_id,
            Device.is_active == True
        ).count()
        
        # Calculate device health percentage safely
        device_health = 0
        if total_devices > 0:
            device_health = round((online_devices / total_devices) * 100, 1)
        
        return {
            'total_devices': total_devices,
            'online_devices': online_devices,
            'offline_devices': total_devices - online_devices,
            'total_sensors': total_sensors,
            'recent_readings': recent_readings,
            'device_health': device_health
        }
    except Exception as e:
        current_app.logger.error(f"Error getting user statistics: {e}")
        return {
            'total_devices': 0,
            'online_devices': 0,
            'offline_devices': 0,
            'total_sensors': 0,
            'recent_readings': 0,
            'device_health': 0
        }

def require_user_access(f):
    """Decorator to ensure user can only access their own data"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please login to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        
        # Check if user is trying to access another user's data via user_id parameter
        user_id = kwargs.get('user_id')
        if user_id and user_id != current_user.id and current_user.role not in ['admin', 'super_admin']:
            flash('Access denied. You can only access your own data.', 'danger')
            return redirect(url_for('user.dashboard'))
        
        # Check device ownership for device-specific routes
        device_id = kwargs.get('device_id')
        if device_id:
            User, Device, Sensor, SensorData, AuditLog = get_models()
            device = Device.query.filter_by(id=device_id, is_active=True).first()
            if not device:
                flash('Device not found.', 'danger')
                return redirect(url_for('user.my_devices'))
            if device.user_id != current_user.id and current_user.role not in ['admin', 'super_admin']:
                flash('Access denied to this device.', 'danger')
                return redirect(url_for('user.my_devices'))
            
        return f(*args, **kwargs)
    return decorated_function

# # Routes
# @user_bp.route('/dashboard')
# @login_required
# def dashboard():
#     """User Dashboard"""
#     try:
#         User, Device, Sensor, SensorData, AuditLog = get_models()
        
#         # Get user's devices with latest data
#         devices_with_data = get_user_devices_with_data(current_user.id)
        
#         # Get user statistics
#         stats = get_user_statistics(current_user.id)
        
#         # Get recent activity for user's devices
#         user_device_ids = [d.id for d in Device.query.filter_by(
#             user_id=current_user.id, 
#             is_active=True
#         ).all()]
        
#         recent_activity = []
#         if user_device_ids:
#             recent_activity = AuditLog.query.filter(
#                 AuditLog.device_id.in_(user_device_ids)
#             ).order_by(AuditLog.timestamp.desc()).limit(5).all()
        
#         return render_template(
#             'user/dashboard.html',
#             devices_with_data=devices_with_data,
#             stats=stats,
#             recent_activity=recent_activity,
#             current_user=current_user
#         )
        
#     except Exception as e:
#         current_app.logger.error(f"Dashboard error: {e}")
#         flash('Error loading dashboard. Please try again.', 'danger')
#         return redirect(url_for('user.my_devices'))

@user_bp.route('/devices')
@login_required
def my_devices():
    """User's Devices List"""
    try:
        User, Device, Sensor, SensorData, AuditLog = get_models()
        
        devices = Device.query.filter_by(
            user_id=current_user.id, 
            is_active=True
        ).order_by(Device.created_at.desc()).all()
        
        return render_template('user/devices.html', devices=devices)
        
    except Exception as e:
        current_app.logger.error(f"Devices list error: {e}")
        flash('Error loading devices. Please try again.', 'danger')
        return redirect(url_for('user.dashboard'))

@user_bp.route('/device/<int:device_id>')
@login_required
@require_user_access
def device_detail(device_id):
    """Device Detail View"""
    try:
        User, Device, Sensor, SensorData, AuditLog = get_models()
        db = get_db()
        
        device = Device.query.filter_by(
            id=device_id, 
            user_id=current_user.id,
            is_active=True
        ).first_or_404()
        
        # Get device sensors
        sensors = Sensor.query.filter_by(device_id=device_id).all()
        
        # Get recent sensor data
        recent_data = SensorData.query.filter_by(device_id=device_id)\
            .order_by(SensorData.timestamp.desc()).limit(50).all()
        
        # Get 24h data for charts
        twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
        chart_data = SensorData.query.filter(
            SensorData.device_id == device_id,
            SensorData.timestamp >= twenty_four_hours_ago
        ).order_by(SensorData.timestamp).all()
        
        # Group chart data by sensor type
        chart_data_grouped = defaultdict(list)
        for data in chart_data:
            sensor_type = data.sensor.sensor_type if data.sensor else "Unknown"
            chart_data_grouped[sensor_type].append({
                'timestamp': data.timestamp.isoformat(),
                'value': float(data.value) if data.value is not None else 0.0
            })
        
        return render_template(
            'user/device_detail.html',
            device=device,
            sensors=sensors,
            recent_data=recent_data,
            chart_data=chart_data_grouped
        )
        
    except Exception as e:
        current_app.logger.error(f"Device detail error for device {device_id}: {e}")
        flash('Error loading device details. Please try again.', 'danger')
        return redirect(url_for('user.my_devices'))

@user_bp.route('/sensors')
@login_required
def my_sensors():
    """User's Sensors"""
    try:
        User, Device, Sensor, SensorData, AuditLog = get_models()
        
        sensors = Sensor.query.join(Device).filter(
            Device.user_id == current_user.id,
            Device.is_active == True
        ).order_by(Sensor.created_at.desc()).all()
        
        return render_template('user/sensors.html', sensors=sensors)
        
    except Exception as e:
        current_app.logger.error(f"Sensors list error: {e}")
        flash('Error loading sensors. Please try again.', 'danger')
        return redirect(url_for('user.dashboard'))

@user_bp.route('/profile')
@login_required
def profile():
    """User Profile"""
    try:
        User, Device, Sensor, SensorData, AuditLog = get_models()
        return render_template('user/profile.html', user=current_user)
    except Exception as e:
        current_app.logger.error(f"Profile error: {e}")
        flash('Error loading profile. Please try again.', 'danger')
        return redirect(url_for('user.dashboard'))

@user_bp.route('/settings')
@login_required
def settings():
    """User Settings"""
    try:
        return render_template('user/settings.html')
    except Exception as e:
        current_app.logger.error(f"Settings error: {e}")
        flash('Error loading settings. Please try again.', 'danger')
        return redirect(url_for('user.dashboard'))

# API endpoints
@user_bp.route('/api/device-data/<int:device_id>')
@login_required
@require_user_access
def api_device_data(device_id):
    """API endpoint for device data"""
    try:
        User, Device, Sensor, SensorData, AuditLog = get_models()
        
        # Verify device belongs to user (handled by decorator)
        device = Device.query.filter_by(
            id=device_id, 
            user_id=current_user.id,
            is_active=True
        ).first_or_404()
        
        # Get data for last 24 hours
        twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
        data = SensorData.query.filter(
            SensorData.device_id == device_id,
            SensorData.timestamp >= twenty_four_hours_ago
        ).order_by(SensorData.timestamp).all()
        
        result = [{
            'timestamp': d.timestamp.isoformat(),
            'sensor_type': d.sensor.sensor_type if d.sensor else 'Unknown',
            'value': float(d.value) if d.value is not None else None,
            'unit': d.unit
        } for d in data]
        
        return jsonify({
            'success': True,
            'data': result,
            'device_name': device.name,
            'device_id': device.id
        })
        
    except Exception as e:
        current_app.logger.error(f"API device data error for device {device_id}: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to fetch device data'
        }), 500

@user_bp.route('/api/dashboard-stats')
@login_required
def api_dashboard_stats():
    """API endpoint for dashboard statistics"""
    try:
        stats = get_user_statistics(current_user.id)
        return jsonify({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        current_app.logger.error(f"Dashboard stats API error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to fetch dashboard statistics'
        }), 500

@user_bp.route('/api/device-status')
@login_required
def api_device_status():
    """API endpoint for quick device status overview"""
    try:
        User, Device, Sensor, SensorData, AuditLog = get_models()
        
        devices = Device.query.filter_by(
            user_id=current_user.id, 
            is_active=True
        ).all()
        
        status_overview = {
            'online': 0,
            'offline': 0,
            'warning': 0,
            'total': len(devices)
        }
        
        for device in devices:
            if device.status == 'online':
                status_overview['online'] += 1
            elif device.status == 'offline':
                status_overview['offline'] += 1
            else:
                status_overview['warning'] += 1
        
        return jsonify({
            'success': True,
            'status_overview': status_overview
        })
        
    except Exception as e:
        current_app.logger.error(f"Device status API error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to fetch device status'
        }), 500

# Error handlers
@user_bp.app_errorhandler(403)
def forbidden(error):
    return render_template('errors/403.html'), 403

@user_bp.app_errorhandler(404)
def not_found(error):
    return render_template('errors/404.html'), 404

@user_bp.app_errorhandler(500)
def internal_error(error):
    return render_template('errors/500.html'), 500