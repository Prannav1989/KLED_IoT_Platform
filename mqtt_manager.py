# mqtt_manager.py - Production-ready IoT MQTT Manager
import paho.mqtt.client as mqtt
import json
import logging
import ssl
from flask import current_app
from datetime import datetime, timedelta
import hashlib
import time
from collections import OrderedDict
import threading
import os
import re
from dataclasses import dataclass
from typing import Optional, Dict, Tuple
import pickle
from pathlib import Path
import builtins

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class DeviceRateLimit:
    """Rate limiting configuration for devices"""
    min_interval: float = 0.45  # 450ms minimum between messages
    burst_capacity: int = 3  # Allow bursts of up to 3 messages
    burst_window: float = 2.0  # Within 2 seconds
    
    def should_allow(self, timestamps: list, current_time: float) -> Tuple[bool, str]:
        """Check if message should be allowed based on rate limiting"""
        if not timestamps:
            return True, "ok"
        
        # Remove old timestamps outside burst window
        recent_timestamps = [ts for ts in timestamps if current_time - ts <= self.burst_window]
        
        # Check burst capacity
        if len(recent_timestamps) >= self.burst_capacity:
            return False, f"burst_limit_exceeded ({len(recent_timestamps)} in {self.burst_window}s)"
        
        # Check minimum interval
        time_since_last = current_time - recent_timestamps[-1] if recent_timestamps else float('inf')
        if time_since_last < self.min_interval:
            return False, f"interval_too_short ({time_since_last:.3f}s < {self.min_interval}s)"
        
        return True, "ok"


class MetricsCollector:
    """Collect and report metrics for monitoring"""
    def __init__(self):
        self.messages_received = 0
        self.messages_processed = 0
        self.duplicates_blocked = 0
        self.rate_limited = 0
        self.errors = 0
        self.start_time = time.time()
        self.lock = threading.Lock()
    
    def increment(self, metric: str):
        """Increment a metric counter"""
        with self.lock:
            if metric == "received":
                self.messages_received += 1
            elif metric == "processed":
                self.messages_processed += 1
            elif metric == "duplicate":
                self.duplicates_blocked += 1
            elif metric == "rate_limited":
                self.rate_limited += 1
            elif metric == "error":
                self.errors += 1
    
    def get_stats(self) -> Dict:
        """Get current statistics"""
        with self.lock:
            uptime = time.time() - self.start_time
            total_blocked = self.duplicates_blocked + self.rate_limited
            processed_rate = self.messages_processed / uptime if uptime > 0 else 0
            
            return {
                "uptime_hours": uptime / 3600,
                "messages_received": self.messages_received,
                "messages_processed": self.messages_processed,
                "duplicates_blocked": self.duplicates_blocked,
                "rate_limited": self.rate_limited,
                "errors": self.errors,
                "processing_rate_per_second": processed_rate,
                "blocked_percentage": (total_blocked / self.messages_received * 100) if self.messages_received > 0 else 0
            }
    
    def log_summary(self):
        """Log summary statistics"""
        stats = self.get_stats()
        logger.info(
            f"📊 METRICS: Processed {stats['messages_processed']} messages "
            f"({stats['processing_rate_per_second']:.1f}/s), "
            f"Blocked {stats['duplicates_blocked']} duplicates + {stats['rate_limited']} rate limited "
            f"({stats['blocked_percentage']:.1f}%)"
        )


class MessageDeduplicator:
    """Advanced message deduplication with multiple strategies"""
    
    def __init__(self, persistence_path: Optional[str] = None):
        # Level 1: Message hash cache (short-term)
        self.message_hashes = OrderedDict()  # hash: timestamp
        self.hash_window = 10  # seconds
        
        # Level 2: Device rate limiting
        self.device_timestamps = {}  # device_eui: list of timestamps
        self.rate_limit = DeviceRateLimit()
        
        # Level 3: Payload fingerprint (for similar messages)
        self.payload_fingerprints = OrderedDict()  # fingerprint: timestamp
        self.fingerprint_window = 5  # seconds
        
        # Level 4: Sequence number tracking
        self.device_sequences = {}  # device_eui: last_sequence
        
        # Persistence for recovery
        self.persistence_path = persistence_path
        self.persistence_interval = 300  # Save every 5 minutes
        self.last_persist = time.time()
        
        self.lock = threading.RLock()
        self.load_state()
    
    def create_fingerprint(self, payload: str) -> str:
        """Create fingerprint by removing variable fields (timestamps, counters)"""
        try:
            data = json.loads(payload)
            # Remove fields that change with each message
            volatile_fields = ['timestamp', 'time', 'counter', 'seq', 'sequence', 'msg_id']
            for field in volatile_fields:
                if field in data:
                    del data[field]
            
            # Also remove from nested structures
            def clean_dict(obj):
                if isinstance(obj, dict):
                    return {k: clean_dict(v) for k, v in obj.items() if k not in volatile_fields}
                elif isinstance(obj, list):
                    return [clean_dict(item) for item in obj]
                else:
                    return obj
            
            cleaned = clean_dict(data)
            return hashlib.md5(json.dumps(cleaned, sort_keys=True).encode()).hexdigest()
        except:
            # Fallback to simple hash
            return hashlib.md5(payload.encode()).hexdigest()
    
    def should_process(self, device_eui: Optional[str], payload: str, 
                      seq_number: Optional[int] = None) -> Tuple[bool, str, Dict]:
        """
        Multi-level deduplication check
        Returns: (should_process, reason, details)
        """
        current_time = time.time()
        details = {}
        
        with self.lock:
            # === Level 1: Message hash ===
            msg_hash = hashlib.md5(payload.encode()).hexdigest()
            if msg_hash in self.message_hashes:
                age = current_time - self.message_hashes[msg_hash]
                if age < self.hash_window:
                    return False, "duplicate_message_hash", {"hash": msg_hash[:8], "age": age}
            
            # === Level 2: Device rate limiting ===
            if device_eui:
                device_eui = device_eui.upper().strip()
                
                # Get or create timestamp list for this device
                timestamps = self.device_timestamps.get(device_eui, [])
                
                # Check rate limiting
                allowed, reason = self.rate_limit.should_allow(timestamps, current_time)
                if not allowed:
                    return False, f"rate_limit_{reason}", {"device": device_eui[:8]}
                
                # Update timestamps
                timestamps.append(current_time)
                # Keep only recent timestamps
                self.device_timestamps[device_eui] = [
                    ts for ts in timestamps 
                    if current_time - ts <= self.rate_limit.burst_window * 2
                ]
            
            # === Level 3: Sequence number ===
            if device_eui and seq_number is not None:
                last_seq = self.device_sequences.get(device_eui)
                if last_seq is not None and seq_number <= last_seq:
                    return False, "old_sequence_number", {
                        "device": device_eui[:8],
                        "received": seq_number,
                        "last": last_seq
                    }
                self.device_sequences[device_eui] = seq_number
            
            # === Level 4: Payload fingerprint ===
            fingerprint = self.create_fingerprint(payload)
            if fingerprint in self.payload_fingerprints:
                age = current_time - self.payload_fingerprints[fingerprint]
                if age < self.fingerprint_window:
                    return False, "similar_payload_recently", {
                        "fingerprint": fingerprint[:8],
                        "age": age
                    }
            
            # === All checks passed - store tracking data ===
            self.message_hashes[msg_hash] = current_time
            self.payload_fingerprints[fingerprint] = current_time
            
            # Cleanup old entries
            self._cleanup_old_entries(current_time)
            
            # Persist state periodically
            if current_time - self.last_persist > self.persistence_interval:
                self.save_state()
                self.last_persist = current_time
            
            return True, "ok", {"msg_hash": msg_hash[:8], "fingerprint": fingerprint[:8]}
    
    def _cleanup_old_entries(self, current_time: float):
        """Cleanup old entries to prevent memory leaks"""
        # Message hashes
        old_hashes = [
            h for h, ts in self.message_hashes.items()
            if current_time - ts > self.hash_window
        ]
        for h in old_hashes:
            del self.message_hashes[h]
        
        # Payload fingerprints
        old_fingerprints = [
            f for f, ts in self.payload_fingerprints.items()
            if current_time - ts > self.fingerprint_window
        ]
        for f in old_fingerprints:
            del self.payload_fingerprints[f]
        
        # Device timestamps (keep 2x burst window)
        for device in list(self.device_timestamps.keys()):
            self.device_timestamps[device] = [
                ts for ts in self.device_timestamps[device]
                if current_time - ts <= self.rate_limit.burst_window * 2
            ]
            if not self.device_timestamps[device]:
                del self.device_timestamps[device]
                if device in self.device_sequences:
                    del self.device_sequences[device]
    
    def save_state(self):
        """Save state to disk for recovery"""
        if not self.persistence_path:
            return
        
        try:
            with self.lock:
                state = {
                    'device_timestamps': self.device_timestamps,
                    'device_sequences': self.device_sequences,
                    'saved_at': time.time()
                }
                
                path = Path(self.persistence_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                
                import builtins
                with builtins.open(path, 'wb') as f:
                    pickle.dump(state, f)
                
                logger.debug(f"💾 Saved deduplication state with {len(self.device_timestamps)} devices")
        except Exception as e:
            logger.error(f"Failed to save deduplication state: {e}")
    
    def load_state(self):
        """Load state from disk"""
        if not self.persistence_path or not os.path.exists(self.persistence_path):
            return
        
        try:
            with builtins.open(self.persistence_path, 'rb') as f:
                state = pickle.load(f)
            
            # Only load if saved within last 24 hours
            if time.time() - state.get('saved_at', 0) < 86400:
                with self.lock:
                    self.device_timestamps = state.get('device_timestamps', {})
                    self.device_sequences = state.get('device_sequences', {})
                
                logger.info(f"📂 Loaded deduplication state with {len(self.device_timestamps)} devices")
        except Exception as e:
            logger.error(f"Failed to load deduplication state: {e}")


class MQTTClientManager:
    """Production-ready MQTT Client Manager for IoT"""
    
    def __init__(self, data_dir: str = "./data"):
        self.app = None
        self.socketio = None
        self.clients = {}
        self._process_id = os.getpid()
        self._connection_lock = threading.RLock()
        
        # Initialize components
        self.metrics = MetricsCollector()
        self.deduplicator = MessageDeduplicator(
            persistence_path=os.path.join(data_dir, "deduplication_state.pkl")
        )
        
        # Configuration
        self.max_reconnect_delay = 300  # 5 minutes
        self.keepalive = 60
        self.connect_timeout = 10
        
        # Statistics logging
        self.stats_interval = 60  # Log stats every 60 seconds
        self.last_stats_log = time.time()
        
        logger.info(f"🚀 Production MQTT Manager initialized in PID: {self._process_id}")
    
    def init_app(self, app, socketio=None):
        """Initialize with Flask app"""
        self.app = app
        self.socketio = socketio
        
        # Create data directory
        os.makedirs("./data", exist_ok=True)
        
        # Connect to brokers
        if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
            with self.app.app_context():
                self.connect_to_all_configs()
        else:
            logger.info("Skipping MQTT connection in reloader subprocess")
    
    def connect_to_all_configs(self):
        """Connect to all MQTT configurations from database"""
        try:
            logger.info(f"🔌 Connecting to all MQTT configs in PID: {self._process_id}")
            
            from models import MQTTConfig
            configs = MQTTConfig.query.filter(MQTTConfig.broker_url.isnot(None)).all()
            
            if not configs:
                logger.warning("No MQTT configurations found")
                return
            
            logger.info(f"Found {len(configs)} MQTT configurations")
            
            successful = 0
            for config in configs:
                if self.connect_to_config(config):
                    successful += 1
            
            logger.info(f"✅ Successfully connected to {successful}/{len(configs)} brokers")
            
        except Exception as e:
            logger.error(f"Error connecting to MQTT configs: {e}")
    
    def connect_to_config(self, config) -> bool:
        """Connect to a specific MQTT configuration"""
        with self._connection_lock:
            config_id = config.id
            
            # Check for existing connection
            if config_id in self.clients:
                client_data = self.clients[config_id]
                if client_data.get('connected', False):
                    logger.debug(f"Already connected to {config.name}")
                    return True
            
            try:
                logger.info(f"🔄 Creating connection to {config.name} ({config.broker_url})")
                
                # Generate unique client ID
                client_id = self._generate_client_id(config_id)
                
                # Create client with MQTT v3.1.1 (required for TTN)
                client = mqtt.Client(
                    client_id=client_id,
                    protocol=mqtt.MQTTv311,
                    clean_session=True
                )
                
                # Configure authentication
                if not self._configure_auth(client, config):
                    return False
                
                # Configure TLS
                self._configure_tls(client, config)
                
                # Configure callbacks
                self._configure_callbacks(client, config)
                
                # Configure reconnection
                client.reconnect_delay_set(
                    min_delay=1,
                    max_delay=self.max_reconnect_delay
                )
                
                # Determine port
                port = self._determine_port(config)
                
                # Connect with timeout
                logger.info(f"Connecting to {config.broker_url}:{port} (timeout: {self.connect_timeout}s)")
                client.connect(
                    config.broker_url,
                    port,
                    keepalive=self.keepalive
                )
                
                # Start network loop
                client.loop_start()
                
                # Store client reference
                self.clients[config_id] = {
                    'client': client,
                    'config': config,
                    'connected': False,
                    'process_id': self._process_id,
                    'last_activity': time.time(),
                    'subscription_count': 0
                }
                
                logger.info(f"⏳ Connection initiated to {config.name}")
                return True
                
            except Exception as e:
                logger.error(f"Failed to connect to {config.broker_url}:{config.port} - {e}")
                if config_id in self.clients:
                    self.clients[config_id]['connected'] = False
                return False
    
    def _generate_client_id(self, config_id: int) -> str:
        """Generate unique client ID"""
        timestamp = int(time.time() * 1000)
        return f"iot_mqtt_{config_id}_{self._process_id}_{timestamp}"
    
    def _configure_auth(self, client: mqtt.Client, config) -> bool:
        """Configure authentication"""
        if not config.username:
            return True
        
        if not config.password:
            logger.error(f"No password provided for {config.username}")
            return False
        
        client.username_pw_set(config.username, config.password)
        logger.debug(f"🔐 Using authentication for {config.username}")
        return True
    
    def _configure_tls(self, client: mqtt.Client, config):
        """Configure TLS/SSL"""
        if config.ssl_enabled or 'thethings.network' in config.broker_url:
            # For TTN and other TLS brokers
            client.tls_set(cert_reqs=ssl.CERT_NONE)
            client.tls_insecure_set(True)  # Accept self-signed certificates
            logger.debug(f"🔒 TLS enabled for {config.broker_url}")
    
    def _configure_callbacks(self, client: mqtt.Client, config):
        """Configure MQTT callbacks"""
        client.on_connect = lambda client, userdata, flags, rc: self.on_connect(client, userdata, flags, rc, config)
        client.on_message = self.on_message
        client.on_disconnect = lambda client, userdata, rc: self.on_disconnect(client, userdata, rc, config)
        client.on_log = self.on_log
    
    def _determine_port(self, config) -> int:
        """Determine the correct port for the broker"""
        if 'thethings.network' in config.broker_url:
            # TTN requires port 8883 for TLS
            return 8883 if config.port in [1883, None] else config.port
        return config.port or 1883
    
    def on_connect(self, client, userdata, flags, rc, config):
        """Callback when connected to MQTT broker"""
        error_messages = {
            0: "Success",
            1: "Incorrect protocol version",
            2: "Invalid client identifier",
            3: "Server unavailable",
            4: "Bad username or password",
            5: "Not authorized"
        }
        
        config_id = config.id
        
        if rc == 0:
            logger.info(f"✅ Connected to {config.name}")
            
            # Update connection status
            if config_id in self.clients:
                self.clients[config_id]['connected'] = True
                self.clients[config_id]['last_activity'] = time.time()
            
            # Subscribe to topics
            self._subscribe_to_device_topics(client, config_id)
            
        else:
            error_msg = error_messages.get(rc, f"Unknown error {rc}")
            logger.error(f"❌ Connection failed to {config.name}: {error_msg}")
            
            if config_id in self.clients:
                self.clients[config_id]['connected'] = False
            
            # Specific troubleshooting
            self._handle_connection_error(rc, config)
    
    def _subscribe_to_device_topics(self, client: mqtt.Client, config_id: int):
        """Subscribe to topics for all devices of this broker"""
        try:
            with self.app.app_context():
                from models import Device
                devices = Device.query.filter_by(
                    mqtt_config_id=config_id,
                    is_active=True
                ).all()
                
                subscribed = 0
                for device in devices:
                    if device.mqtt_topic:
                        topic = self._format_topic_for_subscription(device.mqtt_topic, config_id)
                        
                        # Subscribe with QoS 0 (at most once) to prevent duplicates
                        result = client.subscribe(topic, qos=0)
                        
                        if result[0] == mqtt.MQTT_ERR_SUCCESS:
                            subscribed += 1
                            logger.debug(f"📡 Subscribed to: {topic}")
                        else:
                            logger.warning(f"Failed to subscribe to {topic}")
                
                # Update subscription count
                if config_id in self.clients:
                    self.clients[config_id]['subscription_count'] = subscribed
                
                logger.info(f"Subscribed to {subscribed} topics for config {config_id}")
                
        except Exception as e:
            logger.error(f"Error subscribing to topics: {e}")
    
    def _format_topic_for_subscription(self, base_topic: str, config_id: int) -> str:
        """Format topic for subscription with wildcards if needed"""
        config = self.clients.get(config_id, {}).get('config')
        
        if config and 'thethings.network' in config.broker_url:
            # TTN topics need proper formatting
            if not base_topic.endswith(('#', '+')) and '/devices/' in base_topic:
                return f"{base_topic}/#"
        
        return base_topic
    
    def _handle_connection_error(self, rc: int, config):
        """Handle specific connection errors"""
        if rc in [4, 5] and 'thethings.network' in config.broker_url:
            logger.error("🔍 TTN Authentication failed. Check:")
            logger.error("- Username format: application-name@ttn")
            logger.error("- API Key has MQTT permissions")
            logger.error("- Application exists in TTN Console")
    
    def on_message(self, client, userdata, msg):
        """Main message processing callback with deduplication"""
        self.metrics.increment("received")
        current_time = time.time()
        
        try:
            # Periodic stats logging
            if current_time - self.last_stats_log > self.stats_interval:
                self.metrics.log_summary()
                self.last_stats_log = current_time
            
            # Find which config this client belongs to
            config, config_id = self._get_config_for_client(client)
            if not config:
                logger.error("Could not find config for MQTT client")
                return
            
            # Decode payload
            payload = msg.payload.decode('utf-8', errors='ignore')
            topic = msg.topic
            
            # Extract device information
            device_info = self._extract_device_info(payload, topic, config_id)
            device_eui = device_info.get('device_eui')
            seq_number = device_info.get('seq_number')
            
            # Apply deduplication and rate limiting
            should_process, reason, details = self.deduplicator.should_process(
                device_eui, payload, seq_number
            )
            
            if not should_process:
                if "duplicate" in reason:
                    self.metrics.increment("duplicate")
                elif "rate" in reason:
                    self.metrics.increment("rate_limited")
                
                logger.debug(f"⏭️ Skipped: {reason} {details}")
                return
            
            # Update activity timestamp
            if config_id in self.clients:
                self.clients[config_id]['last_activity'] = current_time
            
            # Log received message
            device_log = f"device {device_eui[:8]}..." if device_eui else "unknown device"
            logger.info(f"📥 Processing from {device_log} on {topic[:50]}...")
            
            # Store raw message in database
            with self.app.app_context():
                self._store_raw_message(topic, payload, config_id, device_eui)
            
            # Emit WebSocket event for real-time updates
            self._emit_websocket_event(topic, payload, config, config_id, device_eui)
            
            self.metrics.increment("processed")
            
        except Exception as e:
            self.metrics.increment("error")
            logger.error(f"Error processing MQTT message: {e}", exc_info=True)
    
    def _get_config_for_client(self, client: mqtt.Client) -> Tuple[Optional[dict], Optional[int]]:
        """Find configuration for a MQTT client"""
        for config_id, client_data in self.clients.items():
            if client_data['client'] is client:
                return client_data['config'], config_id
        return None, None
    
    def _extract_device_info(self, payload: str, topic: str, config_id: int) -> Dict:
        """Extract device EUI and sequence number from payload"""
        device_eui = None
        seq_number = None
        
        try:
            data = json.loads(payload)
            
            # Try common EUI field names
            eui_fields = ['devEUI', 'device_eui', 'eui', 'dev_eui', 'device_id']
            for field in eui_fields:
                if field in data:
                    device_eui = str(data[field]).upper().strip()
                    break
            
            # Try TTN v3 format
            if not device_eui and 'end_device_ids' in data:
                device_eui = data['end_device_ids'].get('device_id', '').upper().strip()
            
            # Extract sequence number if available
            seq_fields = ['seq', 'sequence', 'counter', 'fcnt', 'frm_payload']
            for field in seq_fields:
                if field in data:
                    try:
                        seq_number = int(data[field])
                        break
                    except (ValueError, TypeError):
                        pass
            
        except json.JSONDecodeError:
            # Not JSON, try to extract from topic
            if '/devices/' in topic:
                parts = topic.split('/')
                if len(parts) >= 4:
                    device_eui = parts[3].upper()
        
        return {
            'device_eui': device_eui,
            'seq_number': seq_number,
            'payload_type': 'json' if device_eui else 'raw'
        }
    
    def _store_raw_message(self, topic: str, payload: str, config_id: int, device_eui: Optional[str]):
        """Store raw MQTT message in database"""
        try:
            from models import Device, MQTTMessage
            from extensions import db
            
            # Store the raw message
            mqtt_message = MQTTMessage(
                topic=topic,
                payload=payload,
                mqtt_config_id=config_id,
                timestamp=datetime.now()
            )
            db.session.add(mqtt_message)
            
            # Find and update device last_seen using device_id column
            if device_eui:
                # CORRECT: Use device_id column which contains the device EUI
                device = Device.query.filter(
                    Device.device_id.ilike(device_eui),  # ← FIXED: Use device_id column
                    Device.mqtt_config_id == config_id,
                    Device.is_active == True
                ).first()
                
                if device:
                    device.last_seen = datetime.now()
                    logger.debug(f"🔄 Updated last_seen for {device.name} (EUI: {device_eui[:8]}...)")
                else:
                    logger.warning(f"⚠️ Device with EUI {device_eui[:8]}... not found")
            
            db.session.commit()
            logger.debug(f"💾 Stored raw message ({len(payload)} bytes)")
            
        except Exception as e:
            logger.error(f"Error storing raw message: {e}")
            db.session.rollback()
        
    def _emit_websocket_event(self, topic: str, payload: str, config, config_id: int, 
                            device_eui: Optional[str]):
        """Emit WebSocket event for real-time updates"""
        if not self.socketio:
            return
        
        try:
            # Prepare minimal event data
            event_data = {
                'topic': topic,
                'broker': config.name,
                'config_id': config_id,
                'device_eui': device_eui[:8] if device_eui else None,
                'timestamp': datetime.now().isoformat(),
                'payload_length': len(payload),
                'message_type': 'mqtt_message'
            }
            
            # Only send first 200 chars of payload to avoid overhead
            if len(payload) > 200:
                event_data['payload_preview'] = payload[:200] + "..."
            
            self.socketio.emit('mqtt_message', event_data)
            
        except Exception as e:
            logger.error(f"Error emitting WebSocket event: {e}")
    
    def on_disconnect(self, client, userdata, rc, config):
        """Callback when disconnected from MQTT broker"""
        config_id = config.id
        
        if rc == 0:
            logger.info(f"📴 Disconnected normally from {config.name}")
        else:
            logger.warning(f"⚠️ Unexpected disconnection from {config.name} (code: {rc})")
        
        if config_id in self.clients:
            self.clients[config_id]['connected'] = False
            self.clients[config_id]['last_activity'] = time.time()
    
    def on_log(self, client, userdata, level, buf):
        """MQTT logging callback"""
        if level == mqtt.MQTT_LOG_ERR:
            logger.error(f"MQTT Error: {buf}")
        elif level == mqtt.MQTT_LOG_WARNING:
            logger.warning(f"MQTT Warning: {buf}")
        elif level == mqtt.MQTT_LOG_DEBUG:
            logger.debug(f"MQTT Debug: {buf}")
    
    # Public API methods
    def publish(self, config_id: int, topic: str, message, qos: int = 0, retain: bool = False) -> bool:
        """Publish message to a specific MQTT broker"""
        try:
            if config_id in self.clients and self.clients[config_id]['connected']:
                client = self.clients[config_id]['client']
                
                if isinstance(message, dict):
                    message = json.dumps(message)
                
                result = client.publish(topic, message, qos=qos, retain=retain)
                
                if result.rc == mqtt.MQTT_ERR_SUCCESS:
                    logger.info(f"📤 Published to {topic} (qos={qos})")
                    return True
                else:
                    logger.error(f"Failed to publish to {topic}: {result.rc}")
                    return False
            else:
                logger.error(f"Not connected to config {config_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error publishing message: {e}")
            return False
    
    def get_connection_status(self, config_id: int) -> Optional[Dict]:
        """Get connection status for a specific config"""
        if config_id in self.clients:
            client_data = self.clients[config_id]
            return {
                'connected': client_data['connected'],
                'config_name': client_data['config'].name,
                'process_id': client_data['process_id'],
                'subscription_count': client_data.get('subscription_count', 0),
                'last_activity': client_data.get('last_activity', 0),
                'broker_url': client_data['config'].broker_url
            }
        return None
    
    def get_all_connections(self) -> Dict:
        """Get status of all connections"""
        return {
            config_id: self.get_connection_status(config_id)
            for config_id in self.clients.keys()
        }
    
    def get_metrics(self) -> Dict:
        """Get current metrics"""
        return self.metrics.get_stats()
    
    def disconnect_all(self):
        """Disconnect all MQTT clients gracefully"""
        logger.info("🛑 Disconnecting all MQTT clients...")
        
        for config_id, client_data in self.clients.items():
            try:
                client = client_data['client']
                client.loop_stop()
                client.disconnect()
                logger.info(f"Disconnected from {client_data['config'].name}")
            except Exception as e:
                logger.error(f"Error disconnecting from {client_data['config'].name}: {e}")
        
        # Save deduplication state
        self.deduplicator.save_state()
        
        # Clear clients dict
        self.clients.clear()
        logger.info("All MQTT clients disconnected")
    



# Global singleton instance
mqtt_manager = MQTTClientManager()