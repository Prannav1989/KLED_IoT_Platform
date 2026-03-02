# services/data_processor.py
from datetime import datetime
from extensions import db
from models import MQTTMessage, SensorData, Sensor, Device
import json

class DataProcessor:
    @staticmethod
    def process_user_messages(user_id):
        """Process MQTT messages for a specific user's devices"""
        try:
            # Get user's devices
            devices = Device.query.filter_by(user_id=user_id).all()
            device_topics = [device.mqtt_topic for device in devices]
            
            if not device_topics:
                return 0
                
            # Get unprocessed messages for this user's devices
            unprocessed = MQTTMessage.query.filter(
                MQTTMessage.topic.in_(device_topics),
                MQTTMessage.processed == False
            ).all()
            
            for message in unprocessed:
                DataProcessor._process_single_message(message)
                message.processed = True
                message.processed_at = datetime.now()
            
            db.session.commit()
            return len(unprocessed)
            
        except Exception as e:
            db.session.rollback()
            print(f"Error processing messages for user {user_id}: {e}")
            return 0

    @staticmethod
    def _process_single_message(message):
        """Process a single MQTT message"""
        try:
            # Find device by topic
            device = Device.query.filter_by(mqtt_topic=message.topic).first()
            if not device:
                return
                
            # Update device last seen
            device.last_seen = datetime.now()
            
            # Parse and process the message
            data = json.loads(message.payload)
            
            if isinstance(data, dict):
                if 'value' in data:
                    DataProcessor._create_sensor_data(device, data)
                elif 'readings' in data and isinstance(data['readings'], dict):
                    for sensor_type, reading in data['readings'].items():
                        if isinstance(reading, dict):
                            reading['sensor_type'] = sensor_type
                            DataProcessor._create_sensor_data(device, reading)
                        
        except json.JSONDecodeError:
            # Handle non-JSON data
            DataProcessor._create_raw_data(device, message.payload)
        except Exception as e:
            print(f"Error processing message {message.id}: {e}")

    @staticmethod
    def _create_sensor_data(device, reading):
        """Create sensor data entry from a reading"""
        sensor_type = reading.get('sensor_type', 'unknown')
        value = reading.get('value')
        unit = reading.get('unit', '')
        
        if value is None:
            return
            
        # Find or create sensor
        sensor = Sensor.query.filter_by(
            device_id=device.id,
            sensor_type=sensor_type
        ).first()
        
        if not sensor:
            sensor = Sensor(
                name=f"{device.name} - {sensor_type}",
                sensor_type=sensor_type,
                unit=unit,
                device_id=device.id,
                user_id=device.user_id
            )
            db.session.add(sensor)
            db.session.flush()
        
        # Create sensor data entry
        sensor_data = SensorData(
            device_id=device.id,
            sensor_id=sensor.id,
            value=float(value),
            unit=unit,
            timestamp=datetime.now(),
            latitude=reading.get('latitude'),
            longitude=reading.get('longitude')
        )
        db.session.add(sensor_data)

    @staticmethod
    def _create_raw_data(device, payload):
        """Handle non-JSON raw data"""
        sensor = Sensor.query.filter_by(
            device_id=device.id,
            sensor_type='raw'
        ).first()
        
        if not sensor:
            sensor = Sensor(
                name=f"{device.name} - Raw Data",
                sensor_type='raw',
                unit='',
                device_id=device.id,
                user_id=device.user_id
            )
            db.session.add(sensor)
            db.session.flush()
        
        sensor_data = SensorData(
            device_id=device.id,
            sensor_id=sensor.id,
            value=0,
            unit='',
            timestamp=datetime.now(),
            raw_data=payload
        )
        db.session.add(sensor_data)