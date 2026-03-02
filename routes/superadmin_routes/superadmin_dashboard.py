from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash, g
from datetime import datetime
import sqlite3
from functools import wraps
import json
from contextlib import closing
import traceback

superadmin_bp = Blueprint('superadmin', __name__, url_prefix='/superadmin')

# Database configuration
DB_PATH = "C:\Users\Dell Lattitude 3450\Desktop\IoT Management\data\iot.db"

# Database connection helper with connection pooling
def get_db():
    """Get database connection with connection pooling"""
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db

def close_db(e=None):
    """Close database connection"""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db(app):
    """Initialize database connection handling"""
    app.teardown_appcontext(close_db)

# Superadmin authentication decorator
def superadmin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        
        db = get_db()
        user = db.execute(
            'SELECT role FROM users WHERE id = ?', (session['user_id'],)
        ).fetchone()
        
        if not user or user['role'] != 'superadmin':
            flash('Access denied. Superadmin privileges required.', 'error')
            return redirect(url_for('main.dashboard'))
        
        return f(*args, **kwargs)
    return decorated_function

# Database query helper functions
def execute_query(query, params=(), fetchone=False, fetchall=False):
    """Execute SQL query safely"""
    db = get_db()
    try:
        cursor = db.execute(query, params)
        db.commit()
        if fetchone:
            return cursor.fetchone()
        if fetchall:
            return cursor.fetchall()
        return cursor
    except sqlite3.Error as e:
        db.rollback()
        raise e

def get_statistics():
    """Get all dashboard statistics in single query where possible"""
    queries = {
        'total_users': 'SELECT COUNT(*) as count FROM users',
        'total_devices': 'SELECT COUNT(*) as count FROM devices',
        'total_companies': 'SELECT COUNT(*) as count FROM companies',
        'total_sensor_data': 'SELECT COUNT(*) as count FROM sensor_data',
        'active_users': 'SELECT COUNT(*) as count FROM users WHERE active_status = 1',
        'active_devices': 'SELECT COUNT(*) as count FROM devices WHERE is_active = 1',
        'total_mqtt_configs': 'SELECT COUNT(*) as count FROM mqtt_configs',
        'total_alerts': 'SELECT COUNT(*) as count FROM alert_rule WHERE enabled = 1'
    }
    
    stats = {}
    db = get_db()
    for key, query in queries.items():
        result = db.execute(query).fetchone()
        stats[key] = result['count'] if result else 0
    
    return stats

def format_stats_items(stats):
    """Format statistics for display"""
    return [
        {"value": stats["total_users"], "label": "Users", "icon": "fas fa-users", "color": "primary"},
        {"value": stats["total_devices"], "label": "Devices", "icon": "fas fa-microchip", "color": "success"},
        {"value": stats["total_companies"], "label": "Companies", "icon": "fas fa-building", "color": "info"},
        {"value": stats["total_sensor_data"], "label": "Data Points", "icon": "fas fa-database", "color": "warning"},
    ]

def get_recent_users(limit=10):
    """Get recent users"""
    return execute_query('''
        SELECT id, username, email, role, company, created_at, active_status 
        FROM users 
        ORDER BY created_at DESC 
        LIMIT ?
    ''', (limit,), fetchall=True)

def get_recent_devices(limit=10):
    """Get recent devices with related info"""
    return execute_query('''
        SELECT d.id, d.name, d.device_id, d.mqtt_topic, d.created_at, d.is_active,
               u.username as owner, c.name as company_name
        FROM devices d
        LEFT JOIN users u ON d.user_id = u.id
        LEFT JOIN companies c ON d.company_id = c.id
        ORDER BY d.created_at DESC 
        LIMIT ?
    ''', (limit,), fetchall=True)

def get_recent_sensor_data(limit=10):
    """Get recent sensor data"""
    return execute_query('''
        SELECT sd.id, sd.device_id, sd.sensor_id, sd.value, sd.unit, sd.timestamp,
               d.name as device_name, p.name as parameter_name
        FROM sensor_data sd
        LEFT JOIN devices d ON sd.device_id = d.id
        LEFT JOIN parameters p ON sd.parameter_id = p.id
        ORDER BY sd.timestamp DESC 
        LIMIT ?
    ''', (limit,), fetchall=True)

def get_chart_data():
    """Get data for charts"""
    db = get_db()
    
    # Users by role
    users_by_role_data = db.execute('''
        SELECT role, COUNT(*) as count 
        FROM users 
        GROUP BY role
    ''').fetchall()
    
    role_labels = []
    role_data = []
    role_colors = ['#4e73df', '#1cc88a', '#36b9cc', '#f6c23e']
    
    for i, row in enumerate(users_by_role_data):
        role_labels.append(row['role'].replace('_', ' ').title())
        role_data.append(row['count'])
    
    # Device status distribution
    device_status_result = db.execute('''
        SELECT 
            SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) as active,
            SUM(CASE WHEN is_active = 0 THEN 1 ELSE 0 END) as inactive
        FROM devices
    ''').fetchone()
    
    device_status = {
        'active': device_status_result['active'] or 0 if device_status_result else 0,
        'inactive': device_status_result['inactive'] or 0 if device_status_result else 0
    }
    
    return {
        'users_by_role': {
            'labels': role_labels,
            'data': role_data,
            'colors': role_colors[:len(role_labels)]
        },
        'device_status': {
            'labels': ['Active', 'Inactive'],
            'data': [device_status['active'], device_status['inactive']],
            'colors': ['#1cc88a', '#e74a3b']
        }
    }


@superadmin_bp.route('/sensor-data')
@superadmin_required
def sensor_data_management():
    """Sensor data management"""
    try:
        sensor_data = execute_query('''
            SELECT sd.*, d.name as device_name, p.name as parameter_name, u.username
            FROM sensor_data sd
            LEFT JOIN devices d ON sd.device_id = d.id
            LEFT JOIN parameters p ON sd.parameter_id = p.id
            LEFT JOIN users u ON sd.user_id = u.id
            ORDER BY sd.timestamp DESC
            LIMIT 100
        ''', fetchall=True)
        
        return render_template('superadmin_dashboard/sensor_data.html', sensor_data=sensor_data)
        
    except Exception as e:
        flash(f'Error loading sensor data: {str(e)}', 'error')
        return render_template('superadmin_dashboard/sensor_data.html', sensor_data=[])

@superadmin_bp.route('/mqtt-configs')
@superadmin_required
def mqtt_configs_management():
    """MQTT configs management"""
    try:
        mqtt_configs = execute_query('''
            SELECT m.*, u.username as owner,
                   (SELECT COUNT(*) FROM devices WHERE mqtt_config_id = m.id) as device_count,
                   (SELECT COUNT(*) FROM mqtt_messages WHERE mqtt_config_id = m.id) as message_count
            FROM mqtt_configs m
            LEFT JOIN users u ON m.user_id = u.id
            ORDER BY m.created_at DESC
        ''', fetchall=True)
        
        return render_template('superadmin_dashboard/mqtt_configs.html', mqtt_configs=mqtt_configs)
        
    except Exception as e:
        flash(f'Error loading MQTT configs: {str(e)}', 'error')
        return render_template('superadmin_dashboard/mqtt_configs.html', mqtt_configs=[])

@superadmin_bp.route('/analytics')
@superadmin_required
def analytics():
    """Analytics dashboard"""
    db = get_db()
    
    try:
        # Daily user registrations
        daily_registrations = db.execute('''
            SELECT DATE(created_at) as date, COUNT(*) as count
            FROM users
            WHERE created_at >= date('now', '-30 days')
            GROUP BY DATE(created_at)
            ORDER BY date
        ''').fetchall()
        
        # Device data
        device_data_result = db.execute('''
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) as active,
                SUM(CASE WHEN is_active = 0 THEN 1 ELSE 0 END) as inactive
            FROM devices
        ''').fetchone()
        
        device_data = {
            'total': device_data_result['total'] or 0 if device_data_result else 0,
            'active': device_data_result['active'] or 0 if device_data_result else 0,
            'inactive': device_data_result['inactive'] or 0 if device_data_result else 0
        }
        
        # Data volume
        data_volume = db.execute('''
            SELECT DATE(timestamp) as date, COUNT(*) as count
            FROM sensor_data
            WHERE timestamp >= date('now', '-30 days')
            GROUP BY DATE(timestamp)
            ORDER BY date
        ''').fetchall()
        
        # Top devices
        top_devices = db.execute('''
            SELECT d.name, d.device_id, COUNT(sd.id) as data_count
            FROM devices d
            LEFT JOIN sensor_data sd ON d.id = sd.device_id
            GROUP BY d.id, d.name, d.device_id
            ORDER BY data_count DESC
            LIMIT 10
        ''').fetchall()
        
        return render_template('superadmin_dashboard/analytics.html',
                             daily_registrations=daily_registrations,
                             device_data=device_data,
                             data_volume=data_volume,
                             top_devices=top_devices,
                             )
        
    except Exception as e:
        flash(f'Error loading analytics: {str(e)}', 'error')
        print(f"Analytics error: {e}")
        return render_template('superadmin_dashboard/analytics.html',
                             daily_registrations=[],
                             device_data={'total': 0, 'active': 0, 'inactive': 0},
                             data_volume=[],
                             top_devices=[])

@superadmin_bp.route('/toggle-user/<int:user_id>', methods=['POST'])
@superadmin_required
def toggle_user_status(user_id):
    """Toggle user active status"""
    try:
        db = get_db()
        user = db.execute('SELECT active_status FROM users WHERE id = ?', (user_id,)).fetchone()
        
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        new_status = not user['active_status']
        db.execute('UPDATE users SET active_status = ? WHERE id = ?', (new_status, user_id))
        
        # Log the action
        db.execute('''
            INSERT INTO audit_logs (user_id, action, details, timestamp)
            VALUES (?, ?, ?, ?)
        ''', (session['user_id'], 'TOGGLE_USER_STATUS', 
              f'Changed user {user_id} status to {new_status}', datetime.now()))
        
        db.commit()
        return jsonify({'success': True, 'new_status': new_status})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@superadmin_bp.route('/toggle-device/<int:device_id>', methods=['POST'])
@superadmin_required
def toggle_device_status(device_id):
    """Toggle device active status"""
    try:
        db = get_db()
        device = db.execute('SELECT is_active FROM devices WHERE id = ?', (device_id,)).fetchone()
        
        if not device:
            return jsonify({'success': False, 'error': 'Device not found'}), 404
        
        new_status = not device['is_active']
        db.execute('UPDATE devices SET is_active = ? WHERE id = ?', (new_status, device_id))
        
        # Log the action
        db.execute('''
            INSERT INTO audit_logs (user_id, action, details, timestamp)
            VALUES (?, ?, ?, ?)
        ''', (session['user_id'], 'TOGGLE_DEVICE_STATUS', 
              f'Changed device {device_id} status to {new_status}', datetime.now()))
        
        db.commit()
        return jsonify({'success': True, 'new_status': new_status})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    


def init_superadmin(app):
    """Initialize superadmin blueprint"""
    init_db(app)
    app.register_blueprint(superadmin_bp)