#!/usr/bin/env python3
"""
VOX Full Market Top 30% Scanner v1
Scans ALL 19,356 vox_grades for the best opportunities.
Filters: VOX grade >= 70, aggressive themes, not defensive.
Stores top 100 in top_opportunities table.
Alerts on grade 80+ (new entries only).

This is the "best of the best" scanner — no watchlist limits.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import sys
import psycopg2
from datetime import datetime, timedelta
from pathlib import Path

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"

# Load env
ENV_PATH = os.path.expanduser("~/.hermes/.env")
if os.path.exists(ENV_PATH):
    with open(ENV_PATH) as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k, v)

DB_HOST = os.environ.get("DB_HOST", "acela.proxy.rlwy.net")
DB_PORT = os.environ.get("DB_PORT", "35577")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_NAME = os.environ.get("DB_NAME", "railway")

# Defensive/boring tickers to exclude (user explicitly rejects these)
DEFENSIVE_TICKERS = {
    'PG', 'KO', 'VZ', 'JNJ', 'PEP', 'WMT', 'COST', 'HD', 'LOW', 'TGT',
    'SPG', 'FRT', 'O', 'VTR', 'WPC', 'NNN', 'ADC', 'STAG', 'EXR', 'PSA',
    'MKC', 'CPB', 'GIS', 'K', 'CAG', 'SJM', 'HSY', 'MDLZ', 'KHC', 'LW',
    'NEM', 'GOLD', 'AEM', 'WPM', 'FNV', 'RGLD', 'KGC', 'BVN', 'EGO', 'AGI',
    'STLD', 'NUE', 'MT', 'X', 'CLF', 'RS', 'SCHN', 'CMC', 'TMST', 'ASTL',
    'XLU', 'XLP', 'XLRE', 'VPU', 'VDC', 'VNQ', 'VNQI', 'VDE', 'VAW',
    'WEAT', 'CORN', 'SOYB', 'CANE', 'JO', 'BAL', 'NIB', 'SGG', 'LEAD',
    'PFE', 'MRK', 'ABBV', 'BMY', 'LLY', 'NVO', 'AZN', 'GSK', 'SNY', 'RHHBY',
    'T', 'TMUS', 'VZ', 'LUMN', 'FYBR', 'CCI', 'AMT', 'SBAC', 'EQIX', 'DLR'
}

# Aggressive themes to prioritize
AGGRESSIVE_SECTORS = {
    'quantum', 'ai', 'artificial intelligence', 'nuclear', 'smr', 'hydrogen',
    'crypto', 'bitcoin', 'blockchain', 'fintech', 'emerging markets',
    'biotech', 'gene editing', 'space', 'semiconductor', 'memory',
    'software', 'cloud', 'cybersecurity', 'gaming', 'metaverse',
    'electric vehicles', 'battery', 'lithium', 'solar', 'clean energy'
}


def get_conn():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER,
        password=DB_PASSWORD, dbname=DB_NAME, sslmode="require"
    )


def ensure_tables(conn):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS top_opportunities (
            id SERIAL PRIMARY KEY,
            ticker TEXT UNIQUE,
            vox_grade INTEGER,
            action TEXT,
            technical_score INTEGER,
            fundamental_score INTEGER,
            macro_score INTEGER,
            sector_score INTEGER,
            weather_score INTEGER,
            sentiment_score INTEGER,
            sector TEXT,
            is_aggressive BOOLEAN DEFAULT FALSE,
            is_defensive BOOLEAN DEFAULT FALSE,
            rank INTEGER,
            computed_at TIMESTAMP DEFAULT NOW(),
            alert_sent BOOLEAN DEFAULT FALSE
        )
    """)
    conn.commit()
    cur.close()


def get_sector(cur, ticker):
    """Get sector from sector_momentum or sp500_sector_leaders"""
    # Try sector_momentum first
    cur.execute("""
        SELECT sector FROM sector_momentum 
        WHERE %s = ANY(top_tickers) LIMIT 1
    """, (ticker,))
    row = cur.fetchone()
    if row:
        return row[0]
    
    # Try sp500_sector_leaders
    cur.execute("""
        SELECT sector FROM sp500_sector_leaders WHERE ticker = %s LIMIT 1
    """, (ticker,))
    row = cur.fetchone()
    if row:
        return row[0]
    
    return 'Unknown'


def classify_sector(sector):
    """Classify sector as aggressive or defensive"""
    if not sector:
        return False, False
    
    sector_lower = sector.lower()
    is_aggressive = any(theme in sector_lower for theme in AGGRESSIVE_SECTORS)
    
    # Defensive sectors
    defensive_keywords = {'utilities', 'consumer staples', 'reits', 'telecom', 
                          'healthcare', 'pharma', 'gold', 'materials', 'industrial'}
    is_defensive = any(kw in sector_lower for kw in defensive_keywords)
    
    return is_aggressive, is_defensive


def scan_top_opportunities(cur, top_n=100):
    """Scan all vox_grades for top opportunities"""
    cur.execute("""
        SELECT 
            v.ticker,
            v.vox_grade,
            v.action,
            v.technical_score,
            v.fundamental_score,
            v.macro_score,
            v.sector_score,
            v.weather_score,
            v.sentiment_score
        FROM vox_grades v
        WHERE v.vox_grade >= 65
          AND v.action IN ('BUY', 'STRONG_BUY', 'ACCUMULATE')
        ORDER BY v.vox_grade DESC, v.technical_score DESC
        LIMIT %s
    """, (top_n,))
    
    return cur.fetchall()


def store_opportunities(conn, opportunities):
    """Store top opportunities in DB with batched sector lookups"""
    cur = conn.cursor()
    
    # Clear old data (keep last 7 days for history)
    cur.execute("""
        DELETE FROM top_opportunities 
        WHERE computed_at < NOW() - INTERVAL '7 days'
    """)
    
    # Batch sector lookups: get all sectors at once
    tickers = [opp[0] for opp in opportunities]
    
    # Build sector map from ticker_sectors table (fastest)
    sector_map = {}
    cur.execute("""
        SELECT ticker, sector FROM ticker_sectors 
        WHERE ticker = ANY(%s)
    """, (tickers,))
    for row in cur.fetchall():
        sector_map[row[0]] = row[1]
    
    # Fallback: get remaining from sector_momentum top_tickers
    remaining = [t for t in tickers if t not in sector_map]
    if remaining:
        cur.execute("""
            SELECT sector, top_tickers FROM sector_momentum
            WHERE top_tickers && %s::text[]
        """, (remaining,))
        for row in cur.fetchall():
            for t in row[1]:
                if t in remaining and t not in sector_map:
                    sector_map[t] = row[0]
    
    # Insert new opportunities
    for rank, opp in enumerate(opportunities, 1):
        ticker, grade, action, tech, fund, macro, sector_s, weather, sentiment = opp
        
        sector = sector_map.get(ticker, 'Unknown')
        is_aggressive, is_defensive = classify_sector(sector)
        
        cur.execute("""
            INSERT INTO top_opportunities 
            (ticker, vox_grade, action, technical_score, fundamental_score, 
             macro_score, sector_score, weather_score, sentiment_score,
             sector, is_aggressive, is_defensive, rank, computed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (ticker) DO UPDATE SET
                vox_grade = EXCLUDED.vox_grade,
                action = EXCLUDED.action,
                technical_score = EXCLUDED.technical_score,
                fundamental_score = EXCLUDED.fundamental_score,
                macro_score = EXCLUDED.macro_score,
                sector_score = EXCLUDED.sector_score,
                weather_score = EXCLUDED.weather_score,
                sentiment_score = EXCLUDED.sentiment_score,
                sector = EXCLUDED.sector,
                is_aggressive = EXCLUDED.is_aggressive,
                is_defensive = EXCLUDED.is_defensive,
                rank = EXCLUDED.rank,
                computed_at = NOW()
        """, (ticker, grade, action, tech, fund, macro, sector_s, weather, sentiment,
              sector, is_aggressive, is_defensive, rank))
    
    conn.commit()
    cur.close()


def find_new_alerts(cur):
    """Find opportunities that hit 80+ for the first time today"""
    cur.execute("""
        SELECT ticker, vox_grade, action, sector, is_aggressive
        FROM top_opportunities
        WHERE vox_grade >= 80
          AND alert_sent = FALSE
          AND computed_at > NOW() - INTERVAL '24 hours'
        ORDER BY vox_grade DESC
    """)
    return cur.fetchall()


def main():
    conn = get_conn()
    ensure_tables(conn)
    cur = conn.cursor()
    
    # 1. Scan top 100 opportunities from ALL vox_grades
    print("🔍 Scanning full market for top opportunities...")
    opportunities = scan_top_opportunities(cur, top_n=100)
    print(f"  Found {len(opportunities)} stocks with grade >= 65")
    
    # 2. Store in DB
    store_opportunities(conn, opportunities)
    print(f"  Stored top {len(opportunities)} in top_opportunities table")
    
    # 3. Find aggressive opportunities
    aggressive = [o for o in opportunities if o[0] not in DEFENSIVE_TICKERS]
    print(f"  {len(aggressive)} after removing defensive tickers")
    
    # 4. Check for new alerts (grade 80+, not alerted before)
    new_alerts = find_new_alerts(cur)
    
    # 5. Build output
    print(f"\n🎯 **VOX TOP OPPORTUNITIES — {datetime.now().strftime('%a %b %d %H:%M')}**")
    print(f"Scanned: 19,356 tickers | Filtered: grade ≥ 65 + BUY/STRONG_BUY/ACCUMULATE")
    print(f"Top 100 stored. {len(aggressive)} aggressive plays.")
    
    if new_alerts:
        print(f"\n🚨 **{len(new_alerts)} NEW HIGH-CONVICTION ALERTS (80+)**")
        for alert in new_alerts[:5]:
            ticker, grade, action, sector, is_agg = alert
            agg_emoji = "🔥" if is_agg else ""
            print(f"  {agg_emoji} **{ticker}** — {action} | Grade: {grade} | Sector: {sector}")
        
        # Mark alerts as sent
        for alert in new_alerts:
            cur.execute("""
                UPDATE top_opportunities SET alert_sent = TRUE WHERE ticker = %s
            """, (alert[0],))
        conn.commit()
    
    # 6. Print top 15 aggressive opportunities (deduplicated)
    seen = set()
    print(f"\n**TOP 15 AGGRESSIVE PLAYS:**")
    print("-" * 60)
    count = 0
    for opp in aggressive:
        ticker = opp[0]
        if ticker in seen:
            continue
        seen.add(ticker)
        count += 1
        if count > 15:
            break
        grade, action, tech, fund, macro, sector_s, weather, sentiment = opp[1:]
        sector = get_sector(cur, ticker)
        is_agg, is_def = classify_sector(sector)
        agg_tag = " [AGGRESSIVE]" if is_agg else ""
        tech_str = f"{tech:2d}" if tech is not None else " N"
        print(f"{count:2d}. {ticker:6s} | Grade: {grade:2d} | {action:12s} | Tech: {tech_str}{agg_tag}")
    
    conn.close()
    
    # Return non-zero if new alerts found (triggers notification)
    return 1 if new_alerts else 0


if __name__ == "__main__":
    exit(main())
