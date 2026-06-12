#!/usr/bin/env python3
"""
VOX Alert Monitor
Checks portfolio for stops, targets, concentration, and grade-based alerts.
Run at 9 AM and 3 PM CT weekdays via cron.
"""
import json
import os
import sys
from datetime import datetime

import psycopg2

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
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
        sslmode="require",
    )


def fetch_positions(cur):
    cur.execute("""
        SELECT ticker, shares, live_price, live_value, grade, council, sector, brokers, avg_cost
        FROM positions
        ORDER BY live_value DESC
    """)
    cols = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    return [dict(zip(cols, row)) for row in rows]


def fetch_watchlist(cur):
    cur.execute("""
        SELECT ticker, grade, council, sector
        FROM watchlist
        WHERE grade >= 70
        ORDER BY grade DESC
    """)
    cols = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    return [dict(zip(cols, row)) for row in rows]


def calculate_alerts(positions, watchlist):
    total_aum = sum(p.get("live_value") or 0 for p in positions)
    alerts = []

    for p in positions:
        value = p.get("live_value") or 0
        grade = p.get("grade") or 0
        council = p.get("council") or "HOLD"
        ticker = p["ticker"]
        concentration = value / total_aum if total_aum else 0

        # Critical: concentration
        if concentration > 0.20:
            alerts.append({
                "ticker": ticker,
                "severity": "CRITICAL",
                "type": "CONCENTRATION",
                "message": f"{concentration:.1%} of portfolio — reduce immediately"
            })

        # Critical: very low grade
        if grade > 0 and grade < 35:
            alerts.append({
                "ticker": ticker,
                "severity": "CRITICAL",
                "type": "SELL",
                "message": f"Grade {grade} — cut loss"
            })

        # Action: low grade
        if grade > 0 and 35 <= grade < 45:
            alerts.append({
                "ticker": ticker,
                "severity": "ACTION",
                "type": "SELL",
                "message": f"Grade {grade} — review thesis"
            })

        # Action: council SELL
        if council == "SELL":
            alerts.append({
                "ticker": ticker,
                "severity": "ACTION",
                "type": "COUNCIL_SELL",
                "message": "Council consensus SELL"
            })

        # Action: high grade stock with big loss (thesis disconnect)
        avg_cost = p.get("avg_cost")
        live_price = p.get("live_price")
        if grade >= 70 and avg_cost is not None and live_price is not None and float(live_price) < float(avg_cost) * 0.80:
            alerts.append({
                "ticker": ticker,
                "severity": "ACTION",
                "type": "THESIS_DISCONNECT",
                "message": f"Grade {grade} but down >20% — verify thesis"
            })

    return alerts


def generate_alert_digest():
    conn = get_db()
    cur = conn.cursor()

    positions = fetch_positions(cur)
    watchlist = fetch_watchlist(cur)
    alerts = calculate_alerts(positions, watchlist)

    conn.close()

    critical = [a for a in alerts if a["severity"] == "CRITICAL"]
    action = [a for a in alerts if a["severity"] == "ACTION"]
    watch = [a for a in alerts if a["severity"] == "WATCH"]

    total_aum = sum(p.get("live_value") or 0 for p in positions)

    # Top 10 holdings
    top_holdings = []
    for i, p in enumerate(positions[:10], 1):
        value = float(p.get("live_value") or 0)
        pct = value / float(total_aum) if total_aum else 0
        top_holdings.append({
            "rank": i,
            "ticker": p["ticker"],
            "value": value,
            "pct_aum": pct,
            "grade": p.get("grade", "—"),
            "council": p.get("council", "—"),
            "sector": p.get("sector", "—"),
        })

    # Systemic issues
    systemic_issues = []
    council_sell_high_grade = [a for a in action if a["type"] == "COUNCIL_SELL"]
    if council_sell_high_grade:
        # Check if any council SELL has grade >= 50
        high_grade_count = 0
        for a in council_sell_high_grade:
            # Find matching position
            for p in positions:
                if p["ticker"] == a["ticker"]:
                    grade = p.get("grade") or 0
                    if grade >= 50:
                        high_grade_count += 1
                    break
        if high_grade_count > 0:
            systemic_issues.append({
                "name": "Council Threshold Drift",
                "detail": f"{high_grade_count} position(s) with council=SELL but grade ≥50. Council logic is misaligned with grade scale (50-59 = HOLD). Review but do NOT auto-liquidate.",
            })

    digest = {
        "type": "alert_digest",
        "generated_at": datetime.utcnow().isoformat(),
        "portfolio_summary": {
            "total_positions": len(positions),
            "total_aum": float(total_aum),
            "top_holdings": top_holdings,
            "systemic_issues": systemic_issues,
        },
        "alerts": {
            "critical": critical,
            "action": action,
            "watch": watch,
        },
        "alert_count": len(alerts),
    }

    return digest


def format_digest(digest):
    ps = digest["portfolio_summary"]
    alerts = digest["alerts"]
    critical = alerts["critical"]
    action = alerts["action"]
    watch = alerts["watch"]
    all_alerts = critical + action + watch

    lines = [
        f"# 🚨 VOX Alert Monitor — {digest['generated_at'][:10]}",
        "",
        f"**Portfolio:** {ps['total_positions']} positions | **AUM:** ${ps['total_aum']:,.0f}",
        f"**Alerts:** {digest['alert_count']} total ({len(critical)} critical, {len(action)} action, {len(watch)} watch)",
        "",
        "---",
        "",
    ]

    # CRITICAL
    if critical:
        lines.append("## 🔴 CRITICAL — Act Immediately")
        lines.append("")
        lines.append("| Ticker | Type | Message |")
        lines.append("|:-------|:-----|:--------|")
        for a in critical:
            lines.append(f"| `{a['ticker']}` | {a['type']} | {a['message']} |")
        lines.append("")

    # ACTION — grouped by type
    if action:
        lines.append("## 🟡 ACTION — Review Today")
        lines.append("")

        # Concentration
        conc = [a for a in action if a["type"] == "CONCENTRATION"]
        if conc:
            lines.append("### Concentration Risk (>10% AUM)")
            lines.append("| Ticker | Type | Message |")
            lines.append("|:-------|:-----|:--------|")
            for a in conc:
                lines.append(f"| `{a['ticker']}` | {a['type']} | {a['message']} |")
            lines.append("")

        # Low grade
        low = [a for a in action if a["type"] == "SELL"]
        if low:
            lines.append("### Low Grade (SELL zone < 45)")
            lines.append("| Ticker | Type | Message |")
            lines.append("|:-------|:-----|:--------|")
            for a in low:
                lines.append(f"| `{a['ticker']}` | {a['type']} | {a['message']} |")
            lines.append("")

        # Council SELL
        council = [a for a in action if a["type"] == "COUNCIL_SELL"]
        if council:
            lines.append("### Council SELL Signals")
            lines.append("| Ticker | Type | Message |")
            lines.append("|:-------|:-----|:--------|")
            for a in council:
                lines.append(f"| `{a['ticker']}` | {a['type']} | {a['message']} |")
            lines.append("")

        # Thesis disconnects
        thesis = [a for a in action if a["type"] == "THESIS_DISCONNECT"]
        if thesis:
            lines.append("### Thesis Disconnects")
            lines.append("| Ticker | Type | Message |")
            lines.append("|:-------|:-----|:--------|")
            for a in thesis:
                lines.append(f"| `{a['ticker']}` | {a['type']} | {a['message']} |")
            lines.append("")

    # WATCH
    if watch:
        lines.append("## 🟢 WATCH — Monitor Closely")
        lines.append("")
        lines.append("| Ticker | Type | Message |")
        lines.append("|:-------|:-----|:--------|")
        for a in watch:
            lines.append(f"| `{a['ticker']}` | {a['type']} | {a['message']} |")
        lines.append("")

    if not critical and not action and not watch:
        lines.append("✅ No alerts. Portfolio is within guardrails.")
        lines.append("")

    # Alert Breakdown
    lines.append("---")
    lines.append("")
    lines.append("## Alert Breakdown")
    lines.append("| Type | Count |")
    lines.append("|:-----|:------|")
    type_counts = {}
    for a in all_alerts:
        type_counts[a["type"]] = type_counts.get(a["type"], 0) + 1
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        lines.append(f"| {t} | {c} |")
    lines.append("")

    # Top 10 Holdings
    if ps.get("top_holdings"):
        lines.append("## Top 10 Holdings")
        lines.append("| Rank | Ticker | Value | % AUM | Grade | Council | Sector |")
        lines.append("|:-----|:-------|:------|:------|:------|:--------|:-------|")
        for i, h in enumerate(ps["top_holdings"], 1):
            lines.append(
                f"| {i} | `{h['ticker']}` | ${h['value']:,.0f} | {h['pct_aum']:.1%} | {h['grade']} | {h['council']} | {h['sector']} |"
            )
        lines.append("")

    # Systemic Issues
    if ps.get("systemic_issues"):
        lines.append("## ⚠️ Systemic Issues Flagged")
        lines.append("")
        for issue in ps["systemic_issues"]:
            lines.append(f"1. **{issue['name']}** — {issue['detail']}")
        lines.append("")

    lines.append("---")
    lines.append(f"_Generated at {digest['generated_at']} | VOX Alert Monitor v1.1_")
    return "\n".join(lines)


if __name__ == "__main__":
    digest = generate_alert_digest()

    out_path = os.path.expanduser("~/.hermes/scripts/vox_cron/vox_alert_digest.json")
    with open(out_path, "w") as f:
        json.dump(digest, f, indent=2, default=str)

    print(format_digest(digest))
    sys.exit(0)
