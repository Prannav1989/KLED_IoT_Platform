import sqlite3
import os

# Path to your database
db_path = r"C:\Users\Dell Lattitude 3450\Desktop\IoT Management\instance\iot_dashboard.db"

if not os.path.exists(db_path):
    print(f"❌ Database not found at: {db_path}")
else:
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        print("✅ Connected to database.")

        # 1️⃣ Drop the sensors table if it exists
        cursor.execute("DROP TABLE IF EXISTS sensors;")
        print("🗑️ Dropped table: sensors")

        # 2️⃣ Check if dashboard_sensors exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='dashboard_sensors';")
        if cursor.fetchone():
            print("🔍 Found table: dashboard_sensors")

            # Get the existing data (if needed for backup)
            cursor.execute("SELECT * FROM dashboard_sensors;")
            existing_data = cursor.fetchall()
            print(f"📦 Backed up {len(existing_data)} existing records from dashboard_sensors.")

            # 3️⃣ Rename old table for safety
            cursor.execute("ALTER TABLE dashboard_sensors RENAME TO dashboard_sensors_old;")

            # 4️⃣ Create the new dashboard_sensors table with device_id instead of sensor_id
            cursor.execute("""
                CREATE TABLE dashboard_sensors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dashboard_id INTEGER NOT NULL,
                    device_id INTEGER NOT NULL,
                    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (dashboard_id) REFERENCES dashboards(id),
                    FOREIGN KEY (device_id) REFERENCES devices(id)
                );
            """)
            print("✅ Created new dashboard_sensors table with device_id column.")

            # 5️⃣ Optionally migrate old data (if old sensor_id corresponds to device_id)
            # ⚠️ Only do this if you are sure sensor_id == device_id mapping exists
            try:
                cursor.execute("""
                    INSERT INTO dashboard_sensors (dashboard_id, device_id, added_at)
                    SELECT dashboard_id, sensor_id, added_at
                    FROM dashboard_sensors_old;
                """)
                print("🔁 Migrated existing data (sensor_id → device_id).")
            except Exception as e:
                print(f"⚠️ Could not migrate old data: {e}")

            # 6️⃣ Drop old backup table
            cursor.execute("DROP TABLE dashboard_sensors_old;")
            print("🧹 Removed old dashboard_sensors_old table.")

        else:
            print("⚠️ dashboard_sensors table not found. Skipping modification.")

        # Commit and close
        conn.commit()
        conn.close()
        print("🎯 All operations completed successfully.")

    except Exception as e:
        print(f"❌ Error: {e}")
