#!/usr/bin/env python3
"""
VOX Morning Digest — Consolidated Pre-Market Briefing
Runs at 7:30 AM CT weekdays. Delivers ONE message with everything critical.

Includes:
- Market regime + macro snapshot
- Portfolio state (AUM, P&L, grade distribution)
- Urgent position actions (SELL, TRIM, concentration risk)
- Top 3 new opportunities
- Overnight movers / news
"""
import os
import sys
import json
from datetime import datetime

import psycopg2

# Load env
for env_path in [os.path.expanduser("~/.env"), os.path.expanduser("~/.hermes/.env")]:
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    k, v = line.strip().split("=", 1)
                    os.environ.setdefault(k, v)

DATABASE_URL = os.environ.get("DATABASE_URL")
DB_HOST = os.environ.get("DB_HOST", "acela.proxy.rlwy.net")
DB_PORT = os.environ.get("DB_PORT", "35577")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_NAME = os.environ.get("DB_NAME", "railway")


def get_db():
    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL)
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER,
        password=DB_PASSWORD, dbname=DB_NAME, sslmode="require",
    )


def fetch_macro(cur):
    cur.execute("SELECT signal_name, signal_value, signal_direction FROM macro_signals WHERE computed_at > NOW() - INTERVAL '2 days' ORDER BY signal_name")
    signals = cur.fetchall()
    cur.execute("SELECT regime, confidence, vix_level, yield_curve, fed_stance FROM market_regime ORDER BY created_at DESC LIMIT 1")
    regime = cur.fetchone()
    return signals, regime


def fetch_portfolio(cur):
    cur.execute("""
        SELECT COUNT(*), 
               SUM(CASE WHEN currency = 'MXN' THEN live_value / 17.5 ELSE live_value END),
               COUNT(*) FILTER (WHERE grade >= 70),
               COUNT(*) FILTER (WHERE grade BETWEEN 60 AND 69),
               COUNT(*) FILTER (WHERE grade BETWEEN 50 AND 59),
               COUNT(*) FILTER (WHERE grade > 0 AND grade < 50),
               COUNT(*) FILTER (WHERE grade = 0 OR grade IS NULL)
        FROM positions
    """)
    return cur.fetchone()


def fetch_positions(cur):
    cur.execute("""
        SELECT ticker, live_value, grade, council, live_price, avg_cost, sector
        FROM positions
        WHERE live_value > 0
        ORDER BY live_value DESC
    """)
    cols = [desc[0] for desc in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def fetch_opportunities(cur):
    cur.execute("""
        SELECT g.ticker, g.vox_grade, g.technical_score, g.fundamental_score,
               u.sector, u.security
        FROM sp500_grades g
        JOIN sp500_universe u ON g.ticker = u.ticker
        LEFT JOIN positions p ON g.ticker = p.ticker
        WHERE g.vox_grade >= 75 AND p.ticker IS NULL
        ORDER BY g.vox_grade DESC
        LIMIT 5
    """)
    cols = [desc[0] for desc in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def fetch_watchlist_gems(cur):
    cur.execute("""
        SELECT ticker, grade, council, sector
        FROM watchlist
        WHERE grade >= 75
          AND ticker NOT IN (SELECT ticker FROM positions WHERE live_value > 0)
        ORDER BY grade DESC
        LIMIT 5
    """)
    cols = [desc[0] for desc in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def calculate_alerts(positions):
    total_aum = sum(p.get("live_value") or 0 for p in positions)
    alerts = []
    for p in positions:
        value = p.get("live_value") or 0
        grade = p.get("grade") or 0
        council = p.get("council") or "HOLD"
        ticker = p["ticker"]
        concentration = value / total_aum if total_aum else 0

        if concentration > 0.20:
            alerts.append({"ticker": ticker, "severity": "CRITICAL", "type": "CONCENTRATION", "message": f"{concentration:.1%} of portfolio"})
        if 0 < grade < 40:
            alerts.append({"ticker": ticker, "severity": "CRITICAL", "type": "SELL", "message": f"Grade {grade} — cut immediately"})
        elif 40 <= grade < 50:
            alerts.append({"ticker": ticker, "severity": "ACTION", "type": "SELL", "message": f"Grade {grade} — review today"})
        if council == "SELL":
            alerts.append({"ticker": ticker, "severity": "ACTION", "type": "COUNCIL", "message": "Council says SELL"})
    return alerts


def build_digest():
    conn = get_db()
    cur = conn.cursor()

    signals, regime = fetch_macro(cur)
    portfolio = fetch_portfolio(cur)
    positions = fetch_positions(cur)
    opportunities = fetch_opportunities(cur)
    watchlist_gems = fetch_watchlist_gems(cur)

    conn.close()

    total_pos, total_aum, core, buy, hold, weak, ungraded = portfolio
    alerts = calculate_alerts(positions)
    critical = [a for a in alerts if a["severity"] == "CRITICAL"]
    action = [a for a in alerts if a["severity"] == "ACTION"]

    # Combine opportunities
    all_opps = []
    seen = set()
    for source, items in [("sp500", opportunities), ("watchlist", watchlist_gems)]:
        for item in items:
            t = item.get("ticker")
            if t and t not in seen:
                seen.add(t)
                item["source"] = source
                all_opps.append(item)
    all_opps.sort(key=lambda x: x.get("vox_grade", x.get("grade", 0)) or 0, reverse=True)
    top_opps = all_opps[:3]

    # Top 5 holdings
    top5 = positions[:5]

    lines = []
    lines.append(f"🌅 **VOX MORNING — {datetime.utcnow().strftime('%a %b %d')}**")

    # Regime + Portfolio in one line
    r_name = regime[0] if regime else "UNKNOWN"
    r_vix = regime[2] if regime else 0
    vix_emoji = "🟢" if r_vix < 20 else "🟡" if r_vix < 25 else "🔴"
    lines.append(f"Regime: {r_name} | VIX {vix_emoji} {r_vix:.1f} | AUM ${total_aum or 0:,.0f}")
    lines.append(f"Council: 🟢{core} 🔵{buy} 🟡{hold} 🟠{weak} ⚪{ungraded}")
    lines.append("")

    # Alerts ONLY if they exist (no noise)
    if critical:
        lines.append("🔴 URGENT")
        for a in critical[:3]:
            lines.append(f"  • `{a['ticker']}` — {a['message']}")
        lines.append("")
    if action:
        lines.append("🟡 Action")
        for a in action[:3]:
            lines.append(f"  • `{a['ticker']}` — {a['message']}")
        lines.append("")

    # Top Holdings (only if concentration risk)
    lines.append("Top Holdings")
    for p in top5:
        grade = p.get("grade") or 0
        g_emoji = "🟢" if grade >= 70 else "🔵" if grade >= 60 else "🟡" if grade >= 50 else "🔴"
        lines.append(f"  {g_emoji} `{p['ticker']}` ${p.get('live_value', 0):,.0f} g{grade}")
    lines.append("")

    # Opportunities (only if grade >= 70)
    top_opps = [o for o in all_opps if (o.get("vox_grade", o.get("grade", 0)) or 0) >= 70][:2]
    if top_opps:
        lines.append("🎯 Opportunities")
        for opp in top_opps:
            g = opp.get("vox_grade", opp.get("grade", 0))
            lines.append(f"  `{opp['ticker']}` g{g} | {opp.get('sector', '')}")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    print(build_digest())
