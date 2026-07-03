#!/usr/bin/env python3
"""
VOX Pattern Scanner
Scans for technical patterns, momentum shifts, volume anomalies
Runs silently - only alerts on high conviction (80+)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os, psycopg2, json
from datetime import datetime
import json
from pathlib import Path

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR / "vox_cron"))
from deepseek_review import deepseek_review

def load_unified_grades():
    """Load unified grades from single source of truth"""
    unified_path = SCRIPT_DIR / "vox_unified_grades.json"
    if not unified_path.exists():
        return {}
    with open(unified_path) as f:
        return json.load(f)

def get_unified_grade(ticker, unified_grades):
    """Get grade from unified source"""
    if ticker in unified_grades.get("grades", {}):
        return unified_grades["grades"][ticker].get("grade", 0)
    return 0


def main():
    # Use PGPASSWORD from environment, fallback to direct value for cron jobs
    pwd = os.environ.get('PGPASSWORD', os.environ.get('DB_PASSWORD', ''))
    conn = psycopg2.connect(
        host='acela.proxy.rlwy.net', port=35577,
        database='railway', user='postgres', password=pwd
    )
    cur = conn.cursor()
    
    # Ensure pattern_alerts table exists
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pattern_alerts (
            id SERIAL PRIMARY KEY,
            ticker TEXT,
            pattern_type TEXT,
            conviction INTEGER,
            direction TEXT,
            detected_at TIMESTAMP DEFAULT NOW(),
            alerted BOOLEAN DEFAULT FALSE
        )
    """)
    conn.commit()
    
    # Scan portfolio positions for pattern opportunities
    cur.execute("""
        SELECT p.ticker, p.grade, p.brokers, p.live_value_usd,
               v.technical_score, v.fundamental_score, v.macro_score
        FROM positions p
        LEFT JOIN vox_grades v ON p.ticker = v.ticker
        WHERE p.grade >= 60
    """)
    
    positions = cur.fetchall()
    high_conviction_patterns = []
    
    for pos in positions:
        ticker, grade, broker, value, tech, fund, macro = pos
        
        # Simple pattern detection based on grade + technical score
        if tech and tech >= 85 and grade >= 65:
            pattern = 'MOMENTUM_BREAKOUT'
            conviction = min(100, int((tech + grade) / 2))
            direction = 'BULLISH'
            
            if conviction >= 80:
                high_conviction_patterns.append({
                    'ticker': ticker,
                    'pattern': pattern,
                    'conviction': conviction,
                    'direction': direction,
                    'broker': broker,
                    'value': value
                })
    
    # DeepSeek second-layer review
    reviewed = deepseek_review(high_conviction_patterns, "Pattern scanner momentum breakouts (grade >= 65, technical >= 85, conviction >= 80)")
    approved_tickers = {p['ticker'] for p in reviewed}
    
    for p in reviewed:
        cur.execute("""
            INSERT INTO pattern_alerts (ticker, pattern_type, conviction, direction)
            VALUES (%s, %s, %s, %s)
        """, (p['ticker'], p['pattern'], p['conviction'], p['direction']))
    
    # Scan for sector rotation
    cur.execute("""
        SELECT sector, AVG(grade) as avg_grade, COUNT(*) as count
        FROM positions
        WHERE sector IS NOT NULL
        GROUP BY sector
        ORDER BY avg_grade DESC
    """)
    
    sectors = cur.fetchall()
    
    conn.commit()
    conn.close()
    
    # Only output if high conviction patterns found
    if reviewed:
        print("🚨 PATTERN ALERTS - High Conviction (80+), DeepSeek approved:")
        for p in reviewed:
            print(f"  {p['ticker']} ({p['broker']}): {p['pattern']} | {p['direction']} | Conviction: {p['conviction']}")
    else:
        print("✅ No high-conviction patterns detected.")
    
    return 1 if reviewed else 0

if __name__ == '__main__':
    exit(main())
