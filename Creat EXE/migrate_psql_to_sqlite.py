import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# ======================================================
# FIX IMPORT PATH (so models.py is found)
# ======================================================
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(BASE_DIR)

from models import db   # Flask-SQLAlchemy instance
Base = db.Model

# ======================================================
# DATABASE URLS
# ======================================================
POSTGRES_URI = "postgresql://postgres:1234@localhost:5433/iot"

SQLITE_DB_PATH = os.path.join(BASE_DIR, "data", "iot.db")
os.makedirs(os.path.dirname(SQLITE_DB_PATH), exist_ok=True)

SQLITE_URI = f"sqlite:///{SQLITE_DB_PATH}"

# ======================================================
# ENGINES
# ======================================================
pg_engine = create_engine(POSTGRES_URI)
sqlite_engine = create_engine(SQLITE_URI)

# ======================================================
# STEP 1: CREATE SQLITE DB + TABLES
# ======================================================
print("🆕 Creating SQLite database & tables...")
Base.metadata.create_all(bind=sqlite_engine)

# ======================================================
# STEP 2: COPY DATA
# ======================================================
PGSession = sessionmaker(bind=pg_engine)
SQLiteSession = sessionmaker(bind=sqlite_engine)

pg_session = PGSession()
sqlite_session = SQLiteSession()

for table in Base.metadata.sorted_tables:
    print(f"📦 Migrating table: {table.name}")

    rows = pg_session.execute(table.select()).fetchall()
    if rows:
        sqlite_session.execute(
            table.insert(),
            [dict(row._mapping) for row in rows]
        )

sqlite_session.commit()

pg_session.close()
sqlite_session.close()

print("✅ PostgreSQL → SQLite migration completed successfully")
print(f"📁 SQLite DB location: {SQLITE_DB_PATH}")
