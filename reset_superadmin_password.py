import sqlite3
from werkzeug.security import generate_password_hash
from datetime import datetime

DB_PATH = r"C:\Users\Dell Lattitude 3450\Desktop\IoT Management\data\iot.db"

USERNAME = "superadmin"
EMAIL = "superadmin@example.com"
PASSWORD = "Admin@123"
ROLE = "super_admin"
ACTIVE_STATUS = 1  # 1 = active, 0 = inactive

def reset_superadmin():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    password_hash = generate_password_hash(PASSWORD)
    now = datetime.now().isoformat(sep=" ", timespec="seconds")

    # 🔹 Check if superadmin exists
    cursor.execute(
        "SELECT id FROM users WHERE username = ?",
        (USERNAME,)
    )
    row = cursor.fetchone()

    if row:
        user_id = row[0]

        # 🔁 Update EVERYTHING
        cursor.execute("""
            UPDATE users
            SET
                username = ?,
                email = ?,
                password_hash = ?,
                role = ?,
                active_status = ?,
                parent_admin_id = NULL,
                company_id = NULL
            WHERE id = ?
        """, (
            USERNAME,
            EMAIL,
            password_hash,
            ROLE,
            ACTIVE_STATUS,
            user_id
        ))

        print("🔁 Existing superadmin updated")

    else:
        # ➕ Create fresh superadmin
        cursor.execute("""
            INSERT INTO users (
                username,
                email,
                password_hash,
                role,
                active_status,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            USERNAME,
            EMAIL,
            password_hash,
            ROLE,
            ACTIVE_STATUS,
            now
        ))

        print("➕ New superadmin created")

    conn.commit()
    conn.close()

    print("=" * 60)
    print("✅ SUPERADMIN RESET COMPLETE (SQLite)")
    print("=" * 60)
    print(f"Username : {USERNAME}")
    print(f"Password : {PASSWORD}")
    print(f"Email    : {EMAIL}")
    print(f"Role     : {ROLE}")
    print(f"Active   : YES")
    print("=" * 60)

if __name__ == "__main__":
    reset_superadmin()
