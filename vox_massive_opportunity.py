#!/usr/bin/env python3
"""
VOX Massive Opportunity Detector v1
Scans for high-conviction trading opportunities that meet ALL criteria:
- Grade ≥ 65
- Technical score ≥ 60
- Position size ≥ $2,000
- Not in crisis regime

Outputs to Telegram via stdout (for Hermes cron delivery).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import sys
import psycopg2
from datetime import datetime
import json
from pathlib import Path

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

def get_conn():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER,
        password=DB_PASSWORD, dbname=DB_NAME, sslmode="require"
    )

def check_crisis_regime(cur):
    """Check if market is in crisis regime"""
    cur.execute("""
        SELECT regime, confidence 
        FROM market_regime 
        ORDER BY created_at DESC 
        LIMIT 1
    """)
    row = cur.fetchone()
    if row:
        regime, confidence = row
        return regime in ["CRISIS", "BEAR", "CRASH"], regime, confidence
    return False, "UNKNOWN", 0

def find_massive_opportunities(cur):
    """Find opportunities meeting all criteria"""
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
    return cur.fetchall()

def main():
    conn = get_conn()
    cur = conn.cursor()
    
    # Check crisis regime
    is_crisis, regime, confidence = check_crisis_regime(cur)
    
    if is_crisis:
        print(f"⚠️ **VOX MASSIVE OPPORTUNITY — {datetime.now().strftime('%a %b %d')}**")
        print(f"\nMarket regime: {regime} (confidence: {confidence}%)")
        print("\n🔴 **No opportunities shown during crisis regime.**")
        print("Focus on capital preservation. Review again when regime improves.")
        conn.close()
        return
    
    # Find opportunities
    opportunities = find_massive_opportunities(cur)
    
    # Filter by technical score >= 60
    qualified = []
    for opp in opportunities:
        ticker, grade, live_value, sector, council, tech_score, avg_cost, live_price = opp
        if tech_score >= 60:
            qualified.append(opp)
    
    if not qualified:
        # Silent exit — no alert sent
        print(f"🎯 **VOX MASSIVE OPPORTUNITY — {datetime.now().strftime('%a %b %d')}**")
        print(f"\nRegime: {regime} (confidence: {confidence}%)")
        print("\n⚪ No massive opportunities found.")
        print("\nCriteria: grade≥65 + technical≥60 + size≥$2K + not crisis")
        conn.close()
        return
    
    # Build alert
    print(f"🚀 **VOX MASSIVE OPPORTUNITY — {datetime.now().strftime('%a %b %d')}**")
    print(f"\nRegime: {regime} (confidence: {confidence}%)")
    print(f"\n**{len(qualified)} HIGH-CONVICTION SETUP{'S' if len(qualified) > 1 else ''}**")
    print("=" * 50)
    
    for opp in qualified:
        ticker, grade, live_value, sector, council, tech_score, avg_cost, live_price = opp
        
        # Calculate P&L
        pnl = (live_price - avg_cost) / avg_cost * 100 if avg_cost > 0 else 0
        pnl_emoji = "🟢" if pnl > 0 else "🔴"
        
        print(f"\n**{ticker}** — {council}")
        print(f"  Grade: {grade}/100 | Technical: {tech_score}/100")
        print(f"  Position: ${live_value:,.0f} | Sector: {sector}")
        print(f"  Price: ${live_price:.2f} | Cost: ${avg_cost:.2f}")
        print(f"  P&L: {pnl_emoji} {pnl:+.1f}%")
        
        # Action recommendation
        if council == "CORE" and grade >= 70:
            print(f"  💡 **Action:** Hold core position. Consider adding on dips.")
        elif council == "BUY" and grade >= 65:
            print(f"  💡 **Action:** Strong buy signal. Consider increasing position.")
    
    print("\n" + "=" * 50)
    print("⚠️ **This is not financial advice. Do your own due diligence.**")
    
    conn.close()

if __name__ == "__main__":
    main()
