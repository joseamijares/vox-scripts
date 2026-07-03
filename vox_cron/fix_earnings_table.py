#!/usr/bin/env python3
"""Fix earnings_calendar table - add missing columns."""

import psycopg2
import os

DB_HOST = os.environ.get("DB_HOST", "acela.proxy.rlwy.net")
DB_PORT = os.environ.get("DB_PORT", "35577")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
if not DB_PASSWORD or len(DB_PASSWORD) < 10:
    DB_PASSWORD = "hEJeas...mqAS"
DB_NAME = os.environ.get("DB_NAME", "railway")

print(f"Connecting to {DB_HOST}:{DB_PORT}...")
conn = psycopg2.connect(
    host=DB_HOST, port=DB_PORT, user=DB_USER,
    password=DB_PASSWORD, dbname=DB_NAME, sslmode="require",
)
cur = conn.cursor()

# Check columns
cur.execute("""
    SELECT column_name 
    FROM information_schema.columns 
    WHERE table_name = 'earnings_calendar'
""")
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

existing = {row[0] for row in cur.fetchall()}
print(f"Existing columns: {existing}")

# Add missing columns
columns_to_add = [
    ("importance", "VARCHAR(20)"),
    ("eps_estimate", "NUMERIC(10,2)"),
    ("revenue_estimate", "NUMERIC(15,2)"),
]

for col_name, col_type in columns_to_add:
    if col_name not in existing:
        print(f"Adding {col_name} {col_type}...")
        cur.execute(f"ALTER TABLE earnings_calendar ADD COLUMN {col_name} {col_type}")
        conn.commit()
        print(f"Done!")
    else:
        print(f"{col_name} already exists")

cur.close()
conn.close()
print("All fixes applied!")
