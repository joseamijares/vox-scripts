#!/usr/bin/env python3
"""
VOX Watchlist Grader
Grades stocks we DON'T own but are watching
Runs silently - only alerts on grade 75+
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os, sys, psycopg2, json
from datetime import datetime
import json
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
from hermes_secrets import get_env

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"

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


# Default watchlist tickers (expandable)
WATCHLIST = [
    # X/Twitter alerts, trending, momentum
    'IONQ', 'SE', 'MCO', 'VEEV', 'NVO', 'BAC', 'HOOD', 'C', 'SPGI', 'TWST',
    'JPM', 'NUE', 'CP', 'OKTA', 'HUM', '0700.HK',
    # Sector plays
    'XLE', 'XLF', 'XLI', 'XLU', 'XLP', 'XLB', 'XLRE',
    # Commodity/weather
    'WEAT', 'CORN', 'SOYB', 'CANE',
    # Mexico
    'NAFTRAC', 'EWW',
    # Crypto
    'MSTR', 'RIOT', 'MARA', 'COIN',
    # Meme/momentum
    'GME', 'AMC', 'BB', 'PLTR', 'RBLX'
]

def main():
    pwd = get_env('PGPASSWORD', get_env('DB_PASSWORD', ''))
    conn = psycopg2.connect(
        host=get_env('DB_HOST', 'acela.proxy.rlwy.net'), port=get_env('DB_PORT', '35577'),
        user=get_env('DB_USER', 'postgres'), password=pwd,
        dbname=get_env('DB_NAME', 'railway'), sslmode='require',
    )
    cur = conn.cursor()
    
    # Ensure watchlist_grades table exists
    cur.execute("""
        CREATE TABLE IF NOT EXISTS watchlist_grades (
            ticker TEXT PRIMARY KEY,
            vox_grade INTEGER,
            technical_score INTEGER,
            fundamental_score INTEGER,
            macro_score INTEGER,
            sector_score INTEGER,
            weather_score INTEGER,
            sentiment_score INTEGER,
            graded_at TIMESTAMP DEFAULT NOW(),
            alert_triggered BOOLEAN DEFAULT FALSE
        )
    """)
    conn.commit()
    
    high_grade_alerts = []
    
    for ticker in WATCHLIST:
        # Check if already in portfolio
        cur.execute("SELECT 1 FROM broker_positions WHERE ticker = %s", (ticker,))
        if cur.fetchone():
            continue  # Skip if we own it
        
        # Check if we have a grade
        cur.execute("""
            SELECT vox_grade, technical_score, fundamental_score, macro_score,
                   sector_score, weather_score, sentiment_score
            FROM vox_grades WHERE ticker = %s
        """, (ticker,))
        
        grade_data = cur.fetchone()
        if not grade_data:
            continue
        
        g, t, f, m, s, w, se = grade_data
        
        # Store in watchlist_grades
        cur.execute("""
            INSERT INTO watchlist_grades (ticker, vox_grade, technical_score, fundamental_score,
                macro_score, sector_score, weather_score, sentiment_score, graded_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (ticker) DO UPDATE SET
                vox_grade = EXCLUDED.vox_grade,
                technical_score = EXCLUDED.technical_score,
                fundamental_score = EXCLUDED.fundamental_score,
                macro_score = EXCLUDED.macro_score,
                sector_score = EXCLUDED.sector_score,
                weather_score = EXCLUDED.weather_score,
                sentiment_score = EXCLUDED.sentiment_score,
                graded_at = NOW()
        """, (ticker, g, t, f, m, s, w, se))
        
        # Alert if grade 75+ and not already alerted
        if g >= 75:
            cur.execute("SELECT alert_triggered FROM watchlist_grades WHERE ticker = %s", (ticker,))
            row = cur.fetchone()
            if not row or not row[0]:
                high_grade_alerts.append({
                    'ticker': ticker,
                    'grade': g,
                    'technical': t,
                    'fundamental': f
                })
                cur.execute("""
                    UPDATE watchlist_grades SET alert_triggered = TRUE WHERE ticker = %s
                """, (ticker,))
    
    conn.commit()
    conn.close()
    
    # Only output if high-grade alerts found
    if high_grade_alerts:
        print("🚨 WATCHLIST ALERTS - Grade 75+ Detected:")
        for alert in high_grade_alerts:
            print(f"  {alert['ticker']}: Grade {alert['grade']} (Tech: {alert['technical']}, Fund: {alert['fundamental']})")
        return 1  # Non-zero exit to trigger notification
    
    return 0  # Silent success

if __name__ == '__main__':
    exit(main())
