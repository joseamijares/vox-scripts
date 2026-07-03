#!/usr/bin/env python3
"""
VOX Unified Grades JSON Sync
Regenerates vox_unified_grades.json from the live PostgreSQL database.
Run this after vox_unified_rebuilder to keep the JSON file in sync.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import json
import psycopg2
from pathlib import Path

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"
JSON_PATH = SCRIPT_DIR / "vox_unified_grades.json"

def sync_json():
    # Load DB password from env
    pwd = os.environ.get('PGPASSWORD', '')
    if not pwd:
        with open(Path.home() / ".hermes" / ".env") as f:
            for line in f:
                if line.startswith('PGPASSWORD='):
                    pwd = line.strip().split('=', 1)[1]
                    break
    
    conn = psycopg2.connect(
        host='acela.proxy.rlwy.net', port=35577,
        database='railway', user='postgres', password=pwd
    )
    cur = conn.cursor()
    
    # Get all unified grades
    cur.execute('''
        SELECT ticker, unified_grade, action, vox_grade, sp500_grade, trade_grade, 
               tech_score, contradiction, computed_at
        FROM unified_grades
        ORDER BY unified_grade DESC
    ''')
    
    grades = {}
    for row in cur.fetchall():
        ticker, unified, action, vox, sp500, trade, tech, contradiction, computed = row
        grades[ticker] = {
            "grade": float(unified) if unified else 0,
            "action": action or "HOLD",
            "vox_grade": float(vox) if vox else 0,
            "sp500_grade": float(sp500) if sp500 else 0,
            "trade_grade": float(trade) if trade else 0,
            "technical_score": float(tech) if tech else 0,
            "contradiction": contradiction,
            "last_updated": computed.isoformat() if computed else ""
        }
    
    conn.close()
    
    # Write JSON
    data = {
        "grades": grades,
        "metadata": {
            "count": len(grades),
            "generated_at": datetime.now().isoformat(),
            "source": "unified_grades PostgreSQL table"
        }
    }
    
    with open(JSON_PATH, 'w') as f:
        json.dump(data, f, indent=2, default=str)
    
    print(f"Synced {len(grades)} grades to {JSON_PATH}")
    return True

if __name__ == '__main__':
    from datetime import datetime
    sync_json()
