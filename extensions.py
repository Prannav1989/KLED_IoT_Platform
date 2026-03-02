# extensions.py
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from flask_socketio import SocketIO

# =========================
# DATABASE & AUTH
# =========================
db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()

# =========================
# SOCKET.IO (🔥 HARD FIX)
# =========================
# ⚠️ DO NOT change this
# ⚠️ DO NOT add eventlet/gevent
# ⚠️ This is REQUIRED for PyInstaller EXE
socketio = SocketIO(
    async_mode="threading",          # 🔒 Force threading
    cors_allowed_origins="*",
    logger=False,
    engineio_logger=False
)
