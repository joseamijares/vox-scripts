#!/usr/bin/env python3
"""
VOX Evening Digest — Consolidated Post-Market Summary
Runs at 4:30 PM CT weekdays. Delivers ONE message with the day's wrap-up.

Includes:
- Day's P&L + biggest movers
- Grade changes (what got upgraded/downgraded)
- New alerts triggered during the day
- Tomorrow's watchlist
- Macro update
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import sys
import json
from datetime import datetime, timedelta

import psycopg2
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
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_NAME = os.environ.get("DB_NAME", "railway")


def get_db():
    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL)
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER,
        password=DB_PASSWORD, dbname=DB_NAME, sslmode="require",
    )


def fetch_portfolio(cur):
    cur.execute("""
        SELECT COUNT(*), 
               SUM(live_value),
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
        SELECT ticker, live_value, grade, council, live_price, avg_cost, shares, sector, updated_at, currency
        FROM positions
        WHERE live_value > 0
        ORDER BY live_value DESC
    """)
    cols = [desc[0] for desc in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def fetch_grade_changes(cur):
    """Find positions whose grade changed today vs yesterday."""
    cur.execute("""
        SELECT p.ticker, p.grade as current_grade, p.council as current_council,
               g.vox_grade as previous_grade
        FROM positions p
        LEFT JOIN sp500_grades g ON p.ticker = g.ticker
        WHERE p.grade != COALESCE(g.vox_grade, p.grade)
          AND p.updated_at > NOW() - INTERVAL '1 day'
        LIMIT 10
    """)
    cols = [desc[0] for desc in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def fetch_opportunities(cur):
    cur.execute("""
        SELECT g.ticker, g.vox_grade, u.sector
        FROM sp500_grades g
        JOIN sp500_universe u ON g.ticker = u.ticker
        LEFT JOIN positions p ON g.ticker = p.ticker
        WHERE g.vox_grade >= 75 AND p.ticker IS NULL
        ORDER BY g.vox_grade DESC
        LIMIT 5
    """)
    cols = [desc[0] for desc in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def fetch_macro(cur):
    cur.execute("SELECT regime, confidence, vix_level FROM market_regime ORDER BY created_at DESC LIMIT 1")
    return cur.fetchone()


def calculate_alerts(positions):
    total_aum = sum(float(p.get("live_value") or 0) for p in positions)
    alerts = []
    for p in positions:
        value = float(p.get("live_value") or 0)
        grade = p.get("grade") or 0
        council = p.get("council") or "HOLD"
        ticker = p["ticker"]
        concentration = value / total_aum if total_aum else 0

        if concentration > 0.20:
            alerts.append({"ticker": ticker, "severity": "CRITICAL", "type": "CONCENTRATION", "message": f"{concentration:.1%} of portfolio"})
        if 0 < grade < 40:
            alerts.append({"ticker": ticker, "severity": "CRITICAL", "type": "SELL", "message": f"Grade {grade}"})
        elif 40 <= grade < 50:
            alerts.append({"ticker": ticker, "severity": "ACTION", "type": "SELL", "message": f"Grade {grade}"})
        if council == "SELL":
            alerts.append({"ticker": ticker, "severity": "ACTION", "type": "COUNCIL", "message": "Council SELL"})
    return alerts


def build_digest():
    conn = get_db()
    cur = conn.cursor()

    portfolio = fetch_portfolio(cur)
    positions = fetch_positions(cur)
    grade_changes = fetch_grade_changes(cur)
    opportunities = fetch_opportunities(cur)
    regime = fetch_macro(cur)

    conn.close()

    total_pos, total_aum, core, buy, hold, weak, ungraded = portfolio
    total_aum = float(total_aum) if total_aum else 0
    alerts = calculate_alerts(positions)
    critical = [a for a in alerts if a["severity"] == "CRITICAL"]
    action = [a for a in alerts if a["severity"] == "ACTION"]

    # Biggest movers
    gainers = sorted([p for p in positions if (p.get("pnl_pct") or 0) > 0], key=lambda x: x.get("pnl_pct", 0), reverse=True)[:3]
    losers = sorted([p for p in positions if (p.get("pnl_pct") or 0) < 0], key=lambda x: x.get("pnl_pct", 0))[:3]

    lines = []
    lines.append(f"🌆 **VOX EVENING — {datetime.utcnow().strftime('%a %b %d')}**")

    # P&L + Regime in one line
    # live_value and avg_cost are already in account base currency
    total_pnl = 0
    for p in positions:
        live_val = float(p.get("live_value") or 0)
        cost_basis = float(p.get("avg_cost") or 0) * float(p.get("shares") or 0)
        total_pnl += (live_val - cost_basis)
    pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"
    r_vix = regime[2] if regime else 0
    vix_emoji = "🟢" if r_vix < 20 else "🟡" if r_vix < 25 else "🔴"
    lines.append(f"AUM ${total_aum or 0:,.0f} | P&L {pnl_emoji} ${total_pnl:+,.0f} | VIX {vix_emoji} {r_vix:.1f}")
    lines.append("")

    # Movers (only if significant)
    if gainers or losers:
        lines.append("Movers")
        for p in gainers:
            lines.append(f"  🟢 `{p['ticker']}` +{p.get('pnl_pct', 0):.1f}%")
        for p in losers:
            lines.append(f"  🔴 `{p['ticker']}` {p.get('pnl_pct', 0):.1f}%")
        lines.append("")

    # Grade changes (only significant: crossed 50 or 60)
    significant_changes = [gc for gc in grade_changes
        if (gc.get("previous_grade") or 0) < 50 and (gc.get("current_grade") or 0) >= 50
        or (gc.get("previous_grade") or 0) < 60 and (gc.get("current_grade") or 0) >= 60
        or (gc.get("previous_grade") or 0) >= 50 and (gc.get("current_grade") or 0) < 50
        or (gc.get("previous_grade") or 0) >= 60 and (gc.get("current_grade") or 0) < 60
    ]
    if significant_changes:
        lines.append("Grade Changes")
        for gc in significant_changes[:3]:
            prev = gc.get("previous_grade") or 0
            curr = gc.get("current_grade") or 0
            direction = "⬆️" if curr > prev else "⬇️"
            lines.append(f"  {direction} `{gc['ticker']}` {prev:.0f}→{curr:.0f} ({gc.get('current_council', 'HOLD')})")
        lines.append("")

    # Alerts (only if still active)
    if critical:
        lines.append("🔴 Urgent")
        for a in critical[:3]:
            lines.append(f"  • `{a['ticker']}` — {a['message']}")
        lines.append("")
    if action:
        lines.append("🟡 Action")
        for a in action[:3]:
            lines.append(f"  • `{a['ticker']}` — {a['message']}")
        lines.append("")

    # Opportunities (only CORE grade)
    core_opps = [o for o in opportunities if (o.get("vox_grade") or 0) >= 70][:2]
    if core_opps:
        lines.append("🎯 Watchlist")
        for opp in core_opps:
            lines.append(f"  `{opp['ticker']}` g{opp.get('vox_grade', 0)} | {opp.get('sector', '')}")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    print(build_digest())
