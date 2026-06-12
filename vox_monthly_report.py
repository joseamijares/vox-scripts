#!/usr/bin/env python3
"""
VOX Monthly Report Generator
Aggregates weekly reports into monthly summary.
Shows cumulative P&L, win rate, best/worst plays.
"""

import json
import glob
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"
REPORTS_DIR = SCRIPT_DIR / "reports"
PLAYS_FILE = SCRIPT_DIR / "vox_historic_plays.jsonl"

def ensure_dirs():
    REPORTS_DIR.mkdir(exist_ok=True)

def load_weekly_reports(year, month):
    """Load all weekly reports for a month."""
    pattern = REPORTS_DIR / f"weekly_report_{year}-{month:02d}-*.json"
    reports = []
    for f in sorted(glob.glob(str(pattern))):
        with open(f) as fp:
            reports.append(json.load(fp))
    return reports

def load_all_plays():
    """Load all historic plays."""
    if not PLAYS_FILE.exists():
        return []
    plays = []
    with open(PLAYS_FILE) as f:
        for line in f:
            plays.append(json.loads(line.strip()))
    return plays

def generate_monthly_report(year=None, month=None):
    """Generate monthly report."""
    ensure_dirs()
    
    if not year or not month:
        now = datetime.now(timezone.utc)
        year = now.year
        month = now.month
    
    # Load weekly reports
    weekly_reports = load_weekly_reports(year, month)
    
    # Load all plays
    all_plays = load_all_plays()
    
    # Filter plays to this month
    month_plays = []
    for play in all_plays:
        play_date = datetime.fromisoformat(play["timestamp"]).date()
        if play_date.year == year and play_date.month == month:
            month_plays.append(play)
    
    # Calculate stats
    closed_plays = [p for p in month_plays if p.get("closed", False)]
    open_plays = [p for p in month_plays if not p.get("closed", False) and p["action"] in ("BUY", "ADD")]
    
    wins = [p for p in closed_plays if p.get("pnl", 0) > 0]
    losses = [p for p in closed_plays if p.get("pnl", 0) <= 0]
    
    total_pnl = sum(p.get("pnl", 0) for p in closed_plays)
    total_buys = sum(p.get("notional", 0) for p in month_plays if p["action"] in ("BUY", "ADD"))
    total_sells = sum(p.get("notional", 0) for p in month_plays if p["action"] in ("SELL", "TRIM"))
    
    # Weekly P&L from reports
    weekly_pnls = [r["portfolio"]["weekly_pnl"] for r in weekly_reports if r["portfolio"].get("prev_value")]
    
    # Best/worst closed plays
    best_play = max(closed_plays, key=lambda x: x.get("pnl", 0)) if closed_plays else None
    worst_play = min(closed_plays, key=lambda x: x.get("pnl", 0)) if closed_plays else None
    
    report = {
        "year": year,
        "month": month,
        "generated": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_plays": len(month_plays),
            "closed_plays": len(closed_plays),
            "open_plays": len(open_plays),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / len(closed_plays) * 100, 1) if closed_plays else 0,
            "total_pnl": round(total_pnl, 2),
            "total_buys": round(total_buys, 2),
            "total_sells": round(total_sells, 2),
            "weekly_pnls": weekly_pnls,
        },
        "best_play": best_play,
        "worst_play": worst_play,
        "all_plays": month_plays,
    }
    
    # Save JSON (legacy)
    report_file = REPORTS_DIR / f"monthly_report_{year}-{month:02d}.json"
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2, default=str)
    
    # Generate Markdown
    md = generate_markdown(report)
    md_file = REPORTS_DIR / f"monthly_report_{year}-{month:02d}.md"
    with open(md_file, "w") as f:
        f.write(md)
    
    print(f"✅ Monthly report saved: {report_file}")
    return report, md


def generate_markdown(report):
    """Generate Telegram-friendly markdown."""
    s = report["summary"]
    
    emoji = "🟢" if s["total_pnl"] >= 0 else "🔴"
    
    md = f"""📊 **VOX MONTHLY REPORT**
{report['year']}-{report['month']:02d}

{emoji} **MONTHLY PERFORMANCE**
• Total P&L: **${s['total_pnl']:+,.2f}**
• Win Rate: **{s['win_rate']:.1f}%** ({s['wins']}W / {s['losses']}L)
• Plays: {s['total_plays']} ({s['closed_plays']} closed, {s['open_plays']} open)
• Capital Deployed: ${s['total_buys']:,.2f}
• Capital Recovered: ${s['total_sells']:,.2f}

"""
    
    if s["weekly_pnls"]:
        md += "📈 **WEEKLY BREAKDOWN**\n"
        for i, pnl in enumerate(s["weekly_pnls"], 1):
            e = "🟢" if pnl >= 0 else "🔴"
            md += f"• Week {i}: {e} ${pnl:+,.2f}\n"
        md += "\n"
    
    if report["best_play"]:
        bp = report["best_play"]
        md += f"🏆 **BEST PLAY**\n"
        md += f"• {bp['ticker']}: ${bp.get('pnl', 0):+,.2f} ({bp.get('pnl_pct', 0):+.2f}%)\n"
        md += f"• Entry: ${bp['price']:.2f} → Exit: ${bp.get('exit_price', 0):.2f}\n\n"
    
    if report["worst_play"]:
        wp = report["worst_play"]
        md += f"💩 **WORST PLAY**\n"
        md += f"• {wp['ticker']}: ${wp.get('pnl', 0):+,.2f} ({wp.get('pnl_pct', 0):+.2f}%)\n"
        md += f"• Entry: ${wp['price']:.2f} → Exit: ${wp.get('exit_price', 0):.2f}\n\n"
    
    # All plays
    if report["all_plays"]:
        md += "📋 **ALL PLAYS**\n"
        for play in report["all_plays"]:
            pnl = play.get("pnl") or 0
            status = "🟢" if pnl > 0 else "🔴" if play.get("closed", False) else "⚪"
            md += f"• {status} {play['action']} {play['ticker']}: {play['shares']:.2f} sh @ ${play['price']:.2f}"
            if play.get("closed"):
                md += f" → ${play.get('exit_price', 0):.2f} | ${pnl:+,.2f}"
            md += "\n"
        md += "\n"
    
    md += "---\n*Generated by VOX Monthly Report*"
    return md


def main():
    report, md = generate_monthly_report()
    
    print("\n" + "=" * 60)
    print("TELEGRAM OUTPUT:")
    print("=" * 60)
    print(md)
    
    return report


if __name__ == "__main__":
    main()
