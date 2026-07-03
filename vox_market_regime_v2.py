#!/usr/bin/env python3
"""
VOX Market Regime Detector v2
Detects bull/bear/sideways/volatile regime from live data.
Writes to Railway Postgres market_regime table.
"""

import json
import urllib.request
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


DASHBOARD_API = "https://web-production-9e321.up.railway.app/api"


def fetch_positions():
    try:
        req = urllib.request.Request(f"{DASHBOARD_API}/positions")
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data.get("positions", [])
    except Exception as e:
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


def detect_regime(positions):
    """Detect market regime from portfolio characteristics."""
    if not positions:
        return {
            "regime": "unknown",
            "confidence": 0,
            "description": "No position data available"
        }
    
    # Calculate portfolio metrics
    total_pnl_pct_values = []
    grades = []
    for p in positions:
        pnl = p.get("pnl_pct", 0)
        grade = p.get("grade", 0)
        if pnl != 0:
            total_pnl_pct_values.append(pnl)
        grades.append(grade)
    
    avg_pnl = sum(total_pnl_pct_values) / len(total_pnl_pct_values) if total_pnl_pct_values else 0
    avg_grade = sum(grades) / len(grades) if grades else 0
    
    # Count winners vs losers
    winners = sum(1 for p in total_pnl_pct_values if p > 0)
    losers = sum(1 for p in total_pnl_pct_values if p < 0)
    total = winners + losers
    
    win_rate = (winners / total * 100) if total > 0 else 50
    
    # Determine regime
    if avg_pnl > 30 and win_rate > 60:
        regime = "bull"
        confidence = min(avg_pnl, 100)
        description = f"Strong bull market. Avg P&L +{avg_pnl:.1f}%, {win_rate:.0f}% win rate."
    elif avg_pnl < -20 and win_rate < 40:
        regime = "bear"
        confidence = min(abs(avg_pnl), 100)
        description = f"Bear market. Avg P&L {avg_pnl:.1f}%, {win_rate:.0f}% win rate. Defensive posture recommended."
    elif abs(avg_pnl) < 10:
        regime = "sideways"
        confidence = 50
        description = f"Sideways market. Avg P&L {avg_pnl:.1f}%, {win_rate:.0f}% win rate. Range-bound strategies."
    else:
        regime = "volatile"
        confidence = 60
        description = f"Volatile market. Avg P&L {avg_pnl:.1f}%, mixed signals. Caution warranted."
    
    return {
        "regime": regime,
        "confidence": round(confidence, 1),
        "avg_grade": round(avg_grade, 1),
        "win_rate": round(win_rate, 1),
        "avg_pnl": round(avg_pnl, 1),
        "description": description
    }


if __name__ == "__main__":
    job_name = "vox-market-regime"
    try:
        positions = fetch_positions()
        regime = detect_regime(positions)
        
        output = f"Regime: {regime['regime'].upper()} (confidence: {regime['confidence']})\n"
        output += f"Avg Grade: {regime['avg_grade']} | Win Rate: {regime['win_rate']}% | Avg P&L: {regime['avg_pnl']}%\n"
        output += regime['description']
        
        print(output)
        record_cron_run(job_name, "ok", output)
        
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        print(f"❌ {error_msg}")
        record_cron_run(job_name, "error", "", error_msg)
        raise
