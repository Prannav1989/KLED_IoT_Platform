import sqlite3
import psycopg2

# ---------- CONFIGURE THESE ----------

# Path to your SQLite DB
SQLITE_DB_PATH = r"C:\Users\Dell Lattitude 3450\Desktop\IoT Management\instance\iot_dashboard.db"  # <-- CHANGE THIS

# PostgreSQL connection details
PG_DB_NAME = "iot"
PG_USER = "postgres"
PG_PASSWORD = "1234"
PG_HOST = "localhost"
PG_PORT = 5433

# Tables to migrate (sqlite_sequence is skipped)
TABLES_TO_MIGRATE = [
    "users",
    "sensor_data",
    "parameters",
    "mqtt_configs",
    "mqtt_messages",
    "devices",
    "alert_rule",
    "audit_logs",
    "companies",
    "dashboards",
    "user_dashboards",
    "navigation_settings",
    "report_permission",
    "navigation_permissions",
    "user_devices",
    "dashboard_sensors",
    "sensors",
    "support_ticket",
]

# ---------- MIGRATION LOGIC ----------

def migrate_table(sqlite_conn, pg_conn, table_name):
    sqlite_cur = sqlite_conn.cursor()
    pg_cur = pg_conn.cursor()

    print(f"\nMigrating table: {table_name}")

    # Fetch all rows from SQLite table
    sqlite_cur.execute(f"SELECT * FROM {table_name}")
    rows = sqlite_cur.fetchall()

    if not rows:
        print(f"  -> No rows found in {table_name}, skipping.")
        return

    # Get column names from SQLite
    col_names = [desc[0] for desc in sqlite_cur.description]
    col_list_str = ", ".join(col_names)

    # Prepare parameter placeholders for PostgreSQL
    placeholders = ", ".join(["%s"] * len(col_names))

    insert_query = f"""
        INSERT INTO {table_name} ({col_list_str})
        VALUES ({placeholders})
    """

    # Insert row by row into PostgreSQL
    inserted = 0
    for row in rows:
        try:
            pg_cur.execute(insert_query, row)
            inserted += 1
        except Exception as e:
            print(f"  !! Error inserting row in {table_name}: {e}")
            pg_conn.rollback()
        else:
            # Don't commit every row to avoid slowness, commit per table instead
            pass

    pg_conn.commit()
    print(f"  -> Inserted {inserted} rows into {table_name}")


def main():
    # Connect to SQLite
    print("Connecting to SQLite...")
    sqlite_conn = sqlite3.connect(SQLITE_DB_PATH)

    # Connect to PostgreSQL
    print("Connecting to PostgreSQL...")
    pg_conn = psycopg2.connect(
        dbname=PG_DB_NAME,
        user=PG_USER,
        password=PG_PASSWORD,
        host=PG_HOST,
        port=PG_PORT,
    )

    try:
        for table in TABLES_TO_MIGRATE:
            migrate_table(sqlite_conn, pg_conn, table)

        print("\n✅ Migration completed successfully!")

    finally:
        sqlite_conn.close()
        pg_conn.close()
        print("Connections closed.")


if __name__ == "__main__":
    main()
