# models.py
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from flask_login import UserMixin
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField
from wtforms.validators import DataRequired, Email, Length, Optional
from wtforms import StringField, PasswordField, SelectField, SubmitField
from wtforms.validators import DataRequired, Email, Length
from sqlalchemy import event
# from sqlalchemy.dialects.postgresql import JSONB
from db_types import JSONType



# Import from extensions instead of creating new instance
from extensions import db

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    role = db.Column(db.String(20), nullable=False, default='user')
    parent_admin_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'))  
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    active_status = db.Column(db.Boolean, default=True)

    # One-to-many: Devices "owned" by this user (via devices.user_id)
    devices = db.relationship('Device', backref='owner', lazy=True)

    # Many-to-many: Devices "allocated" to this user (via user_devices link table)
    allocated_devices = db.relationship(
        'Device',
        secondary='user_devices',
        backref=db.backref('assigned_users', lazy='dynamic'),
        lazy='dynamic'
    )

    mqtt_configs = db.relationship('MQTTConfig', backref='owner', lazy=True)
    # Removed sensors relationship

    parent_admin = db.relationship(
        'User',
        remote_side=[id],
        backref=db.backref('sub_users', lazy='dynamic'),
        foreign_keys=[parent_admin_id],
        uselist=False
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def can_access_dashboard(self, dashboard_id):
        """Check if user can access the dashboard"""
        # No imports needed since we're already in models.py
        dashboard = Dashboard.query.get(dashboard_id)
        if not dashboard:
            return False
        
        # User created the dashboard
        if dashboard.created_by == self.id:
            return True
        
        # User has been shared the dashboard
        if UserDashboard.query.filter_by(user_id=self.id, dashboard_id=dashboard_id).first():
            return True
        
        # Super admin can access all dashboards
        if self.role == 'super_admin':
            return True
        
        # Admin can access dashboards in their company
        if self.role == 'admin' and str(dashboard.company_id) == str(self.company_id):
            return True
        
        return False

    @property
    def parent_admin_name(self):
        return self.parent_admin.username if self.parent_admin else None


    def __repr__(self):
        return f'<User {self.username}>'

class MQTTConfig(db.Model):
    __tablename__ = 'mqtt_configs'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    broker_url = db.Column(db.String(255), nullable=False)
    port = db.Column(db.Integer, nullable=False, default=1883)
    username = db.Column(db.String(100))
    password_hash = db.Column(db.String(128))
    password = db.Column(db.String(255))
    ssl_enabled = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    devices = db.relationship('Device', backref='mqtt_config', lazy=True)
    
    def get_mqtt_password(self):
        return self.password or self.password_hash

    
class Device(db.Model):
    __tablename__ = 'devices'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)

    # DevEUI / SN → must be UNIQUE
    device_id = db.Column(db.String(100), nullable=False, unique=True)

    # Shared topic → MUST NOT be unique
    mqtt_topic = db.Column(db.String(255), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    mqtt_config_id = db.Column(db.Integer, db.ForeignKey('mqtt_configs.id'), nullable=False)
    description = db.Column(db.Text, nullable=True)
    
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    sensor_model_id = db.Column(db.Integer, db.ForeignKey('sensor_models.id'), nullable=True)
    
    is_active = db.Column(db.Boolean, default=True)
    last_seen = db.Column(db.DateTime)

    authorized_users = db.relationship(
        'User', 
        secondary='user_devices', 
        backref=db.backref('authorized_devices', lazy='dynamic')
    )

    parameters = db.relationship('Parameter', backref='device', lazy='dynamic')
    sensor_model = db.relationship('SensorModel', backref='devices', lazy=True)

    @property
    def status(self):
        if not self.is_active:
            return 'inactive'
        if self.last_seen:
            return 'online' if (datetime.utcnow() - self.last_seen).total_seconds() < 300 else 'offline'
        return 'offline'


class UserDevice(db.Model):
    __tablename__ = 'user_devices'
    
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey('devices.id'), primary_key=True)
    permission_level = db.Column(db.String(20), default='read')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Removed Sensor model entirely

class SensorData(db.Model):
    __tablename__ = 'sensor_data'
    
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey('devices.id'), nullable=False, index=True)
    # Removed sensor_id foreign key
    value = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(20))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    parameter_type = db.Column(db.String(50), nullable=False, default='unknown')
    
    # FIXED: Add proper foreign key constraint
    parameter_id = db.Column(db.Integer, db.ForeignKey('parameters.id'), nullable=True, index=True)


class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=2, max=20)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    role = SelectField('Role', choices=[('user', 'User'), ('admin', 'Admin')])
    submit = SubmitField('Register')


class MQTTMessage(db.Model):
    __tablename__ = 'mqtt_messages'
    
    id = db.Column(db.Integer, primary_key=True)
    topic = db.Column(db.String(255), nullable=False, index=True)
    payload = db.Column(db.Text, nullable=False)
    qos = db.Column(db.Integer, default=0)
    retain = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    mqtt_config_id = db.Column(db.Integer, db.ForeignKey('mqtt_configs.id'), nullable=False)
    processed = db.Column(db.Boolean, default=False)
    
    # # ADD THESE NEW FIELDS:
    # processing_id = db.Column(db.String(100), nullable=True, index=True)
    # process_pid = db.Column(db.Integer, nullable=True)
    
    # Relationship
    mqtt_config = db.relationship('MQTTConfig', backref='raw_messages')


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(255), nullable=False)   # short description
    details = db.Column(db.Text, nullable=True)          # optional JSON or notes
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship back to user
    user = db.relationship("User", backref="audit_logs")

    def __repr__(self):
        return f"<AuditLog {self.id} - {self.action}>"
    
class Company(db.Model):
    __tablename__ = 'companies'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    users = db.relationship('User', backref='company', lazy=True)
    devices = db.relationship('Device', backref='company', lazy=True)

class Dashboard(db.Model):
    __tablename__ = 'dashboards'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    company = db.relationship('Company', backref='dashboards')
    
    # Specify foreign_keys explicitly to resolve ambiguity
    creator = db.relationship(
        'User', 
        foreign_keys=[created_by],
        backref=db.backref('created_dashboards', lazy=True)
    )


class DashboardSensor(db.Model):
    __tablename__ = 'dashboard_sensors'

    id = db.Column(db.Integer, primary_key=True)
    dashboard_id = db.Column(db.Integer, db.ForeignKey('dashboards.id'), nullable=False)
    device_id = db.Column(db.Integer, db.ForeignKey('devices.id'), nullable=False)  
    added_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships (optional but helpful)
    dashboard = db.relationship('Dashboard', backref='device_assignments')
    device = db.relationship('Device', backref='dashboard_assignments')


class UserDashboard(db.Model):
    __tablename__ = 'user_dashboards'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)          
    dashboard_id = db.Column(db.Integer, db.ForeignKey('dashboards.id'), nullable=False)  
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='dashboard_assignments')
    dashboard = db.relationship('Dashboard', backref='user_assignments')


class NavigationSettings(db.Model):
    __tablename__ = 'navigation_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    dashboard_id = db.Column(db.Integer, db.ForeignKey('dashboards.id'))
    
    # Navigation features
    dashboard_management = db.Column(db.Boolean, default=False)
    reports = db.Column(db.Boolean, default=False)
    analytics = db.Column(db.Boolean, default=False)
    download = db.Column(db.Boolean, default=False)
    support = db.Column(db.Boolean, default=True)
    settings = db.Column(db.Boolean, default=False)
    
    # Role-based approval
    approved_for_admin = db.Column(db.Boolean, default=False)
    approved_for_user = db.Column(db.Boolean, default=False)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    dashboard = db.relationship('Dashboard', backref=db.backref('navigation_settings', lazy=True))
    
    def to_dict(self):
        return {
            'id': self.id,
            'dashboard_management': self.dashboard_management,
            'reports': self.reports,
            'analytics': self.analytics,
            'download': self.download,
            'support': self.support,
            'settings': self.settings,
            'approved_for_admin': self.approved_for_admin,
            'approved_for_user': self.approved_for_user
        }
    
    @classmethod
    def get_user_navigation_settings(cls, dashboard_id, user_role):
        settings = cls.query.filter_by(dashboard_id=dashboard_id).first()
        if not settings:
            # Create default settings if none exist
            settings = cls(dashboard_id=dashboard_id)
            db.session.add(settings)
            db.session.commit()
        
        nav_settings = settings.to_dict()
        
        # Apply role-based filtering
        filtered_settings = {}
        
        for feature, enabled in nav_settings.items():
            if feature in ['id', 'approved_for_admin', 'approved_for_user']:
                continue
                
            if user_role == 'super_admin':
                filtered_settings[feature] = enabled
            elif user_role == 'admin':
                filtered_settings[feature] = enabled and settings.approved_for_admin
            else:  # user
                filtered_settings[feature] = enabled and settings.approved_for_user
        
        return filtered_settings

class ReportPermission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    report_name = db.Column(db.String(100))
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))  # admin/superadmin
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    is_approved = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


class Parameter(db.Model):
    __tablename__ = 'parameters'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    sensor_type = db.Column(db.String(50), nullable=False)
    unit = db.Column(db.String(20))
    device_id = db.Column(db.Integer, db.ForeignKey('devices.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # FIXED: Add proper foreign key relationship
    sensor_data = db.relationship('SensorData', backref='parameter', lazy='dynamic')

    def __repr__(self):
        return f'<Parameter {self.name} (Device: {self.device_id})>'

class NavigationPermissions(db.Model):
    __tablename__ = 'navigation_permissions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    dashboard_management = db.Column(db.Boolean, default=False)
    reports = db.Column(db.Boolean, default=False)
    analytics = db.Column(db.Boolean, default=False)
    settings = db.Column(db.Boolean, default=False)
    download = db.Column(db.Boolean, default=False)
    support = db.Column(db.Boolean, default=False)
    granted_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = db.relationship('User', foreign_keys=[user_id], backref='navigation_permissions')
    grantor = db.relationship('User', foreign_keys=[granted_by])

class SensorModel(db.Model):
    """Database model for sensor models/templates that can have multiple parameters"""
    __tablename__ = 'sensor_models'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True, index=True)
    manufacturer = db.Column(db.String)                 # matches your DB
    parameters = db.Column(JSONType, nullable=False, default=list)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # Backwards-compatible alias for code that still uses model_name
    @property
    def model_name(self):
        return self.name

    @model_name.setter
    def model_name(self, val):
        self.name = val  

    def to_dict(self):
        """Convert model to dictionary for JSON serialization"""
        # JSONB fields in PostgreSQL return as Python objects when using SQLAlchemy
        # So we can use self.parameters directly
        
        # Handle parameters safely
        params = self.parameters
        if params is None:
            params = []
        elif not isinstance(params, list):
            # If it's not a list, try to convert it
            try:
                # If it's already a dict or other iterable that's not a list
                if hasattr(params, 'items'):  # It's a dict-like object
                    params = [params]
                elif hasattr(params, '__iter__') and not isinstance(params, str):
                    params = list(params)
                else:
                    params = []
            except:
                params = []
        
        return {
            'id': self.id,
            'name': self.name or '',
            'manufacturer': self.manufacturer or '',
            'parameters': params,
            'description': self.description or '',
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
    
    @property
    def parameter_types(self):
        types = set()
        for param in self.parameters or []:
            if isinstance(param, dict):
                # Try multiple possible keys for type
                param_type = param.get('type') or param.get('parameter_type') or param.get('sensor_type')
                if param_type:
                    types.add(param_type)
        return list(types)
    
    @property
    def parameter_count(self):
        params = self.parameters
        if params is None:
            return 0
        if hasattr(params, '__len__'):
            return len(params)
        return 0

    def __repr__(self):
        return f"<SensorModel {self.name}>"
    
#Alert 
class AlertEvent(db.Model):
    __tablename__ = "alert_event"

    id = db.Column(db.Integer, primary_key=True)

    rule_id = db.Column(db.Integer, nullable=False)
    device_id = db.Column(db.Integer, nullable=False)

    parameter_type = db.Column(db.String(50), nullable=False)
    actual_value = db.Column(db.Float, nullable=False)
    threshold = db.Column(db.Float, nullable=False)

    triggered_at = db.Column(db.DateTime, nullable=False)

    status = db.Column(db.String(20), nullable=False, default="triggered")
    source = db.Column(db.String(20), nullable=False, default="mqtt")


# Add these to your existing models.py


class NotificationTemplate(db.Model):
    __tablename__ = 'notification_templates'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    subject = db.Column(db.String(200))
    body_template = db.Column(db.Text, nullable=False)
    variables = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SensorAction(db.Model):
    __tablename__ = 'sensor_actions'
    
    id = db.Column(db.Integer, primary_key=True)
    sensor_model_id = db.Column(db.Integer, db.ForeignKey('sensor_models.id'), nullable=False)
    action_type = db.Column(db.String(50), nullable=False)
    payload_template = db.Column(db.Text, nullable=False)
    mqtt_topic = db.Column(db.String(255))
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    sensor_model = db.relationship('SensorModel', backref='sensor_actions')

class WebNotification(db.Model):
    __tablename__ = 'web_notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(50), default='alert')
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref='web_notifications')

# Update your existing AlertRule model
from datetime import datetime

from datetime import datetime
import json
from extensions import db


class AlertRule(db.Model):
    __tablename__ = "alert_rule"

    # =========================
    # Core fields
    # =========================
    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)

    device_id = db.Column(db.Integer, nullable=False)
    parameter_id = db.Column(db.Integer, nullable=False)

    # =========================
    # Metric definition (CRITICAL)
    # =========================
    metric = db.Column(db.String(50), nullable=False)   # machine key (e.g. "co2")
    parameter_type = db.Column(db.String(50))           # display name (e.g. "CO2")
    unit = db.Column(db.String(20))                      # ppm, °C, %

    # =========================
    # Rule condition
    # =========================
    operator = db.Column(db.String(10), nullable=False)  # > < >= <= ==
    threshold = db.Column(db.Float, nullable=False)
    cooldown_seconds = db.Column(db.Integer, default=300)

    # =========================
    # Actions
    # =========================
    action = db.Column(db.Text)        # JSON config
    action_types = db.Column(db.Text)  # JSON list

    # =========================
    # Metadata
    # =========================
    severity = db.Column(db.String(20), default="warning")
    tags = db.Column(db.String(200))
    enabled = db.Column(db.Boolean, default=True)
    
    # =========================
    # ADD THIS: Tracking field from your database table
    # =========================
    last_triggered = db.Column(db.DateTime, nullable=True)

    created_by = db.Column(db.Integer, nullable=False)
    company_id = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # =========================
    # Helpers
    # =========================
    def to_dict(self):
        """Safe serialization for UI / API"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,

            "device_id": self.device_id,
            "parameter_id": self.parameter_id,

            "metric": self.metric,
            "parameter_type": self.parameter_type,
            "unit": self.unit,

            "operator": self.operator,
            "threshold": self.threshold,
            "cooldown_seconds": self.cooldown_seconds,

            "action": json.loads(self.action) if self.action else {},
            "action_types": json.loads(self.action_types) if self.action_types else [],

            "severity": self.severity,
            "tags": self.tags,
            "enabled": self.enabled,
            
            # ADD THIS: Include last_triggered in serialization
            "last_triggered": self.last_triggered.isoformat() if self.last_triggered else None,

            "created_by": self.created_by,
            "company_id": self.company_id,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

    def __repr__(self):
        last_triggered_str = self.last_triggered.strftime("%Y-%m-%d %H:%M") if self.last_triggered else "Never"
        return (
            f"<AlertRule id={self.id} "
            f"metric={self.metric} "
            f"operator={self.operator} "
            f"threshold={self.threshold} "
            f"last_triggered={last_triggered_str}>"
        )



class AlertActionLog(db.Model):
    __tablename__ = "alert_action_log"

    id = db.Column(db.Integer, primary_key=True)

    alert_event_id = db.Column(
        db.Integer,
        db.ForeignKey("alert_event.id"),
        nullable=False
    )

    action_type = db.Column(db.String(30), nullable=False)
    target = db.Column(db.Text, nullable=False)
    payload = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False)
    executed_at = db.Column(db.DateTime, nullable=False)


class PhoneNumber(db.Model):
    __tablename__ = "phone_numbers"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)
    phone_number = db.Column(db.String(20), nullable=False)
    recipient_name = db.Column(db.String(100))
    recipient_role = db.Column(db.String(50))
    purpose = db.Column(db.String(50), default="all")
    priority = db.Column(db.Integer, default=1)
    is_active = db.Column(db.Boolean, default=True)
    verified = db.Column(db.Boolean, default=False)
    verified_at = db.Column(db.DateTime)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    created_by = db.Column(db.Integer)

    def __repr__(self):
        return f"<PhoneNumber {self.phone_number}>"

class SmsTemplate(db.Model):
    __tablename__ = "sms_templates"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    template_type = db.Column(db.String(50), nullable=False)
    subject = db.Column(db.String(200))
    body = db.Column(db.Text, nullable=False)
    placeholders = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    company_id = db.Column(db.Integer, nullable=False)
    created_by = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())

    def __repr__(self):
        return f"<SmsTemplate {self.name}>"



class AlertRulePhoneMap(db.Model):
    __tablename__ = "alert_rule_phone_map"

    id = db.Column(db.Integer, primary_key=True)
    rule_id = db.Column(db.Integer, db.ForeignKey("alert_rule.id"), nullable=False)
    phone_number_id = db.Column(db.Integer, db.ForeignKey("phone_numbers.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    rule = db.relationship("AlertRule", backref="phone_mappings")
    phone = db.relationship("PhoneNumber")