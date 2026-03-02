# app.py
import atexit
from flask import Flask
from flask_wtf.csrf import generate_csrf
from sqlalchemy import event
from sqlalchemy.engine import Engine

from config import Config
from extensions import db, login_manager, migrate, csrf, socketio
from mqtt_manager import mqtt_manager
from models import User

# 🔥 FIXED IMPORT - Import the class, not an instance
from rule_engine.real_time_rule_processor import RealTimeRuleProcessor
# 🔥 ADD SENSOR DATA PROCESSOR IMPORT
from sensor_data_processor import SensorDataProcessor

# Blueprints
from routes.auth_routes import auth_bp
from routes.device_routes import device_bp
from routes.api_routes import api_bp
from routes.main_routes import main_bp
from routes.admin_routes import admin_bp
from routes.mqtt_configs import mqtt_config_bp
from routes.dashboard_routes import dashboard_bp
from routes.sensor_routes import sensor_bp
from routes.user_routes import user_bp
from routes.superadmin_routes.superadmin_routes import superadmin_bp
from routes.company_routes import company_bp
from routes.dashboard_api import dashboard_api_bp
from routes.superadmin_routes.analytics import analytics_bp
from routes.superadmin_routes.settings import dashboard_settings_bp
from routes.superadmin_routes.report import report_bp
from routes.support import support_bp
from routes.dashboard_device import dashboard_device_bp
from routes.socket_routes import register_socket_events
from routes.alert_routes.alerts import alerts_bp
from utils.jinja_filters import register_jinja_filters
from routes.alert_routes.phone_routes import phone_bp


def create_app():
    app = Flask(__name__)

    # ================= CONFIG =================
    app.config.update(
        SECRET_KEY=Config.SECRET_KEY,
        SQLALCHEMY_DATABASE_URI=Config.SQLALCHEMY_DATABASE_URI,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        WTF_CSRF_ENABLED=True,
        WTF_CSRF_SECRET_KEY=Config.WTF_CSRF_SECRET_KEY,
    )

    # ================= SQLITE FK ENABLE =================
    @event.listens_for(Engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection, connection_record):
        try:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
        except Exception:
            pass

    # ================= EXTENSIONS =================
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    socketio.init_app(app)

    login_manager.login_view = "auth.login"

    # ================= USER LOADER =================
    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # ================= BLUEPRINTS =================
    app.register_blueprint(main_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(device_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(mqtt_config_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(sensor_bp)
    app.register_blueprint(superadmin_bp)
    app.register_blueprint(company_bp)
    app.register_blueprint(dashboard_api_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(dashboard_settings_bp)
    app.register_blueprint(report_bp)
    app.register_blueprint(support_bp)
    app.register_blueprint(dashboard_device_bp)
    app.register_blueprint(alerts_bp)
    app.register_blueprint(phone_bp)
    
    # ================= SOCKET EVENTS =================
    register_socket_events(socketio)
# ================= JINJA FILTERS =================
    register_jinja_filters(app)

    # ================= INIT MQTT + REAL-TIME RULE ENGINE =================
    with app.app_context():
        mqtt_manager.init_app(app, socketio)

        # 🔥 CREATE INSTANCE OF REAL-TIME PROCESSOR
        real_time_processor = RealTimeRuleProcessor(app, db)
        
        # 🔥 CREATE INSTANCE OF SENSOR DATA PROCESSOR (connected to rule processor)
        sensor_processor = SensorDataProcessor(app, real_time_processor)
        
        # 🔥 START BOTH PROCESSORS
        real_time_processor.start_real_time_processing(interval_seconds=2)
        sensor_processor.start_continuous_processing(interval_seconds=30)

        print("🚀 Real-time rule processor started")
        print("🚀 Sensor data processor started")
        
        # Store in app context for access from other modules
        app.real_time_processor = real_time_processor
        app.sensor_processor = sensor_processor

    # ================= CLEAN SHUTDOWN =================
    @atexit.register
    def shutdown():
        # Check if processors exist before stopping
        if hasattr(app, 'sensor_processor') and app.sensor_processor:
            if app.sensor_processor.running:
                app.sensor_processor.stop_continuous_processing()
                print("🛑 Sensor data processor stopped gracefully")
        
        if hasattr(app, 'real_time_processor') and app.real_time_processor:
            if app.real_time_processor.processing_active:
                app.real_time_processor.stop_real_time_processing()
                print("🛑 Real-time rule processor stopped gracefully")

    # ================= CSRF TOKEN =================
    @app.route("/get-csrf-token")
    def get_csrf_token():
        return {"csrf_token": generate_csrf()}
    
    # ================= MONITORING ENDPOINTS =================
    @app.route("/api/monitoring/stats")
    def monitoring_stats():
        """Get monitoring statistics"""
        try:
            sensor_stats = {}
            rule_stats = {}
            
            if hasattr(app, 'sensor_processor'):
                sensor_stats = app.sensor_processor.get_processor_stats()
            
            if hasattr(app, 'real_time_processor'):
                rule_stats = app.real_time_processor.get_rule_stats()
            
            return {
                "status": "success",
                "sensor_processor": sensor_stats,
                "rule_processor": rule_stats,
                "timestamp": datetime.utcnow().isoformat()
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}, 500
    
    @app.route("/api/monitoring/refresh-rules", methods=["POST"])
    def refresh_rules():
        """Refresh rules cache"""
        try:
            if hasattr(app, 'real_time_processor'):
                app.real_time_processor.refresh_rules()
                return {"status": "success", "message": "Rules cache refreshed"}
            else:
                return {"status": "error", "message": "Rule processor not available"}, 400
        except Exception as e:
            return {"status": "error", "message": str(e)}, 500

    return app


# Add datetime import at the top if not already present
from datetime import datetime