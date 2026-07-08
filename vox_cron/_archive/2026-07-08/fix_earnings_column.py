#!/usr/bin/env python3
"""Fix vox_earnings_tracker.py - add report_time column if missing."""

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

# Check if report_time column exists
cur.execute("""
    SELECT column_name 
    FROM information_schema.columns 
    WHERE table_name = 'earnings_calendar' AND column_name = 'report_time'
""")
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

exists = cur.fetchone()

if exists:
    print("report_time column already exists")
else:
    print("Adding report_time column to earnings_calendar...")
    cur.execute("ALTER TABLE earnings_calendar ADD COLUMN report_time VARCHAR(20)")
    conn.commit()
    print("Done!")

# Verify
cur.execute("SELECT COUNT(*) FROM earnings_calendar")
count = cur.fetchone()[0]
print(f"earnings_calendar has {count} rows")

cur.close()
conn.close()
