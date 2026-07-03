#!/usr/bin/env python3
"""
VOX Liquid Universe Builder — Fast Batch Version
Builds top 5,000 liquid tickers from 19,356 vox_grades.
Uses batch queries + in-memory scoring for speed.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import psycopg2
from datetime import datetime

ENV_PATH = os.path.expanduser("~/.hermes/.env")
if os.path.exists(ENV_PATH):
    with open(ENV_PATH) as f:
        for line in f:
            if "=" in line and not line.startswith("#") and "DB_PASSWORD" in line:
                k, v = line.strip().split("=", 1)
                os.environ[k] = v

DB_PASSWORD = os.environ.get("DB_PASSWORD", "")

def get_conn():
    return psycopg2.connect(
        host="acela.proxy.rlwy.net", port=35577, database="railway",
        user="postgres", password=DB_PASSWORD, sslmode="require"
    )

def main():
    conn = get_conn()
    cur = conn.cursor()
    
    print(f"🔄 VOX Liquid Universe — {datetime.now().strftime('%a %b %d %H:%M')}")
    
    # Ensure table
    cur.execute("""
        DROP TABLE IF EXISTS liquid_universe;
        CREATE TABLE liquid_universe (
            ticker TEXT PRIMARY KEY,
            vox_grade INTEGER,
            action TEXT,
            technical_score INTEGER,
            fundamental_score INTEGER,
            macro_score INTEGER,
            sector_score INTEGER,
            weather_score INTEGER,
            sentiment_score INTEGER,
            composite_score NUMERIC,
            is_new_entry BOOLEAN DEFAULT FALSE,
            is_removed BOOLEAN DEFAULT FALSE,
            first_seen TIMESTAMP DEFAULT NOW(),
            last_updated TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()
    
    # Get all vox_grades in ONE query (fast)
    print("📥 Loading 19,356 grades...")
    cur.execute("""
        SELECT 
            ticker, vox_grade, action,
            COALESCE(technical_score,0), COALESCE(fundamental_score,0),
            COALESCE(macro_score,0), COALESCE(sector_score,0),
            COALESCE(weather_score,0), COALESCE(sentiment_score,0)
        FROM vox_grades
        WHERE ticker IS NOT NULL
    """)
    rows = cur.fetchall()
    print(f"  Loaded {len(rows)} rows")
    
    # Score in memory
    scored = []
    for row in rows:
        ticker, grade, action, tech, fund, macro, sector, weather, sentiment = row
        # Composite = grade * 0.5 + avg_layer_score * 0.5
        layer_scores = [tech, fund, macro, sector, weather, sentiment]
        valid = [s for s in layer_scores if s > 0]
        avg_layer = sum(valid) / len(valid) if valid else 0
        composite = (grade * 0.5) + (avg_layer * 0.5) if grade else avg_layer
        
        scored.append({
            'ticker': ticker, 'grade': grade or 0, 'action': action or 'UNKNOWN',
            'tech': tech, 'fund': fund, 'macro': macro, 'sector': sector,
            'weather': weather, 'sentiment': sentiment,
            'composite': composite
        })
    
    # Sort by composite, take top 5,000
    scored.sort(key=lambda x: x['composite'], reverse=True)
    top_5000 = scored[:5000]
    
    print(f"  Top 5,000 selected (composite >= {top_5000[-1]['composite']:.1f})")
    
    # Get existing for comparison
    cur.execute("SELECT ticker FROM liquid_universe WHERE is_removed = FALSE")
    existing = {r[0] for r in cur.fetchall()}
    
    # Batch upsert
    print("💾 Storing in DB...")
    new_count = 0
    for stock in top_5000:
        is_new = stock['ticker'] not in existing
        if is_new:
            new_count += 1
        
        cur.execute("""
            INSERT INTO liquid_universe 
            (ticker, vox_grade, action, technical_score, fundamental_score, macro_score,
             sector_score, weather_score, sentiment_score, composite_score, is_new_entry, is_removed, last_updated)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE, NOW())
            ON CONFLICT (ticker) DO UPDATE SET
                vox_grade = EXCLUDED.vox_grade, action = EXCLUDED.action,
                technical_score = EXCLUDED.technical_score, fundamental_score = EXCLUDED.fundamental_score,
                macro_score = EXCLUDED.macro_score, sector_score = EXCLUDED.sector_score,
                weather_score = EXCLUDED.weather_score, sentiment_score = EXCLUDED.sentiment_score,
                composite_score = EXCLUDED.composite_score, is_new_entry = FALSE,
                is_removed = FALSE, last_updated = NOW()
        """, (stock['ticker'], stock['grade'], stock['action'], stock['tech'], stock['fund'],
              stock['macro'], stock['sector'], stock['weather'], stock['sentiment'],
              stock['composite'], is_new))
    
    # Mark removed
    current = {s['ticker'] for s in top_5000}
    removed = existing - current
    for r in removed:
        cur.execute("UPDATE liquid_universe SET is_removed = TRUE, last_updated = NOW() WHERE ticker = %s", (r,))
    
    conn.commit()
    
    # Stats
    high_grade = len([s for s in top_5000 if s['grade'] >= 70])
    buy_strong = len([s for s in top_5000 if s['action'] in ('BUY', 'STRONG_BUY')])
    
    print(f"\n📊 Results:")
    print(f"  New entries: {new_count}")
    print(f"  Removed: {len(removed)}")
    print(f"  Grade 70+: {high_grade}")
    print(f"  BUY/STRONG_BUY: {buy_strong}")
    
    print(f"\n**TOP 20:**")
    for i, s in enumerate(top_5000[:20], 1):
        print(f"{i:2d}. {s['ticker']:6s} | Grade: {s['grade']:2d} | Comp: {s['composite']:5.1f} | {s['action']}")
    
    cur.close()
    conn.close()
    
    return 1 if new_count > 10 or len(removed) > 10 else 0

if __name__ == "__main__":
    exit(main())
