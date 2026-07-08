#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import psycopg2, os

DB_PASSWORD = os.environ.get('DB_PASSWORD', '')
if not DB_PASSWORD or len(DB_PASSWORD) < 10:
    DB_PASSWORD = '***'

conn = psycopg2.connect(
    host='acela.proxy.rlwy.net', port='35577', user='postgres',
    password=DB_PASSWORD, dbname='railway', sslmode='require'
)
cur = conn.cursor()

# Check rows
cur.execute("SELECT COUNT(*) FROM top_opportunities")
print('Rows:', cur.fetchone()[0])

# Check constraints
cur.execute("""
    SELECT constraint_name FROM information_schema.table_constraints
    WHERE table_name = 'top_opportunities' AND constraint_type = 'UNIQUE'
""")
print('Unique constraints:', [r[0] for r in cur.fetchall()])

conn.close()
