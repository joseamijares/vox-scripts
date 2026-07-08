#!/usr/bin/env python3
"""
VOX Unified Grades JSON Sync
Syncs vox_unified_grades.json with PostgreSQL unified_grades table.
Run after vox_unified_rebuilder to keep JSON file fresh.

Pattern 24 Fix: Prevents stale JSON file from causing data discrepancies.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import json
import psycopg2
from pathlib import Path
from datetime import datetime

# Database connection (same pattern as other vox scripts)
DB_HOST = os.environ.get("DB_HOST", "acela.proxy.rlwy.net")
DB_PORT = os.environ.get("DB_PORT", "35577")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
if not DB_PASSWORD or len(DB_PASSWORD) < 10:
    DB_PASSWORD = "***"  # Hardcoded fallback
DB_NAME = os.environ.get("DB_NAME", "railway")

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"
JSON_PATH = SCRIPT_DIR / "vox_unified_grades.json"


def connect():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER,
        password=DB_PASSWORD, dbname=DB_NAME, sslmode="require",
    )


def sync_json():
    """Sync unified_grades from PostgreSQL to JSON file"""
    conn = connect()
    cur = conn.cursor()
    
    # Get all unified grades
    cur.execute("""
        SELECT 
            ticker, unified_grade, action, vox_grade, sp500_grade,
            trade_grade, tech_score, contradiction, computed_at, vox_source
        FROM unified_grades
        ORDER BY unified_grade DESC
    """)
    
    grades = {}
    for row in cur.fetchall():
        (ticker, unified, action, vox, sp500, trade, tech, 
         contradiction, computed, vox_source) = row
        
        grades[ticker] = {
            "grade": float(unified) if unified is not None else 0,
            "action": action or "HOLD",
            "vox_grade": float(vox) if vox is not None else 0,
            "sp500_grade": float(sp500) if sp500 is not None else 0,
            "trade_grade": float(trade) if trade is not None else 0,
            "technical_score": float(tech) if tech is not None else 0,
            "contradiction": contradiction,
            "last_updated": computed.isoformat() if computed else "",
            "vox_source": vox_source or "",
        }
    
    # Build JSON structure
    data = {
        "grades": grades,
        "metadata": {
            "count": len(grades),
            "generated_at": datetime.now().isoformat(),
            "source": "unified_grades PostgreSQL table",
            "sync_version": "1.0",
        }
    }
    
    # Write to JSON file
    with open(JSON_PATH, 'w') as f:
        json.dump(data, f, indent=2, default=str)
    
    cur.close()
    conn.close()
    
    print(f"✅ Synced {len(grades)} grades to {JSON_PATH}")
    print(f"   Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return len(grades)


def main():
    print(f"VOX Unified Grades JSON Sync — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 60)
    
    count = sync_json()
    
    print("-" * 60)
    print(f"Done! {count} grades synced.")
    return 0


if __name__ == "__main__":
    exit(main())
