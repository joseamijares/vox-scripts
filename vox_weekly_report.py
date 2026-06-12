#!/usr/bin/env python3
"""
VOX Weekly Report Generator
Compares portfolio week-over-week:
- Total P&L
- Grade changes (upgrades/downgrades)
- Council consensus changes
- New plays logged
- Best/worst performers
"""

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"
SNAPSHOTS_DIR = SCRIPT_DIR / "portfolio_snapshots"
REPORTS_DIR = SCRIPT_DIR / "reports"
PLAYS_FILE = SCRIPT_DIR / "vox_historic_plays.jsonl"

def ensure_dirs():
    SNAPSHOTS_DIR.mkdir(exist_ok=True)
    REPORTS_DIR.mkdir(exist_ok=True)

def load_snapshot(date_str):
    """Load portfolio snapshot for a date."""
    snapshot_file = SNAPSHOTS_DIR / f"portfolio_{date_str}.json"
    if not snapshot_file.exists():
        return None
    with open(snapshot_file) as f:
        return json.load(f)

def get_positions_dict(snapshot):
    """Extract positions as dict from snapshot."""
    if not snapshot:
        return {}
    positions = snapshot.get("positions", [])
    return {p["ticker"]: p for p in positions if p.get("ticker") != "TOTAL"}

def get_total_value(snapshot):
    """Get total portfolio value from snapshot."""
    if not snapshot:
        return 0
    positions = snapshot.get("positions", [])
    # Find TOTAL entry or sum all
    for p in positions:
        if p.get("ticker") == "TOTAL":
            return p.get("live_value", p.get("value", 0))
    return sum(p.get("live_value", p.get("value", 0)) for p in positions)

def load_plays_this_week(week_start, week_end):
    """Load plays from this week."""
    if not PLAYS_FILE.exists():
        return []
    
    plays = []
    with open(PLAYS_FILE) as f:
        for line in f:
            play = json.loads(line.strip())
            play_date = datetime.fromisoformat(play["timestamp"]).date()
            if week_start <= play_date <= week_end:
                plays.append(play)
    return plays

def generate_weekly_report():
    """Generate the weekly report."""
    ensure_dirs()
    
    today = datetime.now(timezone.utc).date()
    week_start = today - timedelta(days=today.weekday())  # Monday
    week_end = week_start + timedelta(days=6)  # Sunday
    
    # Load snapshots
    current_snapshot = load_snapshot(today.isoformat())
    prev_week_start = week_start - timedelta(days=7)
    prev_snapshot = load_snapshot(prev_week_start.isoformat())
    
    # If no current snapshot, create one
    if not current_snapshot:
        from vox_play_logger import snapshot_portfolio
        snapshot_portfolio()
        current_snapshot = load_snapshot(today.isoformat())
    
    current_positions = get_positions_dict(current_snapshot)
    prev_positions = get_positions_dict(prev_snapshot)
    
    current_total = get_total_value(current_snapshot)
    prev_total = get_total_value(prev_snapshot)
    
    # Weekly P&L
    weekly_pnl = current_total - prev_total if prev_total > 0 else 0
    weekly_pnl_pct = (weekly_pnl / prev_total * 100) if prev_total > 0 else 0
    
    # Grade changes
    upgrades = []
    downgrades = []
    for ticker, pos in current_positions.items():
        if ticker in prev_positions:
            curr_grade = pos.get("grade", 0)
            prev_grade = prev_positions[ticker].get("grade", 0)
            if curr_grade > prev_grade + 5:
                upgrades.append({
                    "ticker": ticker,
                    "prev": prev_grade,
                    "curr": curr_grade,
                    "change": curr_grade - prev_grade
                })
            elif curr_grade < prev_grade - 5:
                downgrades.append({
                    "ticker": ticker,
                    "prev": prev_grade,
                    "curr": curr_grade,
                    "change": curr_grade - prev_grade
                })
    
    # Best/worst performers this week
    performers = []
    for ticker, pos in current_positions.items():
        if ticker in prev_positions:
            curr_value = pos.get("live_value", pos.get("value", 0))
            prev_value = prev_positions[ticker].get("live_value", prev_positions[ticker].get("value", 0))
            if prev_value > 0:
                change_pct = (curr_value - prev_value) / prev_value * 100
                performers.append({
                    "ticker": ticker,
                    "change_pct": change_pct,
                    "change": curr_value - prev_value,
                    "curr_value": curr_value
                })
    
    performers.sort(key=lambda x: x["change_pct"], reverse=True)
    best = performers[:5]
    worst = performers[-5:]
    
    # Plays this week
    plays = load_plays_this_week(week_start, week_end)
    buys = [p for p in plays if p["action"] in ("BUY", "ADD")]
    sells = [p for p in plays if p["action"] in ("SELL", "TRIM")]
    
    # Build report
    report = {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "generated": datetime.now(timezone.utc).isoformat(),
        "portfolio": {
            "current_value": round(current_total, 2),
            "prev_value": round(prev_total, 2) if prev_total > 0 else None,
            "weekly_pnl": round(weekly_pnl, 2),
            "weekly_pnl_pct": round(weekly_pnl_pct, 2),
            "positions_count": len(current_positions),
        },
        "grade_changes": {
            "upgrades": upgrades,
            "downgrades": downgrades,
        },
        "performers": {
            "best": best,
            "worst": worst,
        },
        "plays": {
            "buys": buys,
            "sells": sells,
            "total_plays": len(plays),
        },
    }
    
    # Save JSON (legacy)
    report_file = REPORTS_DIR / f"weekly_report_{week_start.isoformat()}.json"
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2)
    
    # Generate Markdown
    md = generate_markdown(report)
    md_file = REPORTS_DIR / f"weekly_report_{week_start.isoformat()}.md"
    with open(md_file, "w") as f:
        f.write(md)
    
    # Snapshot to Supabase history
    try:
        from vox_supabase_sync import snapshot_to_history
        snapshot_to_history(week_start.isoformat())
        print(f"   ✅ Snapshot saved to Supabase history")
    except Exception as e:
        print(f"   ⚠️ Supabase snapshot failed: {e}")
    
    print(f"✅ Weekly report saved: {report_file}")
    print(f"✅ Markdown report: {md_file}")
    
    return report, md
    
    return report, md


def generate_markdown(report):
    """Generate Telegram-friendly markdown report."""
    p = report["portfolio"]
    
    emoji = "🟢" if p["weekly_pnl"] >= 0 else "🔴"
    
    md = f"""📊 **VOX WEEKLY REPORT**
Week of {report["week_start"]} to {report["week_end"]}

{emoji} **PORTFOLIO PERFORMANCE**
• Current Value: **${p["current_value"]:,.2f}**
• Weekly P&L: **${p["weekly_pnl"]:+,.2f}** ({p["weekly_pnl_pct"]:+.2f}%)
• Positions: {p["positions_count"]}

"""
    
    # Best performers
    if report["performers"]["best"]:
        md += "🚀 **TOP PERFORMERS**\n"
        for perf in report["performers"]["best"]:
            md += f"• {perf['ticker']}: **{perf['change_pct']:+.2f}%** (${perf['change']:+,.2f})\n"
        md += "\n"
    
    # Worst performers
    if report["performers"]["worst"]:
        md += "💩 **WORST PERFORMERS**\n"
        for perf in reversed(report["performers"]["worst"]):
            md += f"• {perf['ticker']}: **{perf['change_pct']:+.2f}%** (${perf['change']:+,.2f})\n"
        md += "\n"
    
    # Grade changes
    if report["grade_changes"]["upgrades"]:
        md += "📈 **GRADE UPGRADES**\n"
        for u in report["grade_changes"]["upgrades"]:
            md += f"• {u['ticker']}: {u['prev']} → {u['curr']} (+{u['change']})\n"
        md += "\n"
    
    if report["grade_changes"]["downgrades"]:
        md += "📉 **GRADE DOWNGRADES**\n"
        for d in report["grade_changes"]["downgrades"]:
            md += f"• {d['ticker']}: {d['prev']} → {d['curr']} ({d['change']})\n"
        md += "\n"
    
    # Plays
    if report["plays"]["buys"]:
        md += "🟢 **BUYS THIS WEEK**\n"
        for play in report["plays"]["buys"]:
            md += f"• {play['action']} {play['ticker']}: {play['shares']:.2f} sh @ ${play['price']:.2f} = ${play['notional']:.2f}\n"
        md += "\n"
    
    if report["plays"]["sells"]:
        md += "🔴 **SELLS THIS WEEK**\n"
        for play in report["plays"]["sells"]:
            md += f"• {play['action']} {play['ticker']}: {play['shares']:.2f} sh @ ${play['price']:.2f}\n"
        md += "\n"
    
    md += "---\n*Generated by VOX Weekly Report*"
    
    return md


def main():
    report, md = generate_weekly_report()
    
    # Print markdown for Telegram
    print("\n" + "=" * 60)
    print("TELEGRAM OUTPUT:")
    print("=" * 60)
    print(md)
    
    return report


if __name__ == "__main__":
    main()
