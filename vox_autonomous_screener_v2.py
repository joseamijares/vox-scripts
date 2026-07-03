#!/usr/bin/env python3
"""
VOX Autonomous Screener v2
Finds oversold quality setups from live Railway Postgres data.
Flags tickers with grade >= 60 but negative P&L (oversold quality).
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
        print(f"❌ Failed to fetch positions: {e}")
        return []


def fetch_watchlist():
    try:
        req = urllib.request.Request(f"{DASHBOARD_API}/watchlist")
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data.get("watchlist", [])
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


def screen_tickers(positions, watchlist):
    """Find oversold quality setups."""
    setups = []
    
    # Screen existing positions: grade >= 60 but down > 15%
    for p in positions:
        grade = p.get("grade", 0)
        pnl_pct = p.get("pnl_pct", 0)
        if grade >= 60 and pnl_pct < -15:
            setups.append({
                "ticker": p["ticker"],
                "source": "portfolio",
                "grade": grade,
                "pnl_pct": pnl_pct,
                "price": p.get("live_price", 0),
                "rationale": f"Grade {grade} but down {pnl_pct:.1f}% — oversold quality"
            })
    
    # Screen watchlist: grade >= 65 with entry targets
    for w in watchlist:
        grade = w.get("grade", 0) or 0
        entry = w.get("entry_price", 0) or 0
        target = w.get("target_price", 0) or 0
        if grade >= 65 and entry > 0:
            setups.append({
                "ticker": w["ticker"],
                "source": "watchlist",
                "grade": grade,
                "entry": entry,
                "target": target,
                "rationale": f"Watchlist grade {grade} — setup ready"
            })
    
    # Sort by grade descending
    setups.sort(key=lambda x: x["grade"], reverse=True)
    return setups


if __name__ == "__main__":
    job_name = "vox-autonomous-screener"
    try:
        positions = fetch_positions()
        watchlist = fetch_watchlist()
        setups = screen_tickers(positions, watchlist)
        
        lines = []
        lines.append("=" * 60)
        lines.append(f"🔍 VOX AUTONOMOUS SCREENER — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append("=" * 60)
        lines.append("")
        lines.append(f"Found {len(setups)} setups")
        lines.append("")
        
        for s in setups[:15]:
            if s["source"] == "portfolio":
                lines.append(f"   {s['ticker']:6} Grade:{s['grade']} | {s['pnl_pct']:+.1f}% | ${s['price']:.2f} | {s['rationale']}")
            else:
                lines.append(f"   {s['ticker']:6} Grade:{s['grade']} | Entry:${s['entry']:.2f} | Target:${s.get('target', 0):.2f} | {s['rationale']}")
        
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
