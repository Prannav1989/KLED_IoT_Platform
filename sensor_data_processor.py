# sensor_data_processor.py
import json
import logging
import time
import threading
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from flask import current_app
from extensions import db
from sqlalchemy import text


class SensorDataProcessor:
    def __init__(self, app=None, rule_processor=None):
        """Initialize with Flask app and optional rule processor"""
        self.app = app
        self.rule_processor = rule_processor
        self.running = False
        self.processing_thread = None
        self.setup_logging()
        
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize with Flask app"""
        self.app = app
        self.logger.info("✅ SensorDataProcessor initialized")
    
    def setup_logging(self):
        """Setup logging configuration"""
        self.logger = logging.getLogger(__name__)
        
        # Only add handlers if not already configured
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
    
    def execute_query(self, query, params=None, fetch=False):
        """
        Execute a SQL query safely.
        - fetch=True  → SELECT queries
        - fetch=False → INSERT / UPDATE / DELETE
        """
        if self.app is None:
            self.logger.error("❌ Flask app not initialized")
            return None

        try:
            with self.app.app_context():
                self.logger.debug(f"Executing query: {query[:100]}...")

                result = db.session.execute(
                    text(query),
                    params or {}
                )

                if fetch:
                    rows = result.fetchall()
                    db.session.rollback()  # close read transaction cleanly
                    return [tuple(row) for row in rows]

                db.session.commit()
                return True

        except Exception as e:
            self.logger.error(f"❌ Error executing query: {e}")
            self.logger.error(f"Query: {query[:200]}")

            with self.app.app_context():
                db.session.rollback()
            
            if fetch:
                return []
            return False
    
    def execute_insert(self, query, params=None):
        """Execute an insert query"""
        return self.execute_query(query, params, fetch=False)

    def normalize_dev_eui(self, dev_eui: str) -> str:
        """
        Normalize device EUI by converting to uppercase and removing any whitespace
        """
        if not dev_eui:
            return dev_eui
        return str(dev_eui).strip().upper()

    def get_device_info_by_dev_eui(self, dev_eui: str) -> Optional[Dict]:
        """
        Get device information from devices table using dev_eui
        """
        try:
            normalized_dev_eui = self.normalize_dev_eui(dev_eui)
            self.logger.info(f"Looking up device with normalized dev_eui: {normalized_dev_eui}")
            
            query = """
            SELECT id, name, device_id, user_id, company_id, mqtt_config_id
            FROM devices 
            WHERE UPPER(TRIM(device_id)) = :dev_eui AND is_active = TRUE
            LIMIT 1
            """
            
            result = self.execute_query(
                query,
                {'dev_eui': normalized_dev_eui},
                fetch=True
            )
            
            if result:
                row = result[0]
                device_info = {
                    'id': row[0],
                    'name': row[1],
                    'device_id': row[2],
                    'user_id': row[3],
                    'company_id': row[4],
                    'mqtt_config_id': row[5]
                }
                self.logger.info(f"✅ Found device: {device_info['name']} (ID: {device_info['id']})")
                return device_info
            
            self.logger.warning(f"⚠️ No device found for dev_eui: {dev_eui} (normalized: {normalized_dev_eui})")
            return None
                
        except Exception as e:
            self.logger.error(f"❌ Database error getting device info: {e}")
            return None

    def get_parameters_for_device(self, device_id: int, user_id: int) -> List[Dict]:
        """
        Get parameters for a specific device from parameters table
        """
        try:
            # Get parameters for this device
            query = """
            SELECT id, name, sensor_type, unit, device_id, user_id
            FROM parameters 
            WHERE device_id = :device_id
            ORDER BY id
            """
            
            result = self.execute_query(
                query,
                {'device_id': device_id},
                fetch=True
            )

            
            parameters = []
            for row in result:
                param = {
                    'id': row[0],
                    'name': row[1],
                    'sensor_type': row[2],
                    'unit': row[3],
                    'device_id': row[4],
                    'user_id': row[5]
                }
                parameters.append(param)
            
            self.logger.info(f"✅ Found {len(parameters)} parameters for device {device_id}")
            
            # Log the parameters found for debugging
            if parameters:
                self.logger.debug(f"Parameters found: {[p['name'] for p in parameters]}")
            
            return parameters
            
        except Exception as e:
            self.logger.error(f"❌ Database error getting parameters: {e}")
            return []

    def extract_device_info_from_payload(self, payload: str) -> Optional[Dict]:
        """
        Extract device information from MQTT message payload
        """
        try:
            if isinstance(payload, str):
                data = json.loads(payload)
            else:
                data = payload
            
            self.logger.debug(f"Payload keys: {list(data.keys())}")
            
            dev_eui = None
            
            # Check for TTN V3 format
            if 'end_device_ids' in data:
                end_device_ids = data.get('end_device_ids', {})
                dev_eui = end_device_ids.get('dev_eui')
                self.logger.debug(f"TTN format - Extracted dev_eui: {dev_eui}")
            
            # Check for devEUI variants
            elif 'devEUI' in data:
                dev_eui = data.get('devEUI')
                self.logger.debug(f"Simple format - Extracted devEUI: {dev_eui}")
            
            elif 'dev_eui' in data:
                dev_eui = data.get('dev_eui')
                self.logger.debug(f"Simple format - Extracted dev_eui: {dev_eui}")
            
            # Check for device_id as fallback
            elif 'device_id' in data:
                dev_eui = data.get('device_id')
                self.logger.debug(f"Fallback - Using device_id: {dev_eui}")
            
            if dev_eui:
                normalized_dev_eui = self.normalize_dev_eui(dev_eui)
                return {
                    'dev_eui': normalized_dev_eui,
                    'original_dev_eui': dev_eui
                }
            
            self.logger.warning(f"⚠️ No dev_eui found in payload")
            return None
                
        except (json.JSONDecodeError, KeyError, AttributeError) as e:
            self.logger.error(f"❌ Error extracting device info from payload: {e}")
            return None

    def extract_sensor_data_from_payload(self, payload: str, parameters: List[Dict], device_info: Dict) -> List[Dict]:
        """
        Extract sensor data from MQTT payload ONLY for parameters that exist in the parameters table
        """
        try:
            if isinstance(payload, str):
                data = json.loads(payload)
            else:
                data = payload
            
            sensor_data = []
            decoded_payload = {}
            latitude = None
            longitude = None
            timestamp = None
            
            # Determine payload format and extract data
            if 'uplink_normalized' in data and 'normalized_payload' in data['uplink_normalized']:
                decoded_payload = data['uplink_normalized']['normalized_payload']
                self.logger.debug("Using TTN uplink_normalized format")
                
                # Extract location
                locations = data.get('end_device_ids', {}).get('locations', {})
                if locations:
                    user_location = locations.get('user', {})
                    if user_location:
                        latitude = user_location.get('latitude')
                        longitude = user_location.get('longitude')
            
            elif 'uplink_message' in data and 'decoded_payload' in data['uplink_message']:
                decoded_payload = data['uplink_message']['decoded_payload']
                self.logger.debug("Using TTN uplink_message format")
                
                # Extract location
                locations = data.get('end_device_ids', {}).get('locations', {})
                if locations:
                    user_location = locations.get('user', {})
                    if user_location:
                        latitude = user_location.get('latitude')
                        longitude = user_location.get('longitude')
            
            else:
                # For simple format, the data itself is the decoded payload
                decoded_payload = data
                self.logger.debug("Using simple sensor data format")
                
                if 'latitude' in data:
                    latitude = data.get('latitude')
                if 'longitude' in data:
                    longitude = data.get('longitude')
            
            self.logger.debug(f"Decoded payload keys: {list(decoded_payload.keys())}")
            
            # Extract timestamp
            received_at = data.get('received_at') or data.get('timestamp')
            if received_at:
                try:
                    if isinstance(received_at, (int, float)):
                        timestamp = datetime.fromtimestamp(received_at)
                    elif 'Z' in received_at:
                        timestamp = datetime.fromisoformat(received_at.replace('Z', '+00:00'))
                    else:
                        timestamp = datetime.fromisoformat(received_at)
                except ValueError as e:
                    self.logger.warning(f"Error parsing timestamp {received_at}: {e}")
                    timestamp = datetime.utcnow()
            else:
                timestamp = datetime.utcnow()
            
            # Pre-process payload keys to lowercase for case-insensitive matching
            payload_lowercase = {k.lower(): v for k, v in decoded_payload.items()}
            
            # For each parameter from the database, look for matching data
            for param in parameters:
                param_name = param['name']
                sensor_type = param['sensor_type']
                unit = param['unit']
                
                self.logger.debug(f"Looking for parameter: {param_name} (type: {sensor_type})")
                
                value = None
                
                # Try exact case-insensitive match with parameter name first
                if param_name:
                    param_name_lower = param_name.lower()
                    if param_name_lower in payload_lowercase:
                        value = payload_lowercase[param_name_lower]
                        self.logger.info(f"✅ Found {param_name} as '{param_name_lower}': {value}")
                
                # If not found, try case-insensitive match with sensor type
                if value is None and sensor_type:
                    sensor_type_lower = sensor_type.lower()
                    if sensor_type_lower in payload_lowercase:
                        value = payload_lowercase[sensor_type_lower]
                        self.logger.info(f"✅ Found {param_name} by sensor_type '{sensor_type}': {value}")
                
                # If still not found, try common variations for this sensor type
                if value is None:
                    value = self.find_sensor_variations(param_name, sensor_type, payload_lowercase)
                
                if value is not None:
                    try:
                        # Convert to float if possible
                        if isinstance(value, (int, float)):
                            numeric_value = float(value)
                        elif isinstance(value, str):
                            # Try to convert string to float
                            numeric_value = float(value)
                        elif isinstance(value, bool):
                            numeric_value = 1.0 if value else 0.0
                        else:
                            self.logger.warning(f"⚠️ Value type {type(value)} for {param_name} not convertible")
                            continue
                        
                        # Create sensor data entry
                        sensor_data.append({
                            'parameter_id': param['id'],
                            'value': numeric_value,
                            'unit': unit,
                            'timestamp': timestamp,
                            'latitude': latitude,
                            'longitude': longitude,
                            'parameter_type': param_name.lower(),
                            'device_id': device_info['id'],
                            'user_id': device_info['user_id']
                        })
                        self.logger.info(f"✓ Extracted {param_name}: {value} {unit}")
                    except (ValueError, TypeError) as e:
                        self.logger.warning(f"⚠️ Could not convert value '{value}' for {param_name}: {e}")
                else:
                    self.logger.debug(f"✗ No data found for parameter: {param_name}")
            
            self.logger.info(f"✅ Total sensor readings extracted: {len(sensor_data)}")
            return sensor_data
            
        except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
            self.logger.error(f"❌ Error extracting sensor data: {e}")
            return []
    
    def find_sensor_variations(self, param_name: str, sensor_type: str, payload_lowercase: Dict) -> any:
        """Find sensor data using common variations"""
        param_lower = param_name.lower()
        sensor_lower = sensor_type.lower()
        
        # TVOC variations
        if 'tvoc' in param_lower or 'tvoc' in sensor_lower:
            for tvoc_key in ['tvoc', 'volatile_organic_compounds', 'total_voc']:
                if tvoc_key in payload_lowercase:
                    return payload_lowercase[tvoc_key]
        
        # Temperature variations
        elif 'temperature' in param_lower or 'temperature' in sensor_lower:
            for temp_key in ['temperature', 'temp', 'tmp']:
                if temp_key in payload_lowercase:
                    return payload_lowercase[temp_key]
        
        # Humidity variations
        elif 'humidity' in param_lower or 'humidity' in sensor_lower:
            for hum_key in ['humidity', 'relativehumidity', 'rh']:
                if hum_key in payload_lowercase:
                    return payload_lowercase[hum_key]
        
        # CO2 variations
        elif 'co2' in param_lower or 'co2' in sensor_lower:
            for co2_key in ['co2', 'carbon_dioxide']:
                if co2_key in payload_lowercase:
                    return payload_lowercase[co2_key]
        
        # Add more variations as needed...
        
        return None

    def insert_sensor_data(self, sensor_data: List[Dict]):
        """
        Insert extracted sensor data into sensor_data table
        """
        if not sensor_data:
            self.logger.warning("⚠️ No sensor data extracted, skipping storage")
            return True
        
        try:
            inserted_count = 0
            for data in sensor_data:
                query = """
                INSERT INTO sensor_data 
                (device_id, value, unit, timestamp, latitude, longitude, 
                 user_id, parameter_type, parameter_id)
                VALUES (:device_id, :value, :unit, :timestamp, :latitude, :longitude, 
                        :user_id, :parameter_type, :parameter_id)
                """
                
                success = self.execute_insert(query, {
                    'device_id': data['device_id'],
                    'value': data['value'],
                    'unit': data['unit'],
                    'timestamp': data['timestamp'],
                    'latitude': data['latitude'],
                    'longitude': data['longitude'],
                    'user_id': data['user_id'],
                    'parameter_type': data['parameter_type'],
                    'parameter_id': data['parameter_id']
                })
                
                if success:
                    inserted_count += 1
                else:
                    self.logger.warning(f"⚠️ Failed to insert data for parameter {data['parameter_type']}")
            
            self.logger.info(f"✅ Successfully inserted {inserted_count}/{len(sensor_data)} sensor readings")
            return inserted_count > 0
            
        except Exception as e:
            self.logger.error(f"❌ Database error inserting sensor data: {e}")
            return False

    def mark_message_processed(self, message_id: int):
        """
        Mark MQTT message as processed
        """
        try:
            query = "UPDATE mqtt_messages SET processed = TRUE WHERE id = :message_id"
            success = self.execute_insert(query, {'message_id': message_id})
            if success:
                self.logger.debug(f"✅ Marked message {message_id} as processed")
            return success
            
        except Exception as e:
            self.logger.error(f"❌ Error marking message as processed: {e}")
            return False

    def get_unprocessed_mqtt_messages(self) -> List[Tuple]:
        """
        Get all unprocessed MQTT messages
        """
        try:
            query = """
            SELECT id, payload, mqtt_config_id, timestamp 
            FROM mqtt_messages 
            WHERE processed = FALSE OR processed IS NULL
            ORDER BY timestamp ASC
            LIMIT 100  
            """
            
            result = self.execute_query(query, fetch=True)
            
            count = len(result) if isinstance(result, list) else 0
            if count > 0:
                self.logger.info(f"📥 Found {count} unprocessed messages")
            
            return result
            
        except Exception as e:
            self.logger.error(f"❌ Database error getting unprocessed messages: {e}")
            return []

    def process_single_message(self, message_id: int, payload: str, mqtt_config_id: int) -> bool:
        """
        Process a single MQTT message
        - Extract sensor data
        - Queue for real-time rule evaluation
        - Persist sensor data for history
        """
        try:
            self.logger.info(f"=== Processing message {message_id} ===")

            # ---------------------------------------
            # 1️⃣ Extract device info from payload
            # ---------------------------------------
            device_info_from_payload = self.extract_device_info_from_payload(payload)

            if not device_info_from_payload:
                self.logger.warning(f"⚠️ Could not extract device info from message {message_id}")
                self.mark_message_processed(message_id)
                return False

            dev_eui = device_info_from_payload['dev_eui']
            original_dev_eui = device_info_from_payload.get('original_dev_eui', dev_eui)

            self.logger.info(f"Original dev_eui from payload: {original_dev_eui}")
            self.logger.info(f"Normalized dev_eui for lookup: {dev_eui}")

            # ---------------------------------------
            # 2️⃣ Resolve device from DB
            # ---------------------------------------
            device_info = self.get_device_info_by_dev_eui(dev_eui)

            if not device_info:
                self.logger.warning(f"⚠️ No device found for dev_eui: {dev_eui}. Marking as processed.")
                self.mark_message_processed(message_id)
                return False

            # ---------------------------------------
            # 3️⃣ Load parameters for device
            # ---------------------------------------
            parameters = self.get_parameters_for_device(
                device_info['id'],
                device_info['user_id']
            )

            if not parameters:
                self.logger.warning(f"⚠️ No parameters found for device {device_info['id']}")
                self.mark_message_processed(message_id)
                return False

            # ---------------------------------------
            # 4️⃣ Extract sensor values from payload
            # ---------------------------------------
            sensor_data = self.extract_sensor_data_from_payload(
                payload,
                parameters,
                device_info
            )

            if not sensor_data:
                self.logger.warning(f"⚠️ No sensor data extracted from message {message_id}")
                self.mark_message_processed(message_id)
                return False

            # ---------------------------------------
            # 🔥 5️⃣ REAL-TIME RULE EVALUATION QUEUE
            # ---------------------------------------
            rule_processor_used = False
            for data in sensor_data:
                try:
                    # Try to use rule processor if available
                    if self.rule_processor:
                        self.rule_processor.add_to_queue(
                            device_id=data['device_id'],
                            param_name=data['parameter_type'],
                            value=data['value'],
                            timestamp=data['timestamp']
                        )
                        rule_processor_used = True
                        self.logger.debug(
                            f"📤 Queued for rule evaluation: "
                            f"device={data['device_id']} "
                            f"parameter={data['parameter_type']} "
                            f"value={data['value']}"
                        )
                    else:
                        self.logger.warning("⚠️ Rule processor not available - skipping real-time alerts")
                        
                except Exception as rule_error:
                    self.logger.error(
                        f"❌ Rule queueing failed for device {data['device_id']} "
                        f"parameter {data['parameter_type']}: {rule_error}"
                    )

            # ---------------------------------------
            # 6️⃣ Persist sensor data (history)
            # ---------------------------------------
            storage_success = self.insert_sensor_data(sensor_data)

            # ---------------------------------------
            # 7️⃣ Mark MQTT message as processed
            # ---------------------------------------
            processing_success = self.mark_message_processed(message_id)

            if rule_processor_used:
                self.logger.info(f"📊 Rules queued for {len(sensor_data)} readings")
            
            self.logger.info(
                f"✅ Successfully processed message {message_id} "
                f"for device {device_info['name']} "
                f"(Storage: {'OK' if storage_success else 'FAIL'}, "
                f"Processing: {'OK' if processing_success else 'FAIL'})"
            )
            return storage_success and processing_success

        except Exception as e:
            self.logger.error(f"❌ Error processing message {message_id}: {e}")
            return False


    def process_all_unprocessed_messages(self):
        """
        Process all unprocessed MQTT messages in batches
        """
        try:
            unprocessed_messages = self.get_unprocessed_mqtt_messages()
            
            if not unprocessed_messages:
                self.logger.debug("📭 No unprocessed messages found")
                return
            
            processed_count = 0
            failed_count = 0
            
            for message in unprocessed_messages:
                message_id, payload, mqtt_config_id, timestamp = message
                
                self.logger.info(f"🔄 Processing message {message_id} from {timestamp}")
                
                success = self.process_single_message(message_id, payload, mqtt_config_id)
                
                if success:
                    processed_count += 1
                else:
                    failed_count += 1
            
            if processed_count > 0 or failed_count > 0:
                self.logger.info(f"📊 Processing complete. Successfully processed: {processed_count}, Failed: {failed_count}")
                
            return {
                'processed': processed_count,
                'failed': failed_count,
                'total': len(unprocessed_messages)
            }
                
        except Exception as e:
            self.logger.error(f"❌ Error in process_all_unprocessed_messages: {e}")
            return {'processed': 0, 'failed': 0, 'total': 0}

    def start_continuous_processing(self, interval_seconds=10):
        """
        Start continuous processing in a background thread
        """
        if self.running:
            self.logger.warning("⚠️ Processor is already running")
            return
        
        self.running = True
        self.processing_thread = threading.Thread(
            target=self._processing_loop,
            args=(interval_seconds,),
            daemon=True,
            name="SensorDataProcessor"
        )
        self.processing_thread.start()
        self.logger.info(f"🚀 Started continuous processing with {interval_seconds} second interval")

    def stop_continuous_processing(self):
        """
        Stop continuous processing
        """
        self.running = False
        if self.processing_thread:
            self.processing_thread.join(timeout=5)
        self.logger.info("🛑 Stopped continuous processing")

    def _processing_loop(self, interval_seconds):
        """
        Main processing loop that runs continuously
        """
        while self.running:
            try:
                # Process any unprocessed messages
                self.process_all_unprocessed_messages()
                
                # Wait for the specified interval
                time.sleep(interval_seconds)
                
            except Exception as e:
                self.logger.error(f"❌ Error in processing loop: {e}")
                time.sleep(interval_seconds)
    
    def get_processor_stats(self) -> Dict:
        """Get processor statistics"""
        return {
            'running': self.running,
            'thread_alive': self.processing_thread.is_alive() if self.processing_thread else False,
            'has_rule_processor': self.rule_processor is not None
        }


# Global processor instance
sensor_processor = SensorDataProcessor()