#!/usr/bin/env python3
"""
VOX P&L Attribution v1.0
Attributes returns to: strategy, sector, agent, timing.

Usage:
    python3 vox_pnl_attribution.py analyze
    python3 vox_pnl_attribution.py report
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

TRADES_FILE = Path.home() / ".hermes" / "scripts" / "vox_trade_journal.json"
GRADES_FILE = Path.home() / ".hermes" / "scripts" / "portfolio_grades.json"


def load_trades() -> List[Dict]:
    if TRADES_FILE.exists():
        with open(TRADES_FILE) as f:
            data = json.load(f)
            return data.get("trades", [])
    return []


def load_grades() -> Dict:
    if GRADES_FILE.exists():
        with open(GRADES_FILE) as f:
            return json.load(f)
    return {}


def analyze_attribution() -> Dict:
    """Analyze P&L attribution"""
    trades = load_trades()
    grades = load_grades()
    
    closed = [t for t in trades if t["status"] == "CLOSED" and t.get("pnl") is not None]
    
    if not closed:
        print("📊 No closed trades to analyze")
        return {}
    
    print("\n📊 P&L ATTRIBUTION ANALYSIS")
    print("=" * 70)
    
    # By action
    by_action = {}
    for t in closed:
        action = t["action"]
        if action not in by_action:
            by_action[action] = []
        by_action[action].append(t["pnl"])
    
    print("\n📈 By Action:")
    for action, pnls in by_action.items():
        total = sum(pnls)
        avg = total / len(pnls)
        win_rate = len([p for p in pnls if p > 0]) / len(pnls) * 100
        print(f"   {action:8} | Trades: {len(pnls)} | Total: ${total:+,.2f} | Avg: ${avg:+,.2f} | Win: {win_rate:.0f}%")
    
    # By grade at entry
    by_grade = {
        "high (70+)": [],
        "medium (50-69)": [],
        "low (<50)": [],
    }
    
    for t in closed:
        grade = grades.get(t["ticker"], {}).get("grade", 0)
        if grade >= 70:
            by_grade["high (70+)"].append(t["pnl"])
        elif grade >= 50:
            by_grade["medium (50-69)"].append(t["pnl"])
        else:
            by_grade["low (<50)"].append(t["pnl"])
    
    print("\n📊 By Grade at Entry:")
    for grade_range, pnls in by_grade.items():
        if pnls:
            total = sum(pnls)
            avg = total / len(pnls)
            win_rate = len([p for p in pnls if p > 0]) / len(pnls) * 100
            print(f"   {grade_range:15} | Trades: {len(pnls)} | Total: ${total:+,.2f} | Avg: ${avg:+,.2f} | Win: {win_rate:.0f}%")
    
    # By broker
    by_broker = {}
    for t in closed:
        broker = t.get("broker", "unknown")
        if broker not in by_broker:
            by_broker[broker] = []
        by_broker[broker].append(t["pnl"])
    
    print("\n🏦 By Broker:")
    for broker, pnls in by_broker.items():
        total = sum(pnls)
        avg = total / len(pnls)
        print(f"   {broker:12} | Trades: {len(pnls)} | Total: ${total:+,.2f} | Avg: ${avg:+,.2f}")
    
    # Time-based (holding period)
    short_term = []  # < 7 days
    medium_term = []  # 7-30 days
    long_term = []  # > 30 days
    
    for t in closed:
        if t.get("exit_date") and t.get("timestamp"):
            entry = datetime.fromisoformat(t["timestamp"])
            exit_d = datetime.fromisoformat(t["exit_date"])
            days = (exit_d - entry).days
            
            if days < 7:
                short_term.append(t["pnl"])
            elif days < 30:
                medium_term.append(t["pnl"])
            else:
                long_term.append(t["pnl"])
    
    print("\n⏱️ By Holding Period:")
    for label, pnls in [("Short (<7d)", short_term), ("Medium (7-30d)", medium_term), ("Long (>30d)", long_term)]:
        if pnls:
            total = sum(pnls)
            avg = total / len(pnls)
            print(f"   {label:15} | Trades: {len(pnls)} | Total: ${total:+,.2f} | Avg: ${avg:+,.2f}")
    
    # Overall
    total_pnl = sum(t["pnl"] for t in closed)
    print(f"\n💰 TOTAL P&L: ${total_pnl:+,.2f} across {len(closed)} trades")
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_trades": len(closed),
        "total_pnl": total_pnl,
        "by_action": {k: {"total": sum(v), "count": len(v)} for k, v in by_action.items()},
    }


def generate_report():
    """Generate comprehensive report"""
    attribution = analyze_attribution()
    
    if not attribution:
        return
    
    # Save
    output_file = Path.home() / ".hermes" / "scripts" / "vox_pnl_attribution.json"
    with open(output_file, 'w') as f:
        json.dump(attribution, f, indent=2)
    
    print(f"\n✅ Saved to {output_file}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="VOX P&L Attribution")
    parser.add_argument("command", choices=["analyze", "report"])
    
    args = parser.parse_args()
    
    if args.command == "analyze":
        analyze_attribution()
    elif args.command == "report":
        generate_report()


if __name__ == "__main__":
    main()
