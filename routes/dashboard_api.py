from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta

from extensions import db
from models import (
    Dashboard,
    Device,
    DashboardSensor,
    Parameter,
    SensorData
)

dashboard_api_bp = Blueprint(
    "dashboard_api",
    __name__,
    url_prefix="/api/dashboard"
)

# =====================================================
# SHARED HELPER: DASHBOARD DATA (ACTIVE DEVICES ONLY)
# =====================================================
def get_dashboard_sensors_data(dashboard_id, start_date=None):
    """
    Fetch dashboard devices, sensors, and sensor data.
    Only ACTIVE devices (devices.is_active = 1) are included.
    """

    dashboard = Dashboard.query.get_or_404(dashboard_id)

    # 🔹 Devices linked to dashboard AND active
    devices = (
        db.session.query(Device)
        .join(DashboardSensor, DashboardSensor.device_id == Device.id)
        .filter(
            DashboardSensor.dashboard_id == dashboard_id,
            Device.is_active == True
        )
        .all()
    )

    device_ids = [d.id for d in devices]

    # 🔹 Sensors (parameters)
    sensors = (
        Parameter.query.filter(Parameter.device_id.in_(device_ids)).all()
        if device_ids else []
    )

    # 🔹 Sensor data
    sensor_data_query = SensorData.query.filter(
        SensorData.device_id.in_(device_ids)
    )

    if start_date:
        sensor_data_query = sensor_data_query.filter(
            SensorData.timestamp >= start_date
        )

    sensor_data = sensor_data_query.order_by(
        SensorData.timestamp.asc()
    ).all()

    return {
        "devices": devices,
        "sensors": sensors,
        "sensor_data": sensor_data
    }

# =====================================================
# HELPER FUNCTIONS (PREVIOUSLY MISSING)
# =====================================================
def calculate_dashboard_statistics(devices, sensors, sensor_data):
    return {
        "total_devices": len(devices),
        "total_sensors": len(sensors),
        "total_readings": len(sensor_data)
    }

def format_devices_data(devices):
    return [
        {
            "id": d.id,
            "name": d.name,
            "device_id": d.device_id,
            "is_enabled": d.is_active,
            "last_seen": d.last_seen.isoformat() if d.last_seen else None
        }
        for d in devices
    ]

def format_sensors_data(sensors, devices):
    return [
        {
            "id": s.id,
            "name": s.name,
            "type": s.sensor_type,
            "unit": s.unit,
            "device_id": s.device_id
        }
        for s in sensors
    ]

def format_sensor_data_for_frontend(sensor_data, sensors, devices):
    return [
        {
            "device_id": d.device_id,
            "parameter_id": d.parameter_id,
            "value": d.value,
            "unit": d.unit,
            "timestamp": d.timestamp.isoformat(),
            "parameter_type": d.parameter_type
        }
        for d in sensor_data
    ]

def prepare_chart_data(sensor_data, sensors, start_date):
    # Simple placeholder — frontend can aggregate as needed
    return []

def get_recent_alerts(dashboard_id):
    # Alerts table exists, but logic not implemented yet
    return []

# =====================================================
# DASHBOARD DATA API
# =====================================================
@dashboard_api_bp.route("/<int:dashboard_id>/data")
def get_dashboard_data(dashboard_id):
    try:
        # 🔹 Time range
        time_range = request.args.get("timeRange", "24h")

        if time_range == "7d":
            start_date = datetime.utcnow() - timedelta(days=7)
        elif time_range == "30d":
            start_date = datetime.utcnow() - timedelta(days=30)
        else:
            start_date = datetime.utcnow() - timedelta(hours=24)

        # 🔹 Fetch dashboard data
        dashboard_data = get_dashboard_sensors_data(
            dashboard_id,
            start_date
        )

        # 🔹 Final response
        response = {
            "statistics": calculate_dashboard_statistics(
                dashboard_data["devices"],
                dashboard_data["sensors"],
                dashboard_data["sensor_data"]
            ),
            "devices": format_devices_data(
                dashboard_data["devices"]
            ),
            "sensors": format_sensors_data(
                dashboard_data["sensors"],
                dashboard_data["devices"]
            ),
            "sensor_data": format_sensor_data_for_frontend(
                dashboard_data["sensor_data"],
                dashboard_data["sensors"],
                dashboard_data["devices"]
            ),
            "chart_data": prepare_chart_data(
                dashboard_data["sensor_data"],
                dashboard_data["sensors"],
                start_date
            ),
            "alerts": get_recent_alerts(dashboard_id)
        }

        return jsonify(response)

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({
            "error": "Failed to load dashboard data",
            "details": str(e)
        }), 500
