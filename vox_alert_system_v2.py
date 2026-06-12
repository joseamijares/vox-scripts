#!/usr/bin/env python3
"""
VOX Alert System v2
Checks portfolio for alerts (stop loss, target hit, grade drops).
Fetches live data from Railway Postgres.
"""

import json
import urllib.request
from datetime import datetime

DASHBOARD_API = "https://web-production-9e321.up.railway.app/api"


def fetch_positions():
    try:
        req = urllib.request.Request(f"{DASHBOARD_API}/positions")
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data.get("positions", [])
    except Exception as e:
        print(f"❌ Failed to fetch positions: {e}")
        return []


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


def check_alerts(positions):
    """Check for alert conditions."""
    alerts = []
    
    for p in positions:
        ticker = p.get("ticker", "")
        grade = p.get("grade", 0)
        pnl_pct = p.get("pnl_pct", 0)
        live_price = p.get("live_price", 0)
        avg_cost = p.get("avg_cost", 0)
        
        # Grade-based alerts
        if 0 < grade < 45:
            alerts.append({
                "ticker": ticker,
                "type": "SELL_SIGNAL",
                "message": f"Grade {grade} — below SELL threshold (45)",
                "severity": "HIGH"
            })
        elif 45 <= grade < 50:
            alerts.append({
                "ticker": ticker,
                "type": "WEAK_GRADE",
                "message": f"Grade {grade} — weak, consider trimming",
                "severity": "MEDIUM"
            })
        
        # P&L alerts
        if pnl_pct < -50:
            alerts.append({
                "ticker": ticker,
                "type": "STOP_LOSS",
                "message": f"Down {pnl_pct:.1f}% — major loss",
                "severity": "HIGH"
            })
        elif pnl_pct > 200:
            alerts.append({
                "ticker": ticker,
                "type": "TAKE_PROFIT",
                "message": f"Up {pnl_pct:.0f}% — consider trimming",
                "severity": "MEDIUM"
            })
    
    return alerts


if __name__ == "__main__":
    job_name = "vox-alert-system"
    try:
        positions = fetch_positions()
        alerts = check_alerts(positions)
        
        lines = []
        lines.append("=" * 60)
        lines.append(f"🚨 VOX ALERT SYSTEM — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append("=" * 60)
        lines.append("")
        
        high = [a for a in alerts if a["severity"] == "HIGH"]
        medium = [a for a in alerts if a["severity"] == "MEDIUM"]
        
        if high:
            lines.append(f"🔴 HIGH ({len(high)}):")
            for a in high:
                lines.append(f"   {a['ticker']:6} | {a['type']:15} | {a['message']}")
            lines.append("")
        
        if medium:
            lines.append(f"🟡 MEDIUM ({len(medium)}):")
            for a in medium:
                lines.append(f"   {a['ticker']:6} | {a['type']:15} | {a['message']}")
            lines.append("")
        
        if not alerts:
            lines.append("✅ No alerts — all clear")
        
        lines.append("")
        lines.append("=" * 60)
        
        output = "\n".join(lines)
        print(output)
        record_cron_run(job_name, "ok", output[:2000])
        
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        print(f"❌ {error_msg}")
        record_cron_run(job_name, "error", "", error_msg)
        raise
