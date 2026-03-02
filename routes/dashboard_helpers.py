# routes/dashboard_helpers.py
from datetime import datetime, timedelta
from models import Device,SensorData, DashboardSensor,Parameter
from sqlalchemy import func

def get_dashboard_parameters_data(dashboard_id, start_date):
    """Shared function to get dashboard parameter data"""
    try:
        # Get dashboard devices (since DashboardSensor links to devices)
        dashboard_devices = DashboardSensor.query.filter_by(dashboard_id=dashboard_id).all()
        device_ids = [ds.device_id for ds in dashboard_devices]
        
        if not device_ids:
            return {'parameters': [], 'devices': [], 'parameter_data': {}, 'device_ids': []}
        
        # Get all devices in the dashboard
        devices = Device.query.filter(Device.id.in_(device_ids)).all()
        
        # Get all parameters for these devices
        parameters = Parameter.query.filter(Parameter.device_id.in_(device_ids)).all()
        parameter_ids = [p.id for p in parameters]
        
        # Get sensor data for these parameters
        sensor_data_records = SensorData.query.filter(
            SensorData.parameter_id.in_(parameter_ids),
            SensorData.timestamp >= start_date
        ).order_by(SensorData.timestamp.asc()).all()
        
        # Group by parameter_id
        parameter_data_by_param = {}
        for record in sensor_data_records:
            if record.parameter_id not in parameter_data_by_param:
                parameter_data_by_param[record.parameter_id] = []
            parameter_data_by_param[record.parameter_id].append(record)
        
        return {
            'parameters': parameters,
            'devices': devices,
            'parameter_data': parameter_data_by_param,
            'device_ids': device_ids,
            'parameter_ids': parameter_ids
        }
    except Exception as e:
        print(f"Error in get_dashboard_parameters_data: {str(e)}")
        return {'parameters': [], 'devices': [], 'parameter_data': {}, 'device_ids': [], 'parameter_ids': []}

def calculate_dashboard_statistics(devices, sensors, sensor_data_by_sensor):
    """Calculate dashboard statistics"""
    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    connected_devices = sum(1 for device in devices if device.last_seen and device.last_seen >= one_hour_ago)
    
    active_sensors = 0
    data_points_24h = 0
    
    twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
    
    for sensor in sensors:
        sensor_id = sensor.id
        if sensor_id in sensor_data_by_sensor:
            records = sensor_data_by_sensor[sensor_id]
            # Check if any data in last hour
            recent_records = [r for r in records if r.timestamp >= one_hour_ago]
            if recent_records:
                active_sensors += 1
            
            # Count data points in last 24 hours
            last_24h_records = [r for r in records if r.timestamp >= twenty_four_hours_ago]
            data_points_24h += len(last_24h_records)
    
    return {
        "connected_devices": connected_devices,
        "active_sensors": active_sensors,
        "data_points_24h": data_points_24h
    }

def format_sensor_data_for_frontend(sensor_data_by_sensor, sensors, devices):
    """Format sensor data for frontend consumption"""
    device_map = {device.id: device for device in devices} if devices else {}
    sensor_map = {sensor.id: sensor for sensor in sensors} if sensors else {}
    
    formatted_data = []
    for sensor_id, records in sensor_data_by_sensor.items():
        sensor = sensor_map.get(sensor_id)
        if not sensor:
            continue
            
        device = device_map.get(sensor.device_id) if sensor.device_id else None
        
        # Get latest reading
        latest_record = max(records, key=lambda x: x.timestamp) if records else None
        
        # Get historical values (last 10 readings for mini-charts)
        history_values = [record.value for record in records[-10:]] if records else []
        
        formatted_data.append({
            "id": sensor_id,
            "sensor_id": sensor_id,
            "name": sensor.name,
            "sensor_name": sensor.name,
            "value": latest_record.value if latest_record else 0,
            "current_value": latest_record.value if latest_record else 0,
            "reading": latest_record.value if latest_record else 0,
            "unit": sensor.unit or "",
            "device_id": sensor.device_id,
            "device_name": device.name if device else "Unknown Device",
            "history": history_values,
            "readings": [{"value": record.value, "timestamp": record.timestamp} for record in records],
            "timestamp": latest_record.timestamp if latest_record else None,
            "icon": get_sensor_icon(sensor.sensor_type)
        })
    
    return formatted_data

def format_devices_data(devices):
    """Format devices data for frontend"""
    formatted_devices = []
    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    
    for device in devices:
        is_active = device.last_seen and device.last_seen >= one_hour_ago
        formatted_devices.append({
            "id": device.id,
            "name": device.name,
            "device_name": device.name,
            "device_id": device.device_id,
            "is_active": is_active,
            "status": "online" if is_active else "offline",
            "last_seen": device.last_seen.isoformat() if device.last_seen else None,
            "created_at": device.created_at.isoformat() if device.created_at else None
        })
    
    return formatted_devices

def prepare_chart_data(sensor_data_by_sensor, sensors, start_date):
    """Prepare chart data for the frontend"""
    # Generate date labels based on time range
    days_diff = (datetime.utcnow() - start_date).days
    num_days = max(days_diff, 1)
    
    labels = []
    for i in range(num_days):
        date = start_date + timedelta(days=i)
        labels.append(date.strftime('%b %d'))
    
    # Prepare datasets for each sensor
    datasets = []
    colors = ['#4e73df', '#1cc88a', '#36b9cc', '#f6c23e', '#e74a3b', '#6f42c1']
    
    for i, sensor in enumerate(sensors):
        color = colors[i % len(colors)]
        sensor_id = sensor.id
        
        # Get data for this sensor
        sensor_records = sensor_data_by_sensor.get(sensor_id, [])
        
        # Group by day and calculate average
        daily_data = {}
        for record in sensor_records:
            day_key = record.timestamp.strftime('%b %d')
            if day_key not in daily_data:
                daily_data[day_key] = []
            daily_data[day_key].append(record.value)
        
        # Create data array matching labels
        data = []
        for label in labels:
            if label in daily_data and daily_data[label]:
                avg_value = sum(daily_data[label]) / len(daily_data[label])
                data.append(round(avg_value, 2))
            else:
                data.append(None)
        
        datasets.append({
            "label": f"{sensor.name} ({sensor.unit})" if sensor.unit else sensor.name,
            "data": data,
            "borderColor": color,
            "backgroundColor": color + '20',
            "tension": 0.4
        })
    
    return {
        "labels": labels,
        "datasets": datasets
    }

def format_sensors_data(sensors, devices):
    """Format sensors data for frontend"""
    device_map = {device.id: device for device in devices} if devices else {}
    
    formatted_sensors = []
    for sensor in sensors:
        device = device_map.get(sensor.device_id) if sensor.device_id else None
        formatted_sensors.append({
            "id": sensor.id,
            "name": sensor.name,
            "sensor_type": sensor.sensor_type,
            "unit": sensor.unit or "",
            "device_id": sensor.device_id,
            "device_name": device.name if device else "Unknown Device",
            "icon": get_sensor_icon(sensor.sensor_type)
        })
    
    return formatted_sensors

def get_sensor_icon(sensor_type):
    """Map sensor type to FontAwesome icon"""
    icon_map = {
        'temperature': 'thermometer-half',
        'humidity': 'tint',
        'pressure': 'compress-arrows-alt',
        'voltage': 'bolt',
        'current': 'bolt',
        'power': 'plug',
        'light': 'lightbulb',
        'motion': 'running',
        'door': 'door-open',
        'water': 'water',
        'gas': 'wind',
        'smoke': 'fire',
        'vibration': 'wave-square',
        'ph': 'flask',
        'co2': 'cloud',
        'sound': 'volume-up'
    }
    return icon_map.get(sensor_type, 'chart-line')

def get_recent_alerts(dashboard_id):
    """Get recent alerts for the dashboard - placeholder"""
    # TODO: Implement based on your alert system
    return []

def calculate_sensor_stats(sensor_id):
    """Calculate min, max, avg for a sensor (last 24 hours)"""
    twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
    stats = SensorData.query.filter(
        SensorData.sensor_id == sensor_id,
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