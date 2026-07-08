#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import psycopg2, os

DB_HOST = os.environ.get("DB_HOST", "acela.proxy.rlwy.net")
DB_PORT = os.environ.get("DB_PORT", "35577")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
if not DB_PASSWORD or len(DB_PASSWORD) < 10:
    DB_PASSWORD = "***"  # Hardcoded fallback
DB_NAME = os.environ.get("DB_NAME", "railway")

conn = psycopg2.connect(
    host=DB_HOST, port=DB_PORT, user=DB_USER,
    password=DB_PASSWORD, dbname=DB_NAME, sslmode="require"
)
cur = conn.cursor()

# Fix NULL live_value_usd from live_value
print('Fixing NULL live_value_usd...')
cur.execute("""
    UPDATE positions
    SET live_value_usd = live_value
    WHERE live_value_usd IS NULL
      AND live_value IS NOT NULL
""")
print(f'Updated {cur.rowcount} rows from live_value')

# Fix remaining NULL from live_price * shares
cur.execute("""
    UPDATE positions
    SET live_value = live_price * shares,
        live_value_usd = live_price * shares
    WHERE live_value_usd IS NULL
      AND live_price IS NOT NULL
      AND shares IS NOT NULL
""")
print(f'Updated {cur.rowcount} rows from price*shares')

conn.commit()

# Verify
cur.execute("SELECT COUNT(*) FROM positions WHERE live_value_usd IS NULL")
remaining = cur.fetchone()[0]
print(f'Remaining NULL: {remaining}')

conn.close()
