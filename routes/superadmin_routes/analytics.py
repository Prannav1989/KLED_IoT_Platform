from flask import Blueprint, render_template, jsonify, request
from models import db, Dashboard, Device, SensorData, DashboardSensor, AlertRule, NavigationSettings
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from sqlalchemy import func, and_

analytics_bp = Blueprint("analytics", __name__, url_prefix="/superadmin/analytics")

@analytics_bp.route("/<int:dashboard_id>")
@login_required
def analytics_page(dashboard_id):
    """Main analytics page for a dashboard"""
    # Get dashboard
    dashboard = Dashboard.query.get_or_404(dashboard_id)
    
    # # Check if user has access to this dashboard
    # if current_user.role != 'superadmin' and current_user.company_id != dashboard.company_id:
    #     return "Access denied", 403
    
    # Get navigation settings for this dashboard
    navigation_settings = NavigationSettings.query.filter_by(dashboard_id=dashboard_id).first()
    if navigation_settings:
        nav_settings = {
            "analytics": navigation_settings.analytics,
            "reports": navigation_settings.reports,
            "settings": navigation_settings.settings,
            "download": navigation_settings.download,
            "support": navigation_settings.support,
            "dashboard_management": navigation_settings.dashboard_management
        }
    else:
        # Default navigation settings
        nav_settings = {
            "analytics": True,
            "reports": True,
            "settings": True,
            "download": True,
            "support": True,
            "dashboard_management": True
        }

    # Get linked devices from DashboardSensor
    linked_device_entries = DashboardSensor.query.filter_by(dashboard_id=dashboard_id).all()
    linked_device_ids = [entry.device_id for entry in linked_device_entries]

    # Get Device objects
    devices = Device.query.filter(Device.id.in_(linked_device_ids)).all()
    total_devices = len(devices)

    # Get active devices (last_seen within 1 hour)
    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    active_devices = 0
    for device in devices:
        if device.last_seen:
            # Convert to naive datetime if needed
            if device.last_seen.tzinfo:
                last_seen_naive = device.last_seen.replace(tzinfo=None)
            else:
                last_seen_naive = device.last_seen
            if last_seen_naive >= one_hour_ago:
                active_devices += 1

    # Get total linked sensors (same as total_devices in your structure)
    total_linked_sensors = len(linked_device_entries)
    
    # Calculate total parameters (count distinct parameter types from sensor_data)
    total_parameters = 0
    if linked_device_ids:
        result = db.session.query(
            func.count(func.distinct(SensorData.parameter_type))
        ).filter(
            SensorData.device_id.in_(linked_device_ids)
        ).first()
        total_parameters = result[0] if result and result[0] else 0

    # Get devices with sensor data
    devices_data = get_real_devices_data(devices)

    return render_template(
        "dashboard/analytics.html",
        dashboard=dashboard,
        navigation_settings=nav_settings,
        total_devices=total_devices,
        active_devices=active_devices,
        total_parameters=total_parameters,
        total_linked_sensors=total_linked_sensors,
        devices_data=devices_data,
        dashboard_id=dashboard_id
    )

    
@analytics_bp.route("/<int:dashboard_id>/data")
@login_required
def dashboard_data(dashboard_id):
    """API endpoint that provides data in the format expected by frontend JavaScript"""
    try:
        # Get time range from query parameter
        time_range = request.args.get('timeRange', '24h')
        
        # Parse custom date range
        start_date, end_date = parse_time_range(time_range)
        
        # Get dashboard devices
        dashboard_devices = DashboardSensor.query.filter_by(dashboard_id=dashboard_id).all()
        device_ids = [dd.device_id for dd in dashboard_devices]

        # Get devices for this dashboard
        devices = Device.query.filter(Device.id.in_(device_ids)).all()
        
        # Get sensor data for the time range
        sensor_data = get_sensor_data_for_devices(device_ids, start_date, end_date)
        
        # Prepare chart data
        chart_data = prepare_chart_data_for_devices(sensor_data, devices, start_date, end_date, time_range)
        
        # Calculate statistics
        statistics = calculate_dashboard_statistics_for_devices(devices, sensor_data, start_date)
        
        # Get recent alerts
        alerts = get_recent_alerts(dashboard_id, start_date)

        response_data = {
            "sensors": format_devices_as_sensors_data(devices, sensor_data),
            "sensor_data": format_sensor_data_for_devices(sensor_data, devices),
            "devices": format_devices_data(devices),
            "chart_data": chart_data,
            "statistics": statistics,
            "alerts": alerts,
            "debug": {
                "device_count": len(devices),
                "sensor_data_combinations": len(sensor_data),
                "time_range": time_range
            }
        }

        return jsonify(response_data)

    except Exception as e:
        return jsonify({"error": "Failed to load dashboard data", "details": str(e)}), 500

def parse_time_range(time_range):
    """Parse time range string into start and end dates"""
    
    now = datetime.utcnow()
    
    if time_range.startswith('custom_'):
        # Format: custom_YYYY-MM-DD_YYYY-MM-DD
        parts = time_range.split('_')
        start_date = datetime.strptime(parts[1], '%Y-%m-%d')
        end_date = datetime.strptime(parts[2], '%Y-%m-%d')
        end_date = end_date.replace(hour=23, minute=59, second=59)
    elif time_range == '7d':
        start_date = now - timedelta(days=7)
        end_date = now
    elif time_range == '30d':
        start_date = now - timedelta(days=30)
        end_date = now
    elif time_range == '90d':
        start_date = now - timedelta(days=90)
        end_date = now
    elif time_range == '1y':
        start_date = now - timedelta(days=365)
        end_date = now
    elif time_range == '2y':
        start_date = now - timedelta(days=730)
        end_date = now
    else:  # 24h default
        start_date = now - timedelta(hours=24)
        end_date = now
    
    # Make dates timezone-naive
    if start_date.tzinfo:
        start_date = start_date.replace(tzinfo=None)
    if end_date.tzinfo:
        end_date = end_date.replace(tzinfo=None)
    
    return start_date, end_date

def get_sensor_data_for_devices(device_ids, start_date, end_date):
    """Get sensor data using device_ids and separate by parameter type"""
    
    if not device_ids:
        return {}
    
    # Query sensor_data table
    sensor_data_records = SensorData.query.filter(
        SensorData.device_id.in_(device_ids),
        SensorData.timestamp >= start_date,
        SensorData.timestamp <= end_date
    ).order_by(SensorData.timestamp.asc()).all()
    
    # Organize by device_id AND parameter_type
    sensor_data_by_device_param = {}
    for record in sensor_data_records:
        # Use parameter_type, default to 'unknown' if None
        param_type = record.parameter_type or 'unknown'
        key = (record.device_id, param_type)
        if key not in sensor_data_by_device_param:
            sensor_data_by_device_param[key] = []
        sensor_data_by_device_param[key].append(record)
    
    return sensor_data_by_device_param

def prepare_chart_data_for_devices(sensor_data_by_device_param, devices, start_date, end_date, time_range):
    """Prepare chart data separating different parameter types"""
    
    total_days = (end_date - start_date).days
    
    # Determine aggregation level based on time range
    if time_range in ['2y', '1y']:
        # Monthly aggregation
        labels = []
        current_date = start_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        while current_date <= end_date:
            labels.append(current_date.strftime('%b %Y'))
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)
        aggregation_type = 'monthly'
        
    elif time_range in ['90d', '30d']:
        # Weekly aggregation
        labels = []
        current_date = start_date
        current_date = current_date - timedelta(days=current_date.weekday())
        while current_date <= end_date:
            labels.append(current_date.strftime('%b %d'))
            current_date += timedelta(days=7)
        aggregation_type = 'weekly'
        
    else:
        # Daily or hourly aggregation based on range
        if total_days <= 1:
            # Hourly aggregation for 24h range
            labels = []
            for i in range(24):
                hour = (start_date + timedelta(hours=i)).hour
                labels.append(f"{hour:02d}:00")
            aggregation_type = 'hourly'
        else:
            # Daily aggregation
            labels = []
            for i in range(total_days + 1):
                date = start_date + timedelta(days=i)
                labels.append(date.strftime('%b %d'))
            aggregation_type = 'daily'
    
    datasets = []
    colors = ['#4e73df', '#1cc88a', '#36b9cc', '#f6c23e', '#e74a3b', '#6f42c1', '#20c9a6', '#858796', '#fd7e14', '#6610f2']
    
    device_map = {device.id: device for device in devices}
    color_index = 0
    
    # Process each device-parameter combination
    for (device_id, param_type), records in sensor_data_by_device_param.items():
        device = device_map.get(device_id)
        if not device:
            continue
            
        color = colors[color_index % len(colors)]
        color_index += 1

        if aggregation_type == 'monthly':
            # Monthly aggregation
            monthly_data = {}
            for record in records:
                timestamp = record.timestamp.replace(tzinfo=None) if record.timestamp.tzinfo else record.timestamp
                month_key = timestamp.strftime('%b %Y')
                monthly_data.setdefault(month_key, []).append(record.value)
            
            data = []
            for label in labels:
                if label in monthly_data and monthly_data[label]:
                    avg_value = sum(monthly_data[label]) / len(monthly_data[label])
                    data.append(round(avg_value, 2))
                else:
                    data.append(None)
                    
        elif aggregation_type == 'weekly':
            # Weekly aggregation
            weekly_data = {}
            for record in records:
                record_date = record.timestamp.replace(tzinfo=None) if record.timestamp.tzinfo else record.timestamp
                week_start = record_date - timedelta(days=record_date.weekday())
                week_key = week_start.strftime('%b %d')
                weekly_data.setdefault(week_key, []).append(record.value)
            
            data = []
            for label in labels:
                if label in weekly_data and weekly_data[label]:
                    avg_value = sum(weekly_data[label]) / len(weekly_data[label])
                    data.append(round(avg_value, 2))
                else:
                    data.append(None)
                    
        elif aggregation_type == 'hourly':
            # Hourly aggregation
            hourly_data = {}
            for record in records:
                timestamp = record.timestamp.replace(tzinfo=None) if record.timestamp.tzinfo else record.timestamp
                hour_key = f"{timestamp.hour:02d}:00"
                hourly_data.setdefault(hour_key, []).append(record.value)
            
            data = []
            for label in labels:
                if label in hourly_data and hourly_data[label]:
                    avg_value = sum(hourly_data[label]) / len(hourly_data[label])
                    data.append(round(avg_value, 2))
                else:
                    data.append(None)
                    
        else:
            # Daily aggregation
            daily_data = {}
            for record in records:
                timestamp = record.timestamp.replace(tzinfo=None) if record.timestamp.tzinfo else record.timestamp
                day_key = timestamp.strftime('%b %d')
                daily_data.setdefault(day_key, []).append(record.value)

            data = []
            for label in labels:
                if label in daily_data and daily_data[label]:
                    avg_value = sum(daily_data[label]) / len(daily_data[label])
                    data.append(round(avg_value, 2))
                else:
                    data.append(None)

        # Get unit from records
        unit = ''
        if records:
            unit = records[0].unit or ''
        
        non_null_data = len([d for d in data if d is not None])
        
        # Only add dataset if there's actual data
        if non_null_data > 0:
            datasets.append({
                "label": f"{device.name} - {param_type} ({unit})" if unit else f"{device.name} - {param_type}",
                "data": data,
                "borderColor": color,
                "backgroundColor": color + '20',
                "tension": 0.4,
                "pointBackgroundColor": color,
                "pointBorderColor": '#fff',
                "pointRadius": 3,
                "fill": False
            })
    
    return {"labels": labels, "datasets": datasets}

def calculate_dashboard_statistics_for_devices(devices, sensor_data_by_device_param, start_date):
    """Calculate dashboard statistics for devices-as-sensors model"""
    now = datetime.utcnow()
    one_hour_ago = now - timedelta(hours=1)
    twenty_four_hours_ago = now - timedelta(hours=24)
    
    # Count connected devices (active in last hour)
    connected_devices = 0
    for device in devices:
        if device.last_seen:
            last_seen_naive = device.last_seen.replace(tzinfo=None) if device.last_seen.tzinfo else device.last_seen
            if last_seen_naive >= one_hour_ago:
                connected_devices += 1
    
    # Count active sensors (have data in last hour)
    active_parameters = set()
    data_points_24h = 0
    latest_values = []
    
    for (device_id, param_type), records in sensor_data_by_device_param.items():
        if not records:
            continue
            
        # Check if any data in last hour for this parameter
        for r in records:
            timestamp_naive = r.timestamp.replace(tzinfo=None) if r.timestamp.tzinfo else r.timestamp
            if timestamp_naive >= one_hour_ago:
                active_parameters.add((device_id, param_type))
                break
        
        # Count data points in last 24 hours
        for r in records:
            timestamp_naive = r.timestamp.replace(tzinfo=None) if r.timestamp.tzinfo else r.timestamp
            if timestamp_naive >= twenty_four_hours_ago:
                data_points_24h += 1
                latest_values.append({
                    "device_id": device_id,
                    "param_type": param_type,
                    "value": r.value,
                    "timestamp": timestamp_naive
                })
    
    # Get most recent reading
    latest_reading = None
    if latest_values:
        latest_values.sort(key=lambda x: x["timestamp"], reverse=True)
        latest_reading = latest_values[0] if latest_values else None
    
    return {
        "connected_devices": connected_devices,
        "active_sensors": len(active_parameters),
        "data_points_24h": data_points_24h,
        "latest_reading": latest_reading
    }

def format_devices_as_sensors_data(devices, sensor_data_by_device_param):
    """Format devices as sensors data for frontend, separating parameter types"""
    formatted_sensors = []
    
    for device in devices:
        # Find all parameter types for this device
        param_types = set()
        for (device_id, param_type) in sensor_data_by_device_param.keys():
            if device_id == device.id:
                param_types.add(param_type)
        
        # If no specific parameter types found, create a default sensor
        if not param_types:
            formatted_sensors.append({
                "id": device.id,
                "name": device.name,
                "sensor_type": 'sensor',
                "unit": '',
                "device_id": device.id,
                "device_name": device.name,
                "icon": get_sensor_icon('sensor'),
                "status": "online" if device.is_active else "offline"
            })
        else:
            # Create separate entries for each parameter type
            for param_type in param_types:
                # Get unit for this parameter type
                unit = ''
                key = (device.id, param_type)
                if key in sensor_data_by_device_param and sensor_data_by_device_param[key]:
                    unit = sensor_data_by_device_param[key][0].unit or ''
                
                formatted_sensors.append({
                    "id": f"{device.id}_{param_type}",
                    "name": f"{device.name} - {param_type}",
                    "sensor_type": param_type,
                    "unit": unit,
                    "device_id": device.id,
                    "device_name": device.name,
                    "parameter_type": param_type,
                    "icon": get_sensor_icon(param_type),
                    "status": "online" if device.is_active else "offline"
                })
    
    return formatted_sensors

def format_sensor_data_for_devices(sensor_data_by_device_param, devices):
    """Format sensor data for frontend separating by parameter types"""
    device_map = {device.id: device for device in devices}
    
    formatted_data = []
    
    for (device_id, param_type), records in sensor_data_by_device_param.items():
        device = device_map.get(device_id)
        if not device:
            continue
        
        if not records:
            continue
            
        # Get latest reading for this parameter type
        latest_record = max(records, key=lambda x: x.timestamp) if records else None
        
        # Get historical values (last 10 readings)
        history_values = [record.value for record in records[-10:]] if records else []
        
        # Get unit from records
        unit = ''
        if records:
            unit = records[0].unit or ''
        
        # Calculate stats
        values = [r.value for r in records if r.value is not None]
        min_val = min(values) if values else 0
        max_val = max(values) if values else 0
        avg_val = sum(values) / len(values) if values else 0
        
        formatted_data.append({
            "id": f"{device_id}_{param_type}",
            "sensor_id": device_id,
            "name": f"{device.name} - {param_type}",
            "sensor_name": param_type,
            "value": latest_record.value if latest_record else 0,
            "current_value": latest_record.value if latest_record else 0,
            "reading": latest_record.value if latest_record else 0,
            "unit": unit,
            "device_id": device_id,
            "device_name": device.name,
            "parameter_type": param_type,
            "history": history_values,
            "readings": [{"value": record.value, "timestamp": record.timestamp.isoformat()} for record in records[-5:]],
            "timestamp": latest_record.timestamp.isoformat() if latest_record else None,
            "icon": get_sensor_icon(param_type),
            "status": "online" if device.is_active else "offline",
            "stats": {
                "min": round(min_val, 2),
                "max": round(max_val, 2),
                "avg": round(avg_val, 2)
            }
        })
    
    return formatted_data

def format_devices_data(devices):
    """Format devices data for frontend"""
    formatted_devices = []
    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    
    for device in devices:
        is_active = False
        if device.last_seen:
            last_seen_naive = device.last_seen.replace(tzinfo=None) if device.last_seen.tzinfo else device.last_seen
            is_active = last_seen_naive >= one_hour_ago
        
        # Get latest sensor data for this device
        latest_data = SensorData.query.filter_by(device_id=device.id).order_by(SensorData.timestamp.desc()).first()
        
        formatted_devices.append({
            "id": device.id,
            "name": device.name,
            "device_name": device.name,
            "device_id": device.device_id,
            "mqtt_topic": device.mqtt_topic,
            "is_active": is_active,
            "status": "online" if is_active else "offline",
            "last_seen": device.last_seen.isoformat() if device.last_seen else None,
            "created_at": device.created_at.isoformat() if device.created_at else None,
            "description": device.description or "",
            "latest_value": latest_data.value if latest_data else None,
            "latest_unit": latest_data.unit if latest_data else "",
            "parameter_type": latest_data.parameter_type if latest_data else ""
        })
    
    return formatted_devices

def get_recent_alerts(dashboard_id=None, start_date=None):
    """Get recent alerts for the dashboard"""
    try:
        # Get devices for this dashboard
        dashboard_devices = DashboardSensor.query.filter_by(dashboard_id=dashboard_id).all()
        device_ids = [dd.device_id for dd in dashboard_devices]
        
        if not device_ids:
            return []
        
        # Query alerts - you might need to adjust this based on your alert system
        alerts = AlertRule.query.filter(
            AlertRule.enabled == True
        ).order_by(AlertRule.created_at.desc()).limit(5).all()
        
        formatted_alerts = []
        for alert in alerts:
            formatted_alerts.append({
                "id": alert.id,
                "name": alert.name,
                "metric": alert.metric,
                "operator": alert.operator,
                "threshold": alert.threshold,
                "action": alert.action,
                "created_at": alert.created_at.isoformat() if alert.created_at else None
            })
        
        return formatted_alerts
    except Exception as e:
        return []

def get_real_devices_data(devices):
    """Get devices with their sensor data"""
    devices_data = []

    for device in devices:
        is_active = False
        if device.last_seen:
            last_seen_naive = device.last_seen.replace(tzinfo=None) if device.last_seen.tzinfo else device.last_seen
            is_active = last_seen_naive >= (datetime.utcnow() - timedelta(hours=1))

        device_info = {
            'device': device,
            'is_active': is_active,
            'last_seen': device.last_seen,
            'parameters': []
        }

        # Get all parameter types for this device
        parameter_types = SensorData.query.with_entities(
            SensorData.parameter_type
        ).filter_by(
            device_id=device.id
        ).distinct().all()
        
        for param_type_tuple in parameter_types:
            param_type = param_type_tuple[0]
            if not param_type:
                continue
                
            # Get latest data for this parameter type
            latest_data = SensorData.query.filter_by(
                device_id=device.id,
                parameter_type=param_type
            ).order_by(SensorData.timestamp.desc()).first()

            # Historical data (last 24 hours)
            twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
            historical_data = SensorData.query.filter(
                SensorData.device_id == device.id,
                SensorData.parameter_type == param_type,
                SensorData.timestamp >= twenty_four_hours_ago
            ).order_by(SensorData.timestamp.asc()).all()

            # Calculate stats
            stats = calculate_device_stats(device.id, param_type)

            # Get unit
            unit = latest_data.unit if latest_data else ''

            parameter = {
                'name': param_type,
                'value': latest_data.value if latest_data else 0,
                'unit': unit,
                'icon': get_sensor_icon(param_type),
                'history': [data.value for data in historical_data] if historical_data else [],
                'stats': stats
            }

            device_info['parameters'].append(parameter)

        devices_data.append(device_info)

    return devices_data

def calculate_device_stats(device_id, parameter_type):
    """Calculate min, max, avg for a device and parameter type (last 24 hours)"""
    twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
    stats = SensorData.query.filter(
        SensorData.device_id == device_id,
        SensorData.parameter_type == parameter_type,
        SensorData.timestamp >= twenty_four_hours_ago
    ).with_entities(
        func.min(SensorData.value).label('min'),
        func.max(SensorData.value).label('max'),
        func.avg(SensorData.value).label('avg')
    ).first()

    return {
        'min': round(stats.min, 2) if stats and stats.min is not None else 0,
        'max': round(stats.max, 2) if stats and stats.max is not None else 0,
        'avg': round(stats.avg, 2) if stats and stats.avg is not None else 0
    }

def get_sensor_icon(sensor_type):
    """Map sensor type to FontAwesome icon"""
    icon_map = {
        'temperature': 'thermometer-half',
        'Temperature': 'thermometer-half',
        'Temp': 'thermometer-half',
        'temp': 'thermometer-half',
        'humidity': 'tint',
        'Humidity': 'tint',
        'humidity': 'tint',
        'pressure': 'compress-arrows-alt',
        'Pressure': 'compress-arrows-alt',
        'pressure': 'compress-arrows-alt',
        'voltage': 'bolt',
        'Voltage': 'bolt',
        'voltage': 'bolt',
        'current': 'bolt',
        'Current': 'bolt',
        'current': 'bolt',
        'power': 'plug',
        'Power': 'plug',
        'power': 'plug',
        'light': 'lightbulb',
        'Light': 'lightbulb',
        'light': 'lightbulb',
        'motion': 'running',
        'Motion': 'running',
        'motion': 'running',
        'door': 'door-open',
        'Door': 'door-open',
        'door': 'door-open',
        'water': 'water',
        'Water': 'water',
        'water': 'water',
        'gas': 'wind',
        'Gas': 'wind',
        'gas': 'wind',
        'smoke': 'fire',
        'Smoke': 'fire',
        'smoke': 'fire',
        'vibration': 'wave-square',
        'Vibration': 'wave-square',
        'vibration': 'wave-square',
        'ph': 'flask',
        'pH': 'flask',
        'ph': 'flask',
        'co2': 'cloud',
        'CO2': 'cloud',
        'co2': 'cloud',
        'sound': 'volume-up',
        'Sound': 'volume-up',
        'sound': 'volume-up',
        'level': 'chart-line',
        'Level': 'chart-line',
        'level': 'chart-line',
        'flow': 'tachometer-alt',
        'Flow': 'tachometer-alt',
        'flow': 'tachometer-alt',
        'speed': 'tachometer-alt',
        'Speed': 'tachometer-alt',
        'speed': 'tachometer-alt'
    }
    return icon_map.get(sensor_type, 'chart-line')

# Debug and utility routes
@analytics_bp.route("/<int:dashboard_id>/debug")
@login_required
def debug_dashboard(dashboard_id):
    """Debug endpoint to check database state"""
    try:
        dashboard = Dashboard.query.get_or_404(dashboard_id)
        
        # Check user access
        if current_user.role != 'superadmin' and current_user.company_id != dashboard.company_id:
            return jsonify({"error": "Access denied"}), 403
        
        # Get dashboard devices
        dashboard_devices = DashboardSensor.query.filter_by(dashboard_id=dashboard_id).all()
        device_ids = [dd.device_id for dd in dashboard_devices]
        
        devices = Device.query.filter(Device.id.in_(device_ids)).all()
        
        # Get sample sensor data
        sensor_data = SensorData.query.filter(SensorData.device_id.in_(device_ids)).limit(10).all()
        
        # Get parameter types for each device
        param_types_by_device = {}
        for device in devices:
            types = SensorData.query.with_entities(
                SensorData.parameter_type
            ).filter_by(
                device_id=device.id
            ).distinct().all()
            param_types_by_device[device.id] = [t[0] for t in types if t[0]]
        
        debug_info = {
            "dashboard": {
                "id": dashboard.id,
                "name": dashboard.name,
                "company_id": dashboard.company_id
            },
            "dashboard_devices_count": len(dashboard_devices),
            "device_ids": device_ids,
            "devices_count": len(devices),
            "devices": [{
                "id": d.id, 
                "name": d.name, 
                "device_id": d.device_id,
                "last_seen": d.last_seen.isoformat() if d.last_seen else None,
                "sensor_model_id": d.sensor_model_id,
                "is_active": d.is_active
            } for d in devices],
            "parameter_types_by_device": param_types_by_device,
            "sensor_data_samples": [{
                "id": s.id, 
                "device_id": s.device_id, 
                "parameter_type": s.parameter_type, 
                "parameter_id": s.parameter_id,
                "value": s.value, 
                "unit": s.unit,
                "timestamp": s.timestamp.isoformat()
            } for s in sensor_data],
            "total_sensor_data_count": SensorData.query.filter(SensorData.device_id.in_(device_ids)).count()
        }
        
        return jsonify(debug_info)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@analytics_bp.route("/<int:dashboard_id>/health")
@login_required
def health_check(dashboard_id):
    """Check database connectivity and data availability"""
    try:
        # Check if dashboard exists
        dashboard = Dashboard.query.get(dashboard_id)
        if not dashboard:
            return jsonify({"error": "Dashboard not found"}), 404
        
        # Check user access
        if current_user.role != 'superadmin' and current_user.company_id != dashboard.company_id:
            return jsonify({"error": "Access denied"}), 403
        
        # Get dashboard devices
        dashboard_devices = DashboardSensor.query.filter_by(dashboard_id=dashboard_id).all()
        device_ids = [dd.device_id for dd in dashboard_devices]
        
        # Check devices
        devices = Device.query.filter(Device.id.in_(device_ids)).all()
        
        # Check sensor data
        sensor_count = SensorData.query.filter(SensorData.device_id.in_(device_ids)).count()
        
        # Check parameter types
        param_types = SensorData.query.with_entities(
            SensorData.parameter_type
        ).filter(
            SensorData.device_id.in_(device_ids)
        ).distinct().all()
        
        return jsonify({
            "status": "healthy",
            "dashboard": {
                "id": dashboard.id,
                "name": dashboard.name
            },
            "device_count": len(devices),
            "devices": [{"id": d.id, "name": d.name, "last_seen": d.last_seen.isoformat() if d.last_seen else None, "is_active": d.is_active} for d in devices],
            "sensor_data_records": sensor_count,
            "parameter_types": [p[0] for p in param_types if p[0]],
            "database": "connected"
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@analytics_bp.route("/<int:dashboard_id>/test-query")
@login_required
def test_query(dashboard_id):
    """Test specific queries for debugging"""
    try:
        dashboard = Dashboard.query.get_or_404(dashboard_id)
        
        # Check user access
        if current_user.role != 'superadmin' and current_user.company_id != dashboard.company_id:
            return jsonify({"error": "Access denied"}), 403
        
        # Get a specific device to test
        dashboard_devices = DashboardSensor.query.filter_by(dashboard_id=dashboard_id).first()
        if not dashboard_devices:
            return jsonify({"error": "No devices linked to dashboard"}), 404
        
        device_id = dashboard_devices.device_id
        device = Device.query.get(device_id)
        
        # Get all sensor data for this device
        all_data = SensorData.query.filter_by(device_id=device_id).order_by(SensorData.timestamp.desc()).limit(20).all()
        
        # Get parameter types
        param_types = SensorData.query.with_entities(
            SensorData.parameter_type
        ).filter_by(
            device_id=device_id
        ).distinct().all()
        
        # Get data from last 24 hours
        twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
        recent_data = SensorData.query.filter(
            SensorData.device_id == device_id,
            SensorData.timestamp >= twenty_four_hours_ago
        ).order_by(SensorData.timestamp.desc()).all()
        
        return jsonify({
            "device": {
                "id": device.id,
                "name": device.name,
                "device_id": device.device_id,
                "sensor_model_id": device.sensor_model_id,
                "is_active": device.is_active,
                "last_seen": device.last_seen.isoformat() if device.last_seen else None
            },
            "parameter_types": [p[0] for p in param_types if p[0]],
            "all_data_count": len(all_data),
            "all_data_sample": [{
                "id": d.id,
                "parameter_type": d.parameter_type,
                "value": d.value,
                "unit": d.unit,
                "timestamp": d.timestamp.isoformat()
            } for d in all_data[:5]],
            "recent_data_count": len(recent_data),
            "recent_data_sample": [{
                "id": d.id,
                "parameter_type": d.parameter_type,
                "value": d.value,
                "unit": d.unit,
                "timestamp": d.timestamp.isoformat()
            } for d in recent_data[:5]]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500