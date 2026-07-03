#!/usr/bin/env python3
"""
VOX Sector Scanner v2
Grades portfolio positions by sector, identifies sector rotation opportunities.
Fetches live data from Railway Postgres.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import json
import urllib.request
from datetime import datetime
from collections import defaultdict
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


def scan_sectors(positions, watchlist):
    """Analyze sector distribution and grades."""
    sector_values = defaultdict(float)
    sector_positions = defaultdict(list)
    sector_pnl = defaultdict(float)
    
    for p in positions:
        sector = p.get("sector") or "Unknown"
        sector_values[sector] += float(p.get("live_value", 0) or 0)
        sector_positions[sector].append(p)
        sector_pnl[sector] += float(p.get("pnl", 0) or 0)
    
    # Calculate avg grade per sector
    sector_avg_grade = {}
    sector_count = {}
    for sector, pos_list in sector_positions.items():
        grades = [p.get("grade", 0) for p in pos_list if p.get("grade", 0) > 0]
        sector_avg_grade[sector] = sum(grades) / len(grades) if grades else 0
        sector_count[sector] = len(pos_list)
    
    total_value = sum(sector_values.values())
    
    # Sort by value
    sorted_sectors = sorted(sector_values.keys(), key=lambda s: sector_values[s], reverse=True)
    
    lines = []
    lines.append("=" * 60)
    lines.append(f"📊 VOX SECTOR SCAN — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"{'Sector':<20} {'Value':>12} {'%':>6} {'Grade':>6} {'Positions':>10} {'P&L':>12}")
    lines.append("-" * 70)
    
    for sector in sorted_sectors:
        val = sector_values[sector]
        pct = (val / total_value * 100) if total_value > 0 else 0
        avg_grade = sector_avg_grade.get(sector, 0)
        count = sector_count.get(sector, 0)
        pnl = sector_pnl[sector]
        lines.append(f"{sector:<20} ${val:>10,.0f} {pct:>5.1f}% {avg_grade:>5.1f} {count:>9} ${pnl:>10,.0f}")
    
    lines.append("")
    
    # Find weak sectors (avg grade < 50)
    weak_sectors = [s for s in sorted_sectors if sector_avg_grade.get(s, 0) < 50 and sector_values[s] > 1000]
    if weak_sectors:
        lines.append("⚠️  WEAK SECTORS (avg grade < 50, value > $1K):")
        for sector in weak_sectors:
            lines.append(f"   {sector}: grade {sector_avg_grade[sector]:.1f}, ${sector_values[sector]:,.0f}")
        lines.append("")
    
    # Find strong sectors (avg grade >= 60)
    strong_sectors = [s for s in sorted_sectors if sector_avg_grade.get(s, 0) >= 60]
    if strong_sectors:
        lines.append("✅ STRONG SECTORS (avg grade ≥ 60):")
        for sector in strong_sectors:
            lines.append(f"   {sector}: grade {sector_avg_grade[sector]:.1f}, ${sector_values[sector]:,.0f}")
        lines.append("")
    
    # Watchlist by sector
    watchlist_by_sector = defaultdict(list)
    for w in watchlist:
        sector = w.get("sector") or "Unknown"
        watchlist_by_sector[sector].append(w)
    
    # Suggest sector rotation
    lines.append("🔄 SECTOR ROTATION OPPORTUNITIES:")
    for sector in sorted_sectors[:5]:
        if sector_avg_grade.get(sector, 0) < 55:
            watch_tickers = [w["ticker"] for w in watchlist_by_sector.get(sector, []) if w.get("grade", 0) >= 60]
            if watch_tickers:
                lines.append(f"   {sector}: Consider rotating to {', '.join(watch_tickers[:3])}")
    
    lines.append("")
    lines.append("=" * 60)
    
    return "\n".join(lines)


if __name__ == "__main__":
    job_name = "vox-sector-scan"
    try:
        positions = fetch_positions()
        watchlist = fetch_watchlist()
        output = scan_sectors(positions, watchlist)
        print(output)
        record_cron_run(job_name, "ok", output[:2000])
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        print(f"❌ {error_msg}")
        record_cron_run(job_name, "error", "", error_msg)
        raise
