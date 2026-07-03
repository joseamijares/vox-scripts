import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import psycopg2

DB_PASSWORD = os.environ.get('DB_PASSWORD', '')
conn = psycopg2.connect(
    host="acela.proxy.rlwy.net", port="35577", user="postgres",
    password=DB_PASSWORD, dbname="railway", sslmode="require",
)
cur = conn.cursor()
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'positions' ORDER BY ordinal_position")
for row in cur.fetchall():
    print(row[0])
conn.close()
