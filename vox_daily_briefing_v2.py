#!/usr/bin/env python3
"""
VOX Daily Briefing Generator v2
Generates actionable intelligence from live Railway Postgres data.
Writes briefing to stdout + records cron run.
"""

import json
import urllib.request
from datetime import datetime

DASHBOARD_API = "https://web-production-9e321.up.railway.app/api"


def fetch_data(endpoint):
    try:
        req = urllib.request.Request(f"{DASHBOARD_API}/{endpoint}")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"❌ Failed to fetch {endpoint}: {e}")
        return {}


def record_cron_run(job_name, status, output, error=None):
    try:
        body = json.dumps({
            "job_name": job_name,
            "status": status,
            "output": output,
            "error": error
        }).encode()
        req = urllib.request.Request(
            f"{DASHBOARD_API}/admin/cron-runs",
            data=body,
            headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=10)
    except:
        pass


def generate_briefing():
    positions_data = fetch_data("positions")
    alerts_data = fetch_data("alerts")
    plays_data = fetch_data("plays")
    
    positions = positions_data.get("positions", [])
    alerts = alerts_data.get("alerts", [])
    plays = plays_data.get("plays", [])
    
    if not positions:
        return "No position data available"
    
    total_value = sum(p.get("live_value", 0) for p in positions)
    total_pnl = sum(p.get("pnl", 0) for p in positions)
    
    # Top movers
    gainers = sorted([p for p in positions if p.get("pnl", 0) > 0], key=lambda x: x["pnl"], reverse=True)[:5]
    losers = sorted([p for p in positions if p.get("pnl", 0) < 0], key=lambda x: x["pnl"])[:5]
    
    # Grade distribution
    strong = [p for p in positions if p.get("grade", 0) >= 60]
    weak = [p for p in positions if p.get("grade", 0) < 50 and p.get("grade", 0) > 0]
    
    # SELL candidates
    sell_now = [p for p in positions if 0 < p.get("grade", 0) < 45]
    
    lines = []
    lines.append("=" * 60)
    lines.append(f"📊 VOX DAILY BRIEFING — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"💰 Portfolio: ${total_value:,.0f} | P&L: ${total_pnl:,.0f}")
    lines.append(f"📈 Positions: {len(positions)} | Strong (≥60): {len(strong)} | Weak (<50): {len(weak)}")
    lines.append("")
    
    if sell_now:
        lines.append("🔴 SELL CANDIDATES (Grade < 45):")
        for p in sell_now[:5]:
            lines.append(f"   {p['ticker']:6} Grade:{p['grade']} | ${p['live_value']:,.0f} | {p.get('pnl_pct', 0):+.1f}%")
        lines.append("")
    
    if gainers:
        lines.append("🟢 TOP GAINERS:")
        for p in gainers[:5]:
            lines.append(f"   {p['ticker']:6} +${p['pnl']:,.0f} ({p['pnl_pct']:+.1f}%)")
        lines.append("")
    
    if losers:
        lines.append("🔴 TOP LOSERS:")
        for p in losers[:5]:
            lines.append(f"   {p['ticker']:6} ${p['pnl']:,.0f} ({p['pnl_pct']:+.1f}%)")
        lines.append("")
    
    if alerts:
        lines.append(f"🚨 RECENT ALERTS ({len(alerts)} total):")
        for a in alerts[:3]:
            lines.append(f"   [{a.get('alert_type', 'ALERT')}] {a.get('ticker', '')}: {a.get('message', '')[:60]}")
        lines.append("")
    
    lines.append("=" * 60)
    
    return "\n".join(lines)


if __name__ == "__main__":
    job_name = "vox-daily-briefing"
    try:
        briefing = generate_briefing()
        print(briefing)
        record_cron_run(job_name, "ok", briefing[:2000])
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        print(f"❌ {error_msg}")
        record_cron_run(job_name, "error", "", error_msg)
        raise
