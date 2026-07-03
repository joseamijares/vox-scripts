#!/usr/bin/env python3
"""
VOX Alert System v3 - FIXED
Uses vox_watchlist_graded.json (yfinance grading) as source of truth
Instead of stale Railway positions table grades
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import json
import urllib.request
from pathlib import Path
from datetime import datetime

DASHBOARD_API = "https://web-production-9e321.up.railway.app/api"
SCRIPT_DIR = Path.home() / ".hermes" / "scripts"


def fetch_positions():
    """Fetch positions from Railway (for P&L, shares, broker info)"""
    try:
        req = urllib.request.Request(f"{DASHBOARD_API}/positions")
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data.get("positions", [])
    except Exception as e:
        print(f"❌ Failed to fetch positions: {e}")
        return []


def load_watchlist_grades():
    """Load current grades from vox_watchlist_graded.json (yfinance source of truth)"""
    graded_path = SCRIPT_DIR / "vox_watchlist_graded.json"
    if not graded_path.exists():
        print(f"❌ Watchlist graded file not found: {graded_path}")
        return {}
    
    try:
        with open(graded_path) as f:
            data = json.load(f)
        
        grades = {}
        for r in data.get("results", []):
            ticker = r.get("ticker", "")
            if ticker:
                grades[ticker] = {
                    "grade": r.get("grade", 0),
                    "rsi": r.get("rsi"),
                    "price": r.get("price", 0),
                    "timestamp": data.get("timestamp", "")
                }
        
        print(f"✅ Loaded {len(grades)} grades from watchlist_graded.json")
        print(f"   Graded at: {data.get('timestamp', 'N/A')}")
        return grades
    except Exception as e:
        print(f"❌ Error loading watchlist grades: {e}")
        return {}


# Minimum portfolio weight % to trigger P&L action alerts
# Positions below this threshold are too small to warrant action
MIN_POSITION_WEIGHT_PCT = 2.5

# Sanity check: P&L % above this is likely a data error (e.g. split-adjusted cost basis)
MAX_SANE_PNL_PCT = 1000


def check_alerts(positions, watchlist_grades):
    """Check for alert conditions using WATCHLIST grades (not Railway stale grades)"""
    alerts = []
    
    # Calculate total portfolio value for weight %
    total_portfolio = sum(p.get("live_value", 0) for p in positions if p.get("live_value", 0) > 0)
    
    for p in positions:
        ticker = p.get("ticker", "")
        
        # Use watchlist grade if available, fallback to Railway grade with warning
        if ticker in watchlist_grades:
            grade = watchlist_grades[ticker]["grade"]
            grade_source = "watchlist"
        else:
            grade = p.get("grade", 0)
            grade_source = "railway (stale)"
        
        pnl_pct = p.get("pnl_pct", 0)
        live_price = p.get("live_price", 0)
        avg_cost = p.get("avg_cost", 0)
        shares = p.get("shares", 0)
        live_value = p.get("live_value", 0)
        brokers = p.get("brokers", [])
        
        # Skip if no position
        if shares <= 0 or live_value <= 0:
            continue
        
        # Calculate portfolio weight
        weight_pct = (live_value / total_portfolio * 100) if total_portfolio > 0 else 0
        
        # Grade-based alerts (using watchlist grades) — always show regardless of size
        if 0 < grade < 40:
            alerts.append({
                "ticker": ticker,
                "type": "SELL_SIGNAL",
                "message": f"Grade {grade} ({grade_source}) — STRONG SELL",
                "severity": "HIGH",
                "grade_source": grade_source,
                "weight_pct": weight_pct
            })
        elif 40 <= grade < 50:
            alerts.append({
                "ticker": ticker,
                "type": "WEAK_GRADE",
                "message": f"Grade {grade} ({grade_source}) — weak, consider trimming",
                "severity": "MEDIUM",
                "grade_source": grade_source,
                "weight_pct": weight_pct
            })
        elif grade >= 70:
            alerts.append({
                "ticker": ticker,
                "type": "STRONG_BUY",
                "message": f"Grade {grade} ({grade_source}) — STRONG BUY signal",
                "severity": "MEDIUM",
                "grade_source": grade_source,
                "weight_pct": weight_pct
            })
        
        # P&L alerts (action alerts) — ONLY for meaningful positions
        # Skip tiny positions that don't move the needle
        if weight_pct < MIN_POSITION_WEIGHT_PCT:
            continue
        
        # Skip absurd P&L values — likely data errors (split-adjusted cost, etc.)
        if abs(pnl_pct) > MAX_SANE_PNL_PCT:
            continue
        
        if pnl_pct < -50:
            alerts.append({
                "ticker": ticker,
                "type": "STOP_LOSS",
                "message": f"Down {pnl_pct:.1f}% — major loss, consider cutting",
                "severity": "HIGH",
                "grade_source": "pnl",
                "weight_pct": weight_pct
            })
        elif pnl_pct > 300:
            alerts.append({
                "ticker": ticker,
                "type": "TAKE_PROFIT",
                "message": f"Up {pnl_pct:.0f}% — massive gain, consider trimming 25-50%",
                "severity": "MEDIUM",
                "grade_source": "pnl",
                "weight_pct": weight_pct
            })
        elif pnl_pct > 200:
            alerts.append({
                "ticker": ticker,
                "type": "TAKE_PROFIT",
                "message": f"Up {pnl_pct:.0f}% — strong gain, consider trimming 20-30%",
                "severity": "LOW",
                "grade_source": "pnl",
                "weight_pct": weight_pct
            })
    
    return alerts


def format_alert_output(alerts, positions):
    """Format alerts for Telegram output"""
    lines = []
    lines.append("=" * 60)
    lines.append(f"🚨 VOX ALERT SYSTEM v3 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 60)
    lines.append("")
    
    # Group by severity
    high = [a for a in alerts if a["severity"] == "HIGH"]
    medium = [a for a in alerts if a["severity"] == "MEDIUM"]
    low = [a for a in alerts if a["severity"] == "LOW"]
    
    # HIGH alerts
    if high:
        lines.append(f"🔴 HIGH PRIORITY ({len(high)}):")
        for a in high:
            lines.append(f"   {a['ticker']:8} | {a['type']:15}")
            lines.append(f"            → {a['message']}")
        lines.append("")
    
    # MEDIUM alerts
    if medium:
        lines.append(f"🟡 MEDIUM PRIORITY ({len(medium)}):")
        for a in medium:
            lines.append(f"   {a['ticker']:8} | {a['type']:15}")
            lines.append(f"            → {a['message']}")
        lines.append("")
    
    # LOW alerts
    if low:
        lines.append(f"🟢 LOW PRIORITY ({len(low)}):")
        for a in low:
            lines.append(f"   {a['ticker']:8} | {a['type']:15}")
            lines.append(f"            → {a['message']}")
        lines.append("")
    
    if not alerts:
        lines.append("✅ No alerts — all clear")
    
    lines.append("")
    lines.append("=" * 60)
    lines.append("📊 Grade Source: vox_watchlist_graded.json (yfinance)")
    lines.append("⚠️  P&L alerts use actual position data from Railway")
    lines.append("=" * 60)
    
    return "\n".join(lines)


if __name__ == "__main__":
    try:
        # Load current grades from watchlist
        watchlist_grades = load_watchlist_grades()
        
        # Fetch positions from Railway (for P&L and position data)
        positions = fetch_positions()
        
        # Check alerts using watchlist grades
        alerts = check_alerts(positions, watchlist_grades)
        
        # Format output
        output = format_alert_output(alerts, positions)
        print(output)
        
        # Save state
        state_path = SCRIPT_DIR / ".vox_alert_state_v9.json"
        try:
            with open(state_path, "w") as f:
                json.dump({
                    "timestamp": datetime.now().isoformat(),
                    "alerts_sent": len(alerts),
                    "alert_details": alerts,
                    "positions_checked": len(positions),
                    "grades_source": "vox_watchlist_graded.json"
                }, f, indent=2, default=str)
        except:
            pass
        
    except Exception as e:
        print(f"❌ Error: {e}")
        raise
