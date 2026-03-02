# sensor_model.py
import json
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
import psycopg2
from psycopg2.extras import RealDictCursor

@dataclass
class SensorParameter:
    name: str
    sensor_type: str
    unit: str
    mqtt_field: str  # Field name in MQTT payload
    data_type: str = "double precision"
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    
    def to_dict(self):
        return asdict(self)

@dataclass
class SensorModel:
    id: Optional[int] = None
    name: str = ""
    description: str = ""
    manufacturer: str = ""
    parameters: List[SensorParameter] = None
    created_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.parameters is None:
            self.parameters = []
        elif isinstance(self.parameters, str):
            self.parameters = [SensorParameter(**p) for p in json.loads(self.parameters)]
        elif isinstance(self.parameters, list) and len(self.parameters) > 0:
            if isinstance(self.parameters[0], dict):
                self.parameters = [SensorParameter(**p) for p in self.parameters]

class SensorModelManager:
    def __init__(self, db_config):
        self.db_config = db_config
        self.connection = None
        
    def connect(self):
        if not self.connection or self.connection.closed:
            self.connection = psycopg2.connect(**self.db_config)
        return self.connection
    
    # Add to SensorModelManager class
    def update_model(self, model_id: int, updated_model: SensorModel) -> bool:
        """Update an existing sensor model"""
        conn = self.connect()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE sensor_models 
                SET name = %s, description = %s, manufacturer = %s, parameters = %s
                WHERE id = %s
            """, (
                updated_model.name,
                updated_model.description,
                updated_model.manufacturer,
                json.dumps([p.to_dict() for p in updated_model.parameters]),
                model_id
            ))
            
            # Also update normalized parameters table
            cursor.execute("DELETE FROM sensor_model_parameters WHERE sensor_model_id = %s", (model_id,))
            
            for param in updated_model.parameters:
                cursor.execute("""
                    INSERT INTO sensor_model_parameters 
                    (sensor_model_id, parameter_name, parameter_type, unit, mqtt_field_name, min_value, max_value)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    model_id,
                    param.name,
                    param.sensor_type,
                    param.unit,
                    param.mqtt_field,
                    param.min_value,
                    param.max_value
                ))
            
            conn.commit()
            return cursor.rowcount > 0
            
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()

    def delete_model(self, model_id: int) -> bool:
        """Delete a sensor model"""
        conn = self.connect()
        cursor = conn.cursor()
        
        try:
            # Check if model is in use
            cursor.execute("""
                SELECT COUNT(*) FROM devices WHERE sensor_model_id = %s
            """, (model_id,))
            
            device_count = cursor.fetchone()[0]
            if device_count > 0:
                raise ValueError(f"Cannot delete model. It is used by {device_count} device(s).")
            
            # Delete from normalized table first
            cursor.execute("DELETE FROM sensor_model_parameters WHERE sensor_model_id = %s", (model_id,))
            
            # Delete from main table
            cursor.execute("DELETE FROM sensor_models WHERE id = %s", (model_id,))
            
            conn.commit()
            return cursor.rowcount > 0
            
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
    
    def create_model(self, model: SensorModel) -> int:
        """Create a new sensor model with its parameters"""
        conn = self.connect()
        cursor = conn.cursor()
        
        try:
            # Insert sensor model
            cursor.execute("""
                INSERT INTO sensor_models (name, description, manufacturer, parameters, created_at)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (
                model.name,
                model.description,
                model.manufacturer,
                json.dumps([p.to_dict() for p in model.parameters]),
                datetime.now()
            ))
            
            model_id = cursor.fetchone()[0]
            
            # Also insert into normalized table if you're using it
            for param in model.parameters:
                cursor.execute("""
                    INSERT INTO sensor_model_parameters 
                    (sensor_model_id, parameter_name, parameter_type, unit, mqtt_field_name, min_value, max_value)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    model_id,
                    param.name,
                    param.sensor_type,
                    param.unit,
                    param.mqtt_field,
                    param.min_value,
                    param.max_value
                ))
            
            conn.commit()
            return model_id
            
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
    
    def get_model(self, model_id: int) -> Optional[SensorModel]:
        """Get sensor model by ID"""
        conn = self.connect()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            cursor.execute("""
                SELECT id, name, description, manufacturer, parameters, created_at
                FROM sensor_models
                WHERE id = %s
            """, (model_id,))
            
            row = cursor.fetchone()
            if row:
                return SensorModel(**row)
            return None
            
        finally:
            cursor.close()
    
    def get_all_models(self) -> List[SensorModel]:
        """Get all sensor models"""
        conn = self.connect()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            cursor.execute("""
                SELECT id, name, description, manufacturer, parameters, created_at
                FROM sensor_models
                ORDER BY name
            """)
            
            return [SensorModel(**row) for row in cursor.fetchall()]
            
        finally:
            cursor.close()
    
    def create_device_from_model(self, device_data: Dict, user_id: int) -> int:
        """
        Create a new device and automatically create its sensors based on model
        """
        conn = self.connect()
        cursor = conn.cursor()
        
        try:
            # Get sensor model
            model = self.get_model(device_data['sensor_model_id'])
            if not model:
                raise ValueError(f"Sensor model {device_data['sensor_model_id']} not found")
            
            # Insert device
            cursor.execute("""
                INSERT INTO devices 
                (name, device_id, mqtt_topic, user_id, company_id, sensor_model_id, is_active, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                device_data['name'],
                device_data.get('device_id', device_data['name'].lower().replace(' ', '-')),
                device_data.get('mqtt_topic', f"devices/{device_data['name'].lower().replace(' ', '-')}"),
                user_id,
                device_data['company_id'],
                device_data['sensor_model_id'],
                True,
                datetime.now()
            ))
            
            device_id = cursor.fetchone()[0]
            
            # Create sensors based on model parameters
            for param in model.parameters:
                # Create sensor entry
                cursor.execute("""
                    INSERT INTO sensors 
                    (name, sensor_type, unit, device_id, user_id, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    f"{device_data['name']} - {param.name}",
                    param.sensor_type,
                    param.unit,
                    device_id,
                    user_id,
                    datetime.now()
                ))
                
                sensor_id = cursor.fetchone()[0]
                
                # Also add to parameters table (for dashboard compatibility)
                cursor.execute("""
                    INSERT INTO parameters 
                    (name, sensor_type, unit, device_id, user_id, created_at, parameter_type)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    param.name,
                    param.sensor_type,
                    param.unit,
                    device_id,
                    user_id,
                    datetime.now(),
                    "autogenerated"
                ))
            
            conn.commit()
            return device_id
            
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
    
    def process_mqtt_payload(self, device_id: int, payload: Dict, mqtt_config_id: int):
        """
        Process MQTT payload based on device's sensor model
        """
        conn = self.connect()
        cursor = conn.cursor()
        
        try:
            # Get device with its model
            cursor.execute("""
                SELECT d.id, d.name, sm.parameters, d.user_id
                FROM devices d
                LEFT JOIN sensor_models sm ON d.sensor_model_id = sm.id
                WHERE d.id = %s
            """, (device_id,))
            
            device_row = cursor.fetchone()
            if not device_row:
                raise ValueError(f"Device {device_id} not found")
            
            device_id, device_name, params_json, user_id = device_row
            
            if params_json:
                model_params = json.loads(params_json)
                
                for param in model_params:
                    mqtt_field = param.get('mqtt_field', param['name'].lower())
                    
                    if mqtt_field in payload:
                        # Get sensor ID
                        cursor.execute("""
                            SELECT id FROM sensors 
                            WHERE device_id = %s AND name ILIKE %s
                        """, (device_id, f"%{param['name']}%"))
                        
                        sensor_result = cursor.fetchone()
                        if sensor_result:
                            sensor_id = sensor_result[0]
                            
                            # Insert sensor data
                            cursor.execute("""
                                INSERT INTO sensor_data 
                                (device_id, sensor_id, value, unit, timestamp, user_id, parameter_type)
                                VALUES (%s, %s, %s, %s, %s, %s, %s)
                            """, (
                                device_id,
                                sensor_id,
                                float(payload[mqtt_field]),
                                param['unit'],
                                datetime.now(),
                                user_id,
                                param['sensor_type']
                            ))
            
            # Update device last seen
            cursor.execute("""
                UPDATE devices 
                SET last_seen = %s 
                WHERE id = %s
            """, (datetime.now(), device_id))
            
            conn.commit()
            
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            