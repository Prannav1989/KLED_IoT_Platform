import sqlite3
import os

# Absolute path to your SQLite database
DB_PATH = r"C:\Users\Dell Lattitude 3450\Desktop\IoT Management - Copy\data\iot.db"

def show_table_structures(db_path):
    if not os.path.exists(db_path):
        print(f"❌ Database not found at: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get all table names
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table'
        ORDER BY name;
    """)
    tables = cursor.fetchall()

    if not tables:
        print("⚠️ No tables found in the database.")
        return

    print(f"\n📦 Database: {db_path}")
    print("=" * 80)

    for (table_name,) in tables:
        print(f"\n📋 Table: {table_name}")
        print("-" * 80)

        cursor.execute(f"PRAGMA table_info({table_name});")
        columns = cursor.fetchall()

        print(f"{'CID':<5}{'Column':<25}{'Type':<20}{'NOT NULL':<10}{'Default':<15}{'PK'}")
        print("-" * 80)

        for col in columns:
            cid, name, col_type, notnull, default, pk = col
            print(
                f"{cid:<5}"
                f"{name:<25}"
                f"{col_type:<20}"
                f"{'YES' if notnull else 'NO':<10}"
                f"{str(default):<15}"
                f"{pk}"
            )

    conn.close()
    print("\n✅ Done")

if __name__ == "__main__":
    show_table_structures(DB_PATH)
