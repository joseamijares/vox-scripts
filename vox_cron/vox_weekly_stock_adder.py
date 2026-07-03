#!/usr/bin/env python3
"""
VOX Weekly Stock Adder
Adds new high-potential tickers to the vox_grades table weekly.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import psycopg2
from datetime import datetime

DB_PASSWORD = ''
ENV_PATH = os.path.expanduser("~/.hermes/.env")
if os.path.exists(ENV_PATH):
    with open(ENV_PATH) as f:
        for line in f:
            if line.startswith("DB_PASSWORD="):
                DB_PASSWORD = line.strip().split("=", 1)[1]
                break

def get_conn():
    return psycopg2.connect(
        host="acela.proxy.rlwy.net", port=35577, database="railway",
        user="postgres", password=DB_PASSWORD, sslmode="require"
    )

# New tickers to add this week (expandable)
WEEKLY_NEW_TICKERS = [
    # Add your weekly discoveries here
    # 'RGTI', 'QBTS', 'SMR', 'CEG', 'PLUG', 'MELI', 'NU', 'ANET', 'RKLB', 'ASTS'
]

def discover_new_tickers(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT ticker FROM liquid_universe 
        WHERE ticker NOT IN (SELECT ticker FROM vox_grades)
        AND is_removed = FALSE
        LIMIT 50
    """)
    missing = [r[0] for r in cur.fetchall()]
    cur.close()
    return list(set(missing + WEEKLY_NEW_TICKERS))

def add_ticker(conn, ticker):
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM vox_grades WHERE ticker = %s", (ticker,))
    if cur.fetchone():
        cur.close()
        return False, "exists"
    cur.execute("""
        INSERT INTO vox_grades 
        (ticker, vox_grade, action, technical_score, fundamental_score, macro_score,
         sector_score, weather_score, sentiment_score, created_at, updated_at)
        VALUES (%s, 50, 'HOLD', 50, 50, 50, 50, 50, 50, NOW(), NOW())
    """, (ticker,))
    conn.commit()
    cur.close()
    return True, "added"

def main():
    conn = get_conn()
    print(f"🆕 VOX Weekly Stock Adder — {datetime.now().strftime('%a %b %d %H:%M')}")
    new_tickers = discover_new_tickers(conn)
    print(f"Discovered {len(new_tickers)} potential tickers")
    added = 0
    for t in new_tickers:
        ok, msg = add_ticker(conn, t)
        if ok:
            added += 1
            print(f"  ✅ {t}")
        else:
            print(f"  ⚠️  {t} — {msg}")
    print(f"\n📊 Added {added} new tickers")
    conn.close()
    return 1 if added > 0 else 0

if __name__ == "__main__":
    exit(main())
