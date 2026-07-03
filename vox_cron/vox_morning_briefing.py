#!/usr/bin/env python3
"""
VOX Morning Briefing — Daily 7:00 AM CT
Generates a structured market + portfolio digest for Telegram.
"""
import os, sys
sys.path.insert(0, os.path.expanduser('~/.hermes/vox-agent/scripts'))
from sync_sp500_to_db import get_db_connection

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


def fetch_macro_summary(cur):
    cur.execute("SELECT signal_name, signal_value, signal_direction FROM macro_signals WHERE computed_at > NOW() - INTERVAL '1 day' ORDER BY signal_name")
    signals = cur.fetchall()
    cur.execute("SELECT regime, confidence FROM market_regime ORDER BY created_at DESC LIMIT 1")
    regime = cur.fetchone()
    return signals, regime

def fetch_portfolio_summary(cur):
    cur.execute("""
        SELECT 
            COUNT(*) AS total_positions,
            SUM(live_value) AS total_aum,
            SUM(live_value) FILTER (WHERE grade > 0) AS stock_aum,
            SUM(live_value) FILTER (WHERE grade = 0) AS crypto_aum,
            COUNT(*) FILTER (WHERE grade >= 70) AS strong,
            COUNT(*) FILTER (WHERE grade BETWEEN 55 AND 69) AS moderate,
            COUNT(*) FILTER (WHERE grade > 0 AND grade < 55) AS weak,
            COUNT(*) FILTER (WHERE avg_cost IS NULL) AS missing_cost_basis
        FROM positions
    """)
    return cur.fetchone()

def fetch_alerts(cur):
    cur.execute("""
        SELECT ticker, live_value, grade, council, live_price
        FROM positions
        WHERE grade > 0
        ORDER BY live_value DESC
    """)
    positions = cur.fetchall()
    total_aum = sum(p[1] or 0 for p in positions)
    alerts = []
    for p in positions:
        ticker, value, grade, council, price = p
        concentration = (value / total_aum) if total_aum else 0
        if concentration > 0.15:
            alerts.append({'ticker': ticker, 'severity': 'CRITICAL', 'type': 'CONCENTRATION', 'message': f'{concentration:.1%} of portfolio'})
        if grade < 45:
            alerts.append({'ticker': ticker, 'severity': 'ACTION', 'type': 'SELL', 'message': f'Grade {grade} below threshold'})
        if council == 'SELL':
            alerts.append({'ticker': ticker, 'severity': 'ACTION', 'type': 'COUNCIL_SELL', 'message': 'Council consensus SELL'})
    return alerts

def fetch_watchlist(cur):
    cur.execute("""
        SELECT w.ticker, w.grade, w.council
        FROM watchlist w
        LEFT JOIN positions p ON w.ticker = p.ticker
        WHERE w.grade >= 70 AND p.ticker IS NULL
        ORDER BY w.grade DESC
        LIMIT 5
    """)
    return cur.fetchall()

def main():
    conn = get_db_connection()
    cur = conn.cursor()

    signals, regime = fetch_macro_summary(cur)
    portfolio = fetch_portfolio_summary(cur)
    alerts = fetch_alerts(cur)
    watchlist = fetch_watchlist(cur)

    conn.close()

    total_positions, total_aum, stock_aum, crypto_aum, strong, moderate, weak, missing_cb = portfolio
    critical = [a for a in alerts if a['severity'] == 'CRITICAL']
    action = [a for a in alerts if a['severity'] == 'ACTION']

    # Build digest
    digest = []
    digest.append(f"# 🌅 VOX Morning Briefing — {datetime.utcnow().strftime('%Y-%m-%d')}")
    digest.append("")
    digest.append(f"**TL;DR:** Market regime: {regime[0] if regime else 'UNKNOWN'}. Portfolio: {total_positions} positions, ${total_aum:,.0f} AUM. {len(critical)} critical alerts, {len(action)} action items.")
    digest.append("")
    digest.append("## Market Snapshot")
    digest.append(f"- Regime: **{regime[0] if regime else 'UNKNOWN'}** (confidence: {regime[1] if regime else 0})")
    for s in signals:
        digest.append(f"- `{s[0]}`: {s[1]} ({s[2]})")
    digest.append("")
    digest.append("## Portfolio State")
    digest.append(f"- AUM: **${total_aum:,.0f}** ({total_positions} positions)")
    digest.append(f"- Stock AUM: ${stock_aum or 0:,.0f} | Crypto AUM: ${crypto_aum or 0:,.0f}")
    digest.append(f"- Grades: 🟢 {strong} | 🟡 {moderate} | 🔴 {weak}")
    digest.append(f"- Missing cost basis: {missing_cb} positions")
    digest.append("")
    digest.append("## Alerts")
    if critical:
        digest.append("🔴 **CRITICAL**")
        for a in critical:
            digest.append(f"- `{a['ticker']}`: {a['message']}")
    if action:
        digest.append("🟡 **ACTION**")
        for a in action[:5]:
            digest.append(f"- `{a['ticker']}` ({a['type']}): {a['message']}")
    if not critical and not action:
        digest.append("✅ No critical or action alerts")
    digest.append("")
    digest.append("## Top Watchlist")
    for w in watchlist:
        digest.append(f"- `{w[0]}` — grade {w[1]}, council {w[2]}")
    digest.append("")
    digest.append(f"_Generated at {datetime.utcnow().isoformat()}_")

    return "\n".join(digest)

if __name__ == "__main__":
    print(main())
