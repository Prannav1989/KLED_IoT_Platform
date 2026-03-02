# import os
# from dotenv import load_dotenv

# # Load environment variables from .env if present
# load_dotenv()

# class Config:
#     # App Security
#     SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key-here')
    
#     # Database connection (PostgreSQL recommended)
#     # Note: Using DB_URI to match app.py, change to DATABASE_URL if preferred
#     SQLALCHEMY_DATABASE_URI = os.getenv(
#         'DB_URI', 
#         'postgresql://postgres:1234@localhost:5433/iot'
#     )
    
#     SQLALCHEMY_TRACK_MODIFICATIONS = False
    
#     # MQTT Settings
#     MQTT_BROKER_URL = os.getenv('MQTT_BROKER_URL', 'localhost')
#     MQTT_BROKER_PORT = int(os.getenv('MQTT_BROKER_PORT', 1883))
    
#     # Flask-SocketIO
#     SOCKETIO_ASYNC_MODE = os.getenv('SOCKETIO_ASYNC_MODE', 'threading')
    
#     # Application settings
#     DEBUG = os.getenv('FLASK_DEBUG', 'True').lower() in ['true', '1', 'yes']
#     PORT = int(os.getenv('PORT', 5000))
#     HOST = os.getenv('HOST', '0.0.0.0')
    
#     # Sensor Data Processor
#     SENSOR_PROCESSOR_INTERVAL = int(os.getenv('SENSOR_PROCESSOR_INTERVAL', 10))
    
#     # CSRF Protection
#     WTF_CSRF_ENABLED = True
#     WTF_CSRF_SECRET_KEY = os.getenv('WTF_CSRF_SECRET_KEY', 'csrf-secret-key')

#config.py
import os
import sys
from dotenv import load_dotenv

# Load .env ONLY for dev / cloud
# (Safe because we are NOT using it for SocketIO)
load_dotenv()


def get_base_dir():
    """
    Returns correct base directory for:
    - Normal Python run
    - PyInstaller EXE
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = get_base_dir()


class Config:
    # =========================
    # APP SECURITY
    # =========================
    SECRET_KEY = os.getenv(
        'SECRET_KEY',
        'kled-iot-local-secret-2025'
    )

    # =========================
    # RUN MODE
    # exe   → Client PC (SQLite)
    # cloud → Server (PostgreSQL)
    # =========================
    RUN_MODE = os.getenv('RUN_MODE', 'exe').lower()

    # =========================
    # DATABASE CONFIG
    # =========================
    if RUN_MODE == 'exe':
        DATA_DIR = os.path.join(BASE_DIR, "data")
        os.makedirs(DATA_DIR, exist_ok=True)

        SQLITE_DB_PATH = os.path.join(DATA_DIR, "iot.db")
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{SQLITE_DB_PATH}"
    else:
        SQLALCHEMY_DATABASE_URI = os.getenv(
            'DB_URI',
            'postgresql://postgres:1234@localhost:5433/iot'
        )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # =========================
    # MQTT SETTINGS
    # =========================
    MQTT_BROKER_URL = os.getenv('MQTT_BROKER_URL', 'localhost')
    MQTT_BROKER_PORT = int(os.getenv('MQTT_BROKER_PORT', 1883))

    # =========================
    # SOCKET.IO  ✅ EXE-SAFE
    # =========================
    # ⚠️ DO NOT use env variables here
    # ⚠️ PyInstaller supports ONLY threading
    # SOCKETIO_ASYNC_MODE = "threading"

    # =========================
    # FLASK SERVER SETTINGS
    # =========================
    DEBUG = False                # 🔒 FORCE FALSE (EXE SAFE)
    HOST = '0.0.0.0'             # 🔓 Browser + LAN safe
    PORT = int(os.getenv('PORT', 5000))

    # =========================
    # SENSOR PROCESSOR
    # =========================
    SENSOR_PROCESSOR_INTERVAL = int(
        os.getenv('SENSOR_PROCESSOR_INTERVAL', 10)
    )

    # =========================
    # CSRF
    # =========================
    WTF_CSRF_ENABLED = True
    WTF_CSRF_SECRET_KEY = os.getenv(
        'WTF_CSRF_SECRET_KEY',
        'csrf-secret-key'
    )
