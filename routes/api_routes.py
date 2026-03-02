from flask import Blueprint, request, jsonify
from models import db, Parameter, SensorData, Device
from datetime import datetime

api_bp = Blueprint('api', __name__)

@api_bp.route('/sensor_data', methods=['POST'])
def receive_sensor_data():
    """API endpoint for devices to send sensor data"""
    try:
        data = request.get_json()
        
        # Validate required fields
        if not all(k in data for k in ['device_id', 'parameter_type', 'value']):
            return jsonify({'error': 'Missing required fields'}), 400
        
        device_id = data['device_id']
        parameter_type = data['parameter_type']
        
        # Find or create parameter
        parameter = Parameter.query.filter_by(
            device_id=device_id,
            sensor_type=parameter_type  # Using sensor_type field which stores the parameter type
        ).first()
        
        if not parameter:
            # Get the device to ensure it exists
            device = Device.query.get(device_id)
            if not device:
                return jsonify({'error': 'Device not found'}), 404
            
            parameter = Parameter(
                name=f"{parameter_type} Parameter",
                sensor_type=parameter_type,
                unit=data.get('unit'),
                device_id=device_id,
                user_id=device.user_id  # Use device owner's user_id
            )
            db.session.add(parameter)
            db.session.commit()
        
        # Create sensor data record
        sensor_data = SensorData(
            device_id=device_id,
            parameter_id=parameter.id,
            value=data['value'],
            unit=data.get('unit'),
            parameter_type=parameter_type,
            latitude=data.get('latitude'),
            longitude=data.get('longitude'),
            user_id=parameter.user_id  # Use parameter's user_id
        )
        
        db.session.add(sensor_data)
        
        # Update device last_seen
        device = Device.query.get(device_id)
        if device:
            device.last_seen = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({'message': 'Data received successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500