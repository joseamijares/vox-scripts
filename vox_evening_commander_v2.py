#!/usr/bin/env python3
"""
VOX Evening Commander v2
Evening scan: positions, watchlist, alerts, grades.
Generates summary + records cron run.
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


def evening_scan():
    positions_data = fetch_data("positions")
    watchlist_data = fetch_data("watchlist")
    alerts_data = fetch_data("alerts")
    
    positions = positions_data.get("positions", [])
    watchlist = watchlist_data.get("watchlist", [])
    alerts = alerts_data.get("alerts", [])
    
    total_value = sum(p.get("live_value", 0) for p in positions)
    total_pnl = sum(p.get("pnl", 0) for p in positions)
    
    # Count by grade
    strong = sum(1 for p in positions if p.get("grade", 0) >= 60)
    moderate = sum(1 for p in positions if 50 <= p.get("grade", 0) < 60)
    weak = sum(1 for p in positions if 0 < p.get("grade", 0) < 50)
    
    # Top/Bottom 3
    gainers = sorted([p for p in positions if p.get("pnl", 0) > 0], key=lambda x: x["pnl"], reverse=True)[:3]
    losers = sorted([p for p in positions if p.get("pnl", 0) < 0], key=lambda x: x["pnl"])[:3]
    
    lines = []
    lines.append("=" * 60)
    lines.append(f"🌙 VOX EVENING COMMANDER — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"💰 Portfolio: ${total_value:,.0f} | P&L: ${total_pnl:,.0f}")
    lines.append(f"📊 Positions: {len(positions)} | Strong: {strong} | Moderate: {moderate} | Weak: {weak}")
    lines.append(f"👁️  Watchlist: {len(watchlist)} | Alerts: {len(alerts)}")
    lines.append("")
    
    if gainers:
        lines.append("🟢 Top Gainers:")
        for p in gainers:
            lines.append(f"   {p['ticker']:6} +${p['pnl']:,.0f} ({p['pnl_pct']:+.1f}%)")
        lines.append("")
    
    if losers:
        lines.append("🔴 Top Losers:")
        for p in losers:
            lines.append(f"   {p['ticker']:6} ${p['pnl']:,.0f} ({p['pnl_pct']:+.1f}%)")
        lines.append("")
    
    # Watchlist highlights
    high_grade_watchlist = [w for w in watchlist if w.get("grade", 0) >= 65]
    if high_grade_watchlist:
        lines.append("⭐ High-Grade Watchlist (≥65):")
        for w in high_grade_watchlist[:5]:
            lines.append(f"   {w['ticker']:6} Grade:{w.get('grade', 0)} | Entry:${w.get('entry_price', 0) or 0:.2f}")
        lines.append("")
    
    lines.append("=" * 60)
    
    return "\n".join(lines)


if __name__ == "__main__":
    job_name = "vox-evening-commander"
    try:
        output = evening_scan()
        print(output)
        record_cron_run(job_name, "ok", output[:2000])
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        print(f"❌ {error_msg}")
        record_cron_run(job_name, "error", "", error_msg)
        raise
