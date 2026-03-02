# run_app.py
import threading
import time
import webbrowser
import os
import sys

from app import create_app
from extensions import socketio
from config import Config

app = create_app()

# =========================
# 🔧 AUTO OPEN BROWSER TOGGLE
# Priority:
# 1. Command-line flag
# 2. Environment variable
# 3. Config.py default
# =========================

def str_to_bool(value, default=True):
    if value is None:
        return default
    return value.lower() in ("1", "true", "yes", "on")

# 3️⃣ Default from Config
AUTO_OPEN_BROWSER = getattr(Config, "AUTO_OPEN_BROWSER", False)

# 2️⃣ Override via environment variable
# set AUTO_OPEN_BROWSER=0
AUTO_OPEN_BROWSER = str_to_bool(
    os.getenv("AUTO_OPEN_BROWSER"),
    AUTO_OPEN_BROWSER
)

# 1️⃣ Override via command-line flags
# python run_app.py --no-browser
# python run_app.py --browser
if "--no-browser" in sys.argv:
    AUTO_OPEN_BROWSER = False
elif "--browser" in sys.argv:
    AUTO_OPEN_BROWSER = True


def open_browser():
    time.sleep(1.5)
    webbrowser.open(f"http://127.0.0.1:{Config.PORT}")


if __name__ == "__main__":

    if AUTO_OPEN_BROWSER:
        threading.Thread(
            target=open_browser,
            daemon=True
        ).start()

    socketio.run(
        app,
        host=Config.HOST,
        port=Config.PORT,
        debug=True,
        allow_unsafe_werkzeug=True
    )
