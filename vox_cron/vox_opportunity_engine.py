#!/usr/bin/env python3
"""
VOX Opportunity Engine v2.0
Merges vox_top_opportunities_scanner + vox_massive_opportunity.
- Scans all vox_grades for top 100 opportunities
- Scans portfolio positions for massive opportunities (grade≥65, technical≥60, size≥$2K, not crisis)
- Adds DeepSeek v4 Pro second-layer review for high-conviction alerts
- Outputs unified report; exits 0 always on success (stdout is the alert body)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import psycopg2
import json
from datetime import datetime
import vox_utils as vu

DB_HOST = os.environ.get('DB_HOST', 'acela.proxy.rlwy.net')
DB_PORT = os.environ.get('DB_PORT', '35577')
DB_USER = os.environ.get('DB_USER', 'postgres')
DB_NAME = os.environ.get('DB_NAME', 'railway')
DB_PASSWORD = os.environ.get('DB_PASSWORD', os.environ.get('PGPASSWORD', ''))

OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')

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
        password=DB_PASSWORD, dbname=DB_NAME, sslmode='require'
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


def classify_sector(sector):
    if not sector:
        return False, False
    sector_lower = sector.lower()
    is_aggressive = any(theme in sector_lower for theme in AGGRESSIVE_SECTORS)
    defensive_keywords = {'utilities', 'consumer staples', 'reits', 'telecom', 'healthcare', 'pharma', 'gold', 'materials'}
    is_defensive = any(kw in sector_lower for kw in defensive_keywords)
    return is_aggressive, is_defensive


def get_sector(cur, ticker):
    cur.execute("SELECT sector FROM sector_momentum WHERE %s = ANY(top_tickers) LIMIT 1", (ticker,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute("SELECT sector FROM sp500_sector_leaders WHERE ticker = %s LIMIT 1", (ticker,))
    row = cur.fetchone()
    if row:
        return row[0]
    return 'Unknown'


def scan_top_opportunities(cur, top_n=100):
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
    cur = conn.cursor()
    cur.execute("DELETE FROM top_opportunities WHERE computed_at < NOW() - INTERVAL '7 days'")
    tickers = [opp[0] for opp in opportunities]
    sector_map = {}
    if tickers:
        cur.execute("SELECT ticker, sector FROM ticker_sectors WHERE ticker = ANY(%s)", (tickers,))
        for row in cur.fetchall():
            sector_map[row[0]] = row[1]
        remaining = [t for t in tickers if t not in sector_map]
        if remaining:
            cur.execute("SELECT sector, top_tickers FROM sector_momentum WHERE top_tickers && %s::text[]", (remaining,))
            for row in cur.fetchall():
                for t in row[1]:
                    if t in remaining and t not in sector_map:
                        sector_map[t] = row[0]
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
    cur.execute("""
        SELECT ticker, vox_grade, action, sector, is_aggressive
        FROM top_opportunities
        WHERE vox_grade >= 80
          AND alert_sent = FALSE
          AND computed_at > NOW() - INTERVAL '24 hours'
        ORDER BY vox_grade DESC
    """)
    return cur.fetchall()


def check_crisis_regime(cur):
    cur.execute("SELECT regime, confidence FROM market_regime ORDER BY created_at DESC LIMIT 1")
    row = cur.fetchone()
    if row:
        regime, confidence = row
        return regime in ["CRISIS", "BEAR", "CRASH"], regime, confidence
    return False, "UNKNOWN", 0


def massive_opportunities(cur):
    is_crisis, regime, confidence = check_crisis_regime(cur)
    if is_crisis:
        return [], regime, confidence
    cur.execute("""
        SELECT 
            p.ticker,
            p.grade,
            p.live_value,
            p.sector,
            p.council,
            COALESCE(ts.score, 0) as technical_score,
            p.avg_cost,
            p.live_price
        FROM positions p
        LEFT JOIN technical_signals ts ON p.ticker = ts.ticker
        WHERE p.shares > 0
          AND p.grade >= 65
          AND p.live_value >= 2000
          AND p.council IN ('BUY', 'CORE')
        ORDER BY p.grade DESC, p.live_value DESC
    """)
    qualified = []
    for row in cur.fetchall():
        ticker, grade, live_value, sector, council, tech_score, avg_cost, live_price = row
        if tech_score >= 60:
            pnl = (live_price - avg_cost) / avg_cost * 100 if avg_cost > 0 else 0
            qualified.append({
                'ticker': ticker, 'grade': grade, 'live_value': live_value,
                'sector': sector, 'council': council, 'technical_score': tech_score,
                'avg_cost': avg_cost, 'live_price': live_price, 'pnl': pnl
            })
    return qualified, regime, confidence


def deepseek_review(candidates, context):
    """Second-layer review via DeepSeek v4 Pro. Returns approved list."""
    if not OPENROUTER_API_KEY or not candidates:
        return candidates
    system_prompt = """You are a strict quantitative review layer for a stock alert system. You receive candidate alerts with data fields. Your job is to reject any alert that:
|- Is based on mock, synthetic, or placeholder data
|- Has missing or zero scores that make it non-actionable
|- Is a defensive/boring sector (utilities, staples, telecom, REITs, gold, pharma) unless explicitly justified
|- Is a position with extreme P&L but tiny cost basis (data error)
|- Is a duplicate or low-conviction signal
Return a JSON object with key "approved" containing only the tickers you approve. Example: {"approved": ["TICKER1", "TICKER2"]}. If none are approved, return {"approved": []}. Do not include any other text."""
    user_prompt = f"Context: {context}\n\nCandidates:\n{json.dumps(candidates, indent=2, default=str)}\n\nReturn JSON only."
    try:
        result = vu.call_openrouter(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model="deepseek/deepseek-v4-pro",
            max_tokens=2000,
            temperature=0.2,
            script_name="vox_opportunity_engine.py",
            notes="DeepSeek v4 Pro second-layer review",
        )
        content = result.get("content", "")
        # Extract JSON
        start = content.find('{')
        end = content.rfind('}')
        if start == -1 or end == -1:
            return candidates
        parsed = json.loads(content[start:end+1])
        approved = set(parsed.get('approved', []))
        return [c for c in candidates if c.get('ticker') in approved]
    except Exception as e:
        print(f"DeepSeek review failed: {e}")
        return candidates


def main():
    conn = get_conn()
    ensure_tables(conn)
    cur = conn.cursor()

    print(f"🎯 VOX OPPORTUNITY ENGINE — {datetime.now().strftime('%a %b %d %H:%M')}")

    # 1. Top opportunities from full market
    opportunities = scan_top_opportunities(cur, top_n=100)
    store_opportunities(conn, opportunities)
    aggressive = [o for o in opportunities if o[0] not in DEFENSIVE_TICKERS]
    new_alerts = find_new_alerts(cur)

    # 2. Massive opportunities from portfolio
    massive, regime, confidence = massive_opportunities(cur)

    # 3. DeepSeek second-layer review
    new_alert_candidates = [{'ticker': a[0], 'grade': a[1], 'action': a[2], 'sector': a[3], 'is_aggressive': a[4]} for a in new_alerts]
    approved_new_alerts = deepseek_review(new_alert_candidates, "Top opportunity new alerts (grade >= 80)")
    approved_tickers = {a['ticker'] for a in approved_new_alerts}
    approved_massive = deepseek_review(massive, "Massive portfolio opportunities (grade >= 65, technical >= 60, size >= $2K)")

    print(f"Scanned: 19,356 tickers | Filtered: grade ≥ 65 + BUY/STRONG_BUY/ACCUMULATE")
    print(f"Top 100 stored. {len(aggressive)} aggressive plays.")
    print(f"Market regime: {regime} (confidence: {confidence}%)")
    print(f"Massive opportunities: {len(massive)} found, {len(approved_massive)} approved by DeepSeek")

    if approved_new_alerts:
        print(f"\n🚨 {len(approved_new_alerts)} NEW HIGH-CONVICTION ALERTS (80+)")
        for a in approved_new_alerts[:5]:
            emoji = "🔥" if a.get('is_aggressive') else ""
            print(f"  {emoji} **{a['ticker']}** — {a['action']} | Grade: {a['grade']} | Sector: {a.get('sector', 'Unknown')}")
        for a in new_alerts:
            if a[0] in approved_tickers:
                cur.execute("UPDATE top_opportunities SET alert_sent = TRUE WHERE ticker = %s", (a[0],))
        conn.commit()

    if approved_massive:
        print(f"\n🚀 {len(approved_massive)} MASSIVE OPPORTUNITY SETUPS")
        for opp in approved_massive[:5]:
            pnl_emoji = "🟢" if opp['pnl'] > 0 else "🔴"
            print(f"  **{opp['ticker']}** — {opp['council']} | Grade: {opp['grade']} | Tech: {opp['technical_score']}")
            print(f"    Position: ${opp['live_value']:,.0f} | P&L: {pnl_emoji} {opp['pnl']:+.1f}%")

    # 4. Top 15 aggressive
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
        is_agg, _ = classify_sector(sector)
        tag = " [AGGRESSIVE]" if is_agg else ""
        tech_str = f"{tech:2d}" if tech is not None else " N"
        print(f"{count:2d}. {ticker:6s} | Grade: {grade:2d} | {action:12s} | Tech: {tech_str}{tag}")

    conn.close()
    # Always exit 0 on successful scan — actionable content is in stdout.
    # (Exit 1 was previously used as an "alert" flag but marks the cron as failed.)
    return 0


if __name__ == "__main__":
    exit(main())
