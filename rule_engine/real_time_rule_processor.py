# real_time_rule_processor.py
import json
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from flask import current_app
from sqlalchemy import text
from extensions import socketio


class RealTimeRuleProcessor:
    def __init__(self, app=None, db=None):
        """Initialize with Flask app and database"""
        self.app = app
        self.db = db
        self.logger = logging.getLogger(__name__)
        
        # Threading setup
        self.rules_cache = {}  # Cache for faster access
        self.rule_check_queue = []  # Queue for immediate processing
        self.queue_lock = threading.Lock()
        self.processing_active = False
        self.rule_check_thread = None
        
        # Initialize if app is provided
        if app and db:
            self.init_app(app, db)
    
    def init_app(self, app, db):
        """Initialize with app context"""
        self.app = app
        self.db = db
        self.logger.info("✅ RealTimeRuleProcessor initialized")
    
    def execute_query(self, query: str, params: Dict = None, fetch: bool = True) -> Any:
        """Execute SQL query safely"""
        if params is None:
            params = {}
        
        try:
            with self.app.app_context():
                result = self.db.session.execute(text(query), params)
                if fetch:
                    rows = result.fetchall()
                    return rows if rows else []
                else:
                    self.db.session.commit()
                    return True
        except Exception as e:
            self.logger.error(f"❌ Query execution error: {e}")
            self.logger.error(f"Query: {query[:200]}...")
            if not fetch:
                self.db.session.rollback()
            return [] if fetch else False
    
    def load_all_rules(self):
        """Load all enabled rules into memory cache - ADAPTED FOR YOUR SCHEMA"""
        try:
            query = """
            SELECT id, name, metric, operator, threshold, action, action_types,
                   device_id, parameter_type, unit, severity, cooldown_seconds,
                   company_id, enabled, last_triggered
            FROM alert_rule 
            WHERE enabled = TRUE
            """
            
            rules = self.execute_query(query)
            
            self.rules_cache.clear()
            for rule in rules:
                rule_dict = {
                    'id': rule[0],
                    'name': rule[1],
                    'metric': rule[2] if rule[2] else rule[8],
                    'operator': rule[3],
                    'threshold': float(rule[4]) if rule[4] is not None else 0.0,
                    'action': rule[5],
                    'action_types': rule[6],
                    'device_id': rule[7],
                    'parameter_type': rule[8] if rule[8] else rule[2],
                    'unit': rule[9],
                    'severity': rule[10],
                    'cooldown_seconds': rule[11] or 300,
                    'company_id': rule[12],
                    'enabled': rule[13],
                    'last_triggered': rule[14]
                }
                
                # Create cache key using metric or parameter_type
                metric_key = rule_dict['metric'].lower() if rule_dict['metric'] else rule_dict['parameter_type'].lower()
                cache_key = (rule_dict['device_id'], metric_key)
                
                if cache_key not in self.rules_cache:
                    self.rules_cache[cache_key] = []
                self.rules_cache[cache_key].append(rule_dict)
            
            self.logger.info(f"✅ Loaded {len(rules)} enabled rules into cache")
                
        except Exception as e:
            self.logger.error(f"❌ Error loading rules: {e}")
    
    def add_to_queue(self, device_id: int, param_name: str, value: float, timestamp: datetime):
        """Add rule check to queue for processing"""
        with self.queue_lock:
            self.rule_check_queue.append({
                'device_id': device_id,
                'param_name': param_name,
                'value': value,
                'timestamp': timestamp
            })
    
    def process_queue(self):
        """Process all items in the rule check queue"""
        with self.queue_lock:
            items = list(self.rule_check_queue)
            self.rule_check_queue.clear()
        
        for item in items:
            self.check_rules_for_parameter(
                device_id=item['device_id'],
                param_name=item['param_name'],
                value=item['value'],
                timestamp=item['timestamp']
            )
    
    def check_rules_for_parameter(self, device_id: int, param_name: str, value: float, timestamp: datetime):
        """Check ALL rules for this parameter"""
        try:
            # Normalize parameter name for lookup
            param_name_lower = param_name.lower()
            
            # Check for rules for this specific device
            specific_key = (device_id, param_name_lower)
            
            # Also check for rules that apply to all devices (device_id is NULL)
            all_devices_key = (None, param_name_lower)
            
            triggered_rules = []
            
            # Check specific device rules
            if specific_key in self.rules_cache:
                for rule in self.rules_cache[specific_key]:
                    if self.should_trigger_rule(rule, value):
                        triggered_rules.append(self.trigger_rule(rule, value, timestamp))
            
            # Check all-device rules
            if all_devices_key in self.rules_cache:
                for rule in self.rules_cache[all_devices_key]:
                    if self.should_trigger_rule(rule, value):
                        triggered_rules.append(self.trigger_rule(rule, value, timestamp))
            
            # Log triggered rules
            successful_triggers = [name for name, success in triggered_rules if success]
            if successful_triggers:
                self.logger.info(f"📢 Triggered rules: {', '.join(successful_triggers)}")
                
        except Exception as e:
            self.logger.error(f"❌ Error checking rules: {e}")
    
    def should_trigger_rule(self, rule: Dict, value: float) -> bool:
        """Check if rule should trigger"""
        # Check cooldown
        if self.is_in_cooldown(rule):
            return False
        
        # Check condition
        if not self.evaluate_condition(value, rule['operator'], rule['threshold']):
            return False
        
        return True
    
    def trigger_rule(self, rule: Dict, value: float, timestamp: datetime) -> tuple:
        """Trigger a rule and return (rule_name, success)"""
        try:
            self.logger.warning(
                f"🚨 RULE TRIGGERED: {rule['name']} - {rule['metric']}={value} {rule['unit']}"
            )

            # --------------------------------------------------
            # 1️⃣ Create alert event
            # --------------------------------------------------
            event_id = self.create_alert_event(rule, value, timestamp)
            if not event_id:
                return (rule['name'], False)

            # --------------------------------------------------
            # 2️⃣ Execute actions (DB logging etc.)
            # --------------------------------------------------
            self.execute_rule_actions(rule, event_id, value)

            # --------------------------------------------------
            # 3️⃣ Resolve device name safely
            # --------------------------------------------------
            device_name = "Unknown Device"
            if rule.get("device_id"):
                result = self.execute_query(
                    "SELECT name FROM devices WHERE id = :device_id",
                    {"device_id": rule["device_id"]}
                )
                if result:
                    device_name = result[0][0]

            # --------------------------------------------------
            # 4️⃣ Resolve active users for company
            # --------------------------------------------------
            users = self.execute_query(
                """
                SELECT id FROM users
                WHERE company_id = :company_id AND active_status = TRUE
                """,
                {"company_id": rule["company_id"]}
            )
            user_ids = [u[0] for u in users] if users else []

            # --------------------------------------------------
            # 5️⃣ REAL-TIME SOCKET EMIT
            # --------------------------------------------------
            payload = {
                "title": f"🚨 Alert: {rule['name']}",
                "message": f"{device_name} - {rule['metric']}: {value} {rule['unit']}",
                "severity": rule.get("severity", "warning"),
                "rule_id": rule["id"],
                "event_id": event_id,
                "timestamp": timestamp.isoformat(),
                "audio": {
                    "sound": "beep",  # CHANGED FROM "alert" TO "beep" TO MATCH
                    "volume": 0.8,
                    "loop": False
                },
                # Add these fields for compatibility
                "device_id": rule["device_id"],
                "parameter": rule["parameter_type"],
                "value": value,
                "unit": rule["unit"],
                "device_name": device_name
            }

            for user_id in user_ids:
                socketio.emit(
                    "alert_triggered",
                    payload,
                    room=f"alerts_user_{user_id}",
                    namespace='/'  # ADD NAMESPACE
                )
                self.logger.info(
                    f"🔔 Socket alert emitted to alerts_user_{user_id}"
                )

            # --------------------------------------------------
            # 6️⃣ Update last triggered time
            # --------------------------------------------------
            self.update_rule_last_triggered(rule['id'])

            return (rule['name'], True)

        except Exception as e:
            self.logger.exception(
                f"❌ Error triggering rule {rule.get('name', 'UNKNOWN')}"
            )
            return (rule.get('name', 'UNKNOWN'), False)


    
    def is_in_cooldown(self, rule: Dict) -> bool:
        """Check if rule is in cooldown period"""
        if not rule.get('last_triggered') or rule.get('cooldown_seconds', 300) <= 0:
            return False
        
        try:
            last_triggered = rule['last_triggered']
            if isinstance(last_triggered, str):
                last_triggered = datetime.fromisoformat(
                    last_triggered.replace('Z', '+00:00')
                )
            
            cooldown_end = last_triggered + timedelta(
                seconds=rule['cooldown_seconds']
            )
            return datetime.utcnow() < cooldown_end
            
        except Exception as e:
            self.logger.error(f"❌ Error checking cooldown: {e}")
            return False
    
    def evaluate_condition(self, value: float, operator: str, threshold: float) -> bool:
        """Evaluate rule condition"""
        try:
            if operator == ">":
                return value > threshold
            elif operator == "<":
                return value < threshold
            elif operator == ">=":
                return value >= threshold
            elif operator == "<=":
                return value <= threshold
            elif operator == "==":
                return abs(value - threshold) < 0.0001
            elif operator == "!=":
                return abs(value - threshold) >= 0.0001
            else:
                self.logger.error(f"❌ Unknown operator: {operator}")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Error evaluating condition: {e}")
            return False
    
    def create_alert_event(self, rule: Dict, value: float, timestamp: datetime) -> Optional[int]:
        """Create alert event in database (SQLite-safe version)"""
        try:
            with self.app.app_context():
                query = """
                INSERT INTO alert_event 
                (rule_id, device_id, parameter_type, actual_value, threshold, 
                triggered_at, status, source)
                VALUES (:rule_id, :device_id, :parameter_type, :actual_value, :threshold,
                        :triggered_at, :status, :source)
                """

                params = {
                    'rule_id': rule['id'],
                    'device_id': rule['device_id'],
                    'parameter_type': rule['parameter_type'],
                    'actual_value': value,
                    'threshold': rule['threshold'],
                    'triggered_at': timestamp,
                    'status': 'triggered',
                    'source': 'realtime'
                }

                result = self.db.session.execute(text(query), params)
                self.db.session.commit()

                # 🔥 SQLite-safe way to get last inserted ID
                event_id = result.lastrowid

                if event_id:
                    self.logger.info(f"✅ Created alert event ID: {event_id}")
                    return event_id

        except Exception as e:
            self.logger.exception("❌ Error creating alert event")
            self.db.session.rollback()

        return None
        
    def execute_rule_actions(self, rule: Dict, event_id: int, value: float):

        try:
            with self.app.app_context():   # 🔥 ADD THIS LINE

                if not rule.get('action'):
                    self.logger.debug(f"No actions configured for rule {rule['name']}")
                    return

                actions_config = {}

                if isinstance(rule['action'], str):
                    try:
                        actions_config = json.loads(rule['action'])
                    except json.JSONDecodeError:
                        if rule.get('action_types'):
                            try:
                                actions_config = json.loads(rule['action_types'])
                            except:
                                self.logger.warning(
                                    f"Invalid JSON in actions for rule {rule['name']}"
                                )
                                return
                        else:
                            self.logger.warning(
                                f"Invalid JSON in actions for rule {rule['name']}"
                            )
                            return

                elif isinstance(rule['action'], dict):
                    actions_config = rule['action']
                else:
                    self.logger.warning(
                        f"Invalid actions format for rule {rule['name']}"
                    )
                    return

                for action_type, config in actions_config.items():

                    if not isinstance(config, dict):
                        config = {'enabled': bool(config)}

                    if not config.get('enabled', True):
                        continue

                    self.log_action(event_id, rule['id'], action_type, config)

                    if action_type == "web":
                        self.execute_web_notification(rule, event_id, value, config)

                    elif action_type == "email":
                        self.execute_email_action(rule, event_id, value, config)

                    elif action_type == "sms":
                        self.execute_sms_action(rule, event_id, value, config)

                    elif action_type == "mqtt":
                        self.execute_mqtt_action(rule, event_id, value, config)

                    else:
                        self.logger.warning(f"Unknown action type: {action_type}")

        except Exception as e:
            self.logger.error(f"❌ Error executing actions: {e}")
    
    def log_action(self, event_id: int, rule_id: int, action_type: str, config: Dict):
        """Log action execution - ADAPTED FOR YOUR alert_action_log TABLE"""
        try:
            query = """
            INSERT INTO alert_action_log 
            (alert_event_id, action_type, target, status, executed_at)
            VALUES (:event_id, :action_type, :target, :status, :executed_at)
            """
            
            params = {
                'event_id': event_id,
                'action_type': action_type,
                'target': json.dumps(config),
                'status': 'pending',
                'executed_at': datetime.utcnow()
            }
            
            self.execute_query(query, params, fetch=False)
            self.logger.debug(f"📝 Logged {action_type} action for event {event_id}")
            
        except Exception as e:
            self.logger.error(f"❌ Error logging action: {e}")
    
    def execute_web_notification(self, rule: Dict, event_id: int, value: float, config: Dict):
        """Send real-time web notification (DB + Socket.IO)"""
        try:
            # --------------------------------------------------
            # Get device name
            # --------------------------------------------------
            device_query = "SELECT name FROM devices WHERE id = :device_id"
            device_result = self.execute_query(
                device_query,
                {'device_id': rule['device_id']}
            )
            device_name = (
                device_result[0][0]
                if device_result and device_result[0]
                else "Unknown Device"
            )

            # --------------------------------------------------
            # Get active users for company
            # --------------------------------------------------
            user_query = """
            SELECT id FROM users
            WHERE company_id = :company_id AND active_status = TRUE
            """
            users = self.execute_query(
                user_query,
                {'company_id': rule['company_id']}
            )

            if not users:
                self.logger.warning(
                    f"No active users found for company {rule['company_id']}"
                )
                return

            # --------------------------------------------------
            # Prepare notification content
            # --------------------------------------------------
            title = f"🚨 Alert: {rule['name']}"
            message = (
                f"{device_name} - {rule['parameter_type']}: "
                f"{value} {rule['unit']}"
            )

            now = datetime.utcnow()

            # --------------------------------------------------
            # Insert DB notifications + emit Socket.IO
            # --------------------------------------------------
            for (user_id,) in users:
                # 1️⃣ Store notification in DB
                notification_query = """
                INSERT INTO web_notifications
                (user_id, title, message, notification_type, is_read, created_at)
                VALUES (:user_id, :title, :message, :notification_type, :is_read, :created_at)
                """

                self.execute_query(
                    notification_query,
                    {
                        'user_id': user_id,
                        'title': title,
                        'message': message,
                        'notification_type': 'alert',
                        'is_read': False,
                        'created_at': now
                    },
                    fetch=False
                )

                # 2️⃣ Emit real-time alert to frontend - USE SAME EVENT NAME!
                socketio.emit(
                    "alert_triggered",  # CHANGED FROM "new_alert" TO "alert_triggered"
                    {
                        "title": title,
                        "message": message,
                        "severity": rule.get("severity", "warning"),
                        "audio": {
                            "sound": "beep",
                            "volume": 0.8,
                            "loop": False
                        },
                        "rule_id": rule["id"],
                        "event_id": event_id,
                        "device_id": rule["device_id"],
                        "parameter": rule["parameter_type"],
                        "value": value,
                        "unit": rule["unit"],
                        "timestamp": now.isoformat()
                    },
                    room=f"alerts_user_{user_id}"
                )

            self.logger.info(
                f"📢 Web alerts delivered to {len(users)} users: {title}"
            )

            # --------------------------------------------------
            # Update action log status
            # --------------------------------------------------
            update_query = """
            UPDATE alert_action_log
            SET status = 'sent', payload = :payload
            WHERE alert_event_id = :event_id AND action_type = 'web'
            """

            self.execute_query(
                update_query,
                {
                    'payload': json.dumps({
                        'title': title,
                        'message': message,
                        'users_count': len(users)
                    }),
                    'event_id': event_id
                },
                fetch=False
            )

        except Exception as e:
            self.logger.exception("❌ Error sending web notification")
    
    def execute_email_action(self, rule: Dict, event_id: int, value: float, config: Dict):
        """Execute email action (placeholder)"""
        try:
            self.logger.info(f"📧 Email action for rule {rule['name']}")
            
            # Update action log
            update_query = """
            UPDATE alert_action_log 
            SET status = 'sent', payload = :payload
            WHERE alert_event_id = :event_id AND action_type = 'email'
            """
            
            self.execute_query(update_query, {
                'payload': json.dumps({
                    'rule_name': rule['name'],
                    'device_id': rule['device_id'],
                    'parameter': rule['parameter_type'],
                    'value': value,
                    'unit': rule['unit']
                }),
                'event_id': event_id
            }, fetch=False)
            
        except Exception as e:
            self.logger.error(f"❌ Error in email action: {e}")
    
    def execute_sms_action(self, rule: Dict, event_id: int, value: float, config: Dict):
        """Execute SMS action with strict DLT template + subscription + logging"""
        try:
            from rule_engine.sms_service import SMSService

            sms_service = SMSService(self.db, self.app)

            company_id = rule["company_id"]
            device_id = rule["device_id"]

            self.logger.info(f"📱 Processing SMS action for rule {rule['name']}")

            # --------------------------------------------------
            # 1️⃣ Get mapped phone numbers for rule
            # --------------------------------------------------
            phones = self.execute_query("""
                SELECT pn.phone_number
                FROM alert_rule_phone_map rpm
                JOIN phone_numbers pn ON pn.id = rpm.phone_number_id
                WHERE rpm.rule_id = :rule_id
                AND pn.is_active = 1
            """, {"rule_id": rule["id"]})

            if not phones:
                self.logger.warning("⚠️ No phone numbers mapped for this rule")
                return

            # --------------------------------------------------
            # 2️⃣ Get device name
            # --------------------------------------------------
            device_row = self.execute_query("""
                SELECT name FROM devices WHERE id = :device_id
            """, {"device_id": device_id})

            device_name = device_row[0][0] if device_row else "Device"

            # --------------------------------------------------
            # 3️⃣ STRICT DLT TEMPLATE (DO NOT MODIFY FORMAT)
            # --------------------------------------------------
            MESSAGE_TEMPLATE = (
                "🚨 Alert from Kled IoT {name} - {parameter} Alert! "
                "{parameter}: {value} "
                "Time: {alert_time} "
                "Please take necessary action. - Kled"
            )

            # Must match registered time format exactly
            alert_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 🔥 CORRECT COLUMN: Use metric for alert label
            parameter = rule.get("metric")

            if not parameter:
                parameter = "Parameter"

            # Remove decimal .0 if integer
            try:
                if float(value).is_integer():
                    value = int(value)
            except:
                pass

            message = MESSAGE_TEMPLATE.format(
                name=device_name,
                parameter=parameter,
                value=value,
                alert_time=alert_time
            )

            self.logger.info(f"📩 Final SMS Message: {message}")

            # --------------------------------------------------
            # 4️⃣ Send SMS
            # --------------------------------------------------
            successful = 0
            failed = 0

            for (phone,) in phones:

                if not sms_service.check_sms_quota(company_id):
                    self.logger.warning("❌ SMS quota exceeded")
                    break

                sent = sms_service.send_sms(company_id, phone, message)

                if sent:
                    successful += 1
                else:
                    failed += 1

            # --------------------------------------------------
            # 5️⃣ Update action log
            # --------------------------------------------------
            status = "sent" if successful > 0 else "failed"

            update_query = """
            UPDATE alert_action_log
            SET status = :status,
                payload = :payload
            WHERE alert_event_id = :event_id
            AND action_type = 'sms'
            """

            self.execute_query(update_query, {
                "status": status,
                "payload": json.dumps({
                    "successful": successful,
                    "failed": failed,
                    "company_id": company_id,
                    "message": message
                }),
                "event_id": event_id
            }, fetch=False)

            self.logger.info(
                f"📱 SMS completed → Success: {successful}, Failed: {failed}"
            )

        except Exception as e:
            self.logger.exception("❌ Error in execute_sms_action")

            # --------------------------------------------------
            # 4️⃣ Send SMS
            # --------------------------------------------------
            successful = 0
            failed = 0

            for (phone,) in phones:

                # Check quota before each send
                if not sms_service.check_sms_quota(company_id):
                    self.logger.warning("❌ SMS quota exceeded")
                    break

                sent = sms_service.send_sms(company_id, phone, message)

                if sent:
                    successful += 1
                else:
                    failed += 1

            # --------------------------------------------------
            # 5️⃣ Update action log
            # --------------------------------------------------
            status = "sent" if successful > 0 else "failed"

            update_query = """
            UPDATE alert_action_log
            SET status = :status,
                payload = :payload
            WHERE alert_event_id = :event_id
            AND action_type = 'sms'
            """

            self.execute_query(update_query, {
                "status": status,
                "payload": json.dumps({
                    "successful": successful,
                    "failed": failed,
                    "company_id": company_id,
                    "message": message
                }),
                "event_id": event_id
            }, fetch=False)

            self.logger.info(
                f"📱 SMS completed → Success: {successful}, Failed: {failed}"
            )

        except Exception as e:
            self.logger.exception("❌ Error in execute_sms_action")
        
    def execute_mqtt_action(self, rule: Dict, event_id: int, value: float, config: Dict):
        """Execute MQTT action (publish to topic)"""
        try:
            topic = config.get('topic', f"alerts/{rule['device_id']}")
            payload = {
                'rule_id': rule['id'],
                'rule_name': rule['name'],
                'device_id': rule['device_id'],
                'parameter': rule['parameter_type'],
                'value': value,
                'unit': rule['unit'],
                'threshold': rule['threshold'],
                'operator': rule['operator'],
                'timestamp': datetime.utcnow().isoformat()
            }
            
            # TODO: Implement actual MQTT publish
            # mqtt_client.publish(topic, json.dumps(payload))
            
            self.logger.info(f"📡 MQTT action for rule {rule['name']} on topic {topic}")
            
            # Update action log
            update_query = """
            UPDATE alert_action_log 
            SET status = 'sent', payload = :payload
            WHERE alert_event_id = :event_id AND action_type = 'mqtt'
            """
            
            self.execute_query(update_query, {
                'payload': json.dumps(payload),
                'event_id': event_id
            }, fetch=False)
            
        except Exception as e:
            self.logger.error(f"❌ Error in MQTT action: {e}")
    
    def update_rule_last_triggered(self, rule_id: int):
        """Update rule's last_triggered timestamp"""
        try:
            query = """
            UPDATE alert_rule 
            SET last_triggered = :now
            WHERE id = :rule_id
            """
            
            now = datetime.utcnow()
            self.execute_query(query, {'now': now, 'rule_id': rule_id}, fetch=False)
            
            # Also update cache
            for key in self.rules_cache:
                for rule in self.rules_cache[key]:
                    if rule['id'] == rule_id:
                        rule['last_triggered'] = now
                        break
            
        except Exception as e:
            self.logger.error(f"❌ Error updating rule last_triggered: {e}")
    
    def start_real_time_processing(self, interval_seconds: float = 0.5):
        """Start real-time processing with faster intervals"""
        if self.processing_active:
            self.logger.warning("⚠️ Real-time processor is already running")
            return
        
        # Load rules before starting
        self.load_all_rules()
        
        self.processing_active = True

        socketio.start_background_task(
            self._real_time_processing_loop,
            interval_seconds
        )

        self.logger.info(
            f"🚀 Started REAL-TIME processing with {interval_seconds} second interval"
        )
    
    def stop_real_time_processing(self):
        """Stop the real-time processing"""
        self.processing_active = False
        if self.rule_check_thread:
            self.rule_check_thread.join(timeout=2.0)
        self.logger.info("🛑 Real-time processor stopped")
    
    def _real_time_processing_loop(self, interval_seconds: float):
        """Real-time processing loop"""
        while self.processing_active:
            try:
                # Process queue if there are items
                if self.rule_check_queue:
                    self.process_queue()
                
                # Very short sleep for real-time
                time.sleep(interval_seconds)
                
            except Exception as e:
                self.logger.error(f"❌ Error in real-time loop: {e}")
                time.sleep(1)  # Longer sleep on error
    
    def refresh_rules(self):
        """Refresh rules cache (call when rules are modified)"""
        self.load_all_rules()
        self.logger.info("🔄 Rules cache refreshed")
    
    def get_rule_stats(self) -> Dict:
        """Get statistics about rules and processing"""
        total_rules = sum(len(rules) for rules in self.rules_cache.values())
        return {
            'total_rules_cached': total_rules,
            'queue_size': len(self.rule_check_queue),
            'processing_active': self.processing_active,
            'rules_cache_keys': len(self.rules_cache),
            'last_refresh': datetime.utcnow().isoformat()
        }


# Create a global instance (optional)
real_time_processor = RealTimeRuleProcessor()