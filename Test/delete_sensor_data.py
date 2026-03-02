from app import app          # your Flask app
from extensions import db
from sqlalchemy import text

with app.app_context():
    try:
        db.session.execute(text("DELETE FROM sensor_data"))
        db.session.commit()
        print("✅ sensor_data table cleared successfully")
    except Exception as e:
        db.session.rollback()
        print("❌ Error clearing sensor_data:", e)
