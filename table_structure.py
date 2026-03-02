import psycopg2

PG_DB_NAME = "iot"
PG_USER = "postgres"
PG_PASSWORD = "1234"
PG_HOST = "localhost"
PG_PORT = 5433

def show_database_details():
    try:
        conn = psycopg2.connect(
            dbname=PG_DB_NAME,
            user=PG_USER,
            password=PG_PASSWORD,
            host=PG_HOST,
            port=PG_PORT
        )
        cursor = conn.cursor()

        # Get all table names
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        tables = cursor.fetchall()

        print("\n==================== TABLES IN DATABASE ====================\n")
        for t in tables:
            table_name = t[0]
            print(f"\n===== TABLE: {table_name} =====")

            # ---------- Get column names only ----------
            cursor.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns
                WHERE table_name = %s
                ORDER BY ordinal_position;
            """, (table_name,))
            columns = cursor.fetchall()

            print("\nColumns:")
            for col in columns:
                print(f" - {col[0]}  ({col[1]})")

            print("\n-----------------------------------------------------------")

        cursor.close()
        conn.close()

    except Exception as e:
        print("Error:", e)


if __name__ == "__main__":
    show_database_details()
