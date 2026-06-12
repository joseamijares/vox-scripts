#!/usr/bin/env python3
"""
VOX Daily Debrief v1.0
Generates end-of-day learning summary.

What happened today:
- Market moves
- Portfolio performance
- Agent predictions vs reality
- Lessons learned

Usage:
    python3 vox_daily_debrief.py generate
    python3 vox_daily_debrief.py history
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List


def load_portfolio():
    file = Path.home() / ".hermes" / "scripts" / "dashboard_positions.json"
    if file.exists():
        with open(file) as f:
            return json.load(f)
    return None


def load_trades():
    file = Path.home() / ".hermes" / "scripts" / "vox_trade_journal.json"
    if file.exists():
        with open(file) as f:
            return json.load(f)
    return {"trades": []}


def load_council_votes():
    file = Path.home() / ".hermes" / "scripts" / "vox_council_votes.json"
    if file.exists():
        with open(file) as f:
            return json.load(f)
    return {"results": []}


def load_regime():
    file = Path.home() / ".hermes" / "scripts" / "vox_market_regime.json"
    if file.exists():
        with open(file) as f:
            return json.load(f)
    return {}


def generate_debrief():
    """Generate daily learning debrief"""
    portfolio = load_portfolio()
    trades = load_trades()
    council = load_council_votes()
    regime = load_regime()
    
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    print("\n📚 VOX DAILY DEBRIEF")
    print("=" * 70)
    print(f"Date: {today}")
    
    # Market regime
    if regime:
        print(f"\n🌍 Market Regime: {regime.get('regime', 'Unknown')}")
        print(f"   Confidence: {regime.get('confidence', 0)}%")
    
    # Portfolio snapshot
    if portfolio:
        total_value = portfolio.get("total_value", 0)
        total_pnl = portfolio.get("total_pnl", 0)
        print(f"\n💰 Portfolio: ${total_value:,.0f} | P&L: ${total_pnl:+,.0f}")
    
    # Today's trades
    today_trades = []
    for t in trades.get("trades", []):
        trade_date = t["timestamp"][:10]
        if trade_date == today:
            today_trades.append(t)
    
    if today_trades:
        print(f"\n📊 Today's Trades ({len(today_trades)}):")
        for t in today_trades:
            emoji = "🟢" if t.get("pnl", 0) > 0 else "🔴" if t.get("pnl", 0) < 0 else "⚪"
            print(f"   {emoji} {t['action']} {t['ticker']} | ${t.get('pnl', 0):+,.2f}")
    
    # Council accuracy check
    if council.get("results"):
        print(f"\n🗳️ Council Votes Today:")
        for vote in council["results"][:5]:
            print(f"   {vote['ticker']}: {vote['consensus']} ({vote['consensus_pct']:.0f}%)")
            if vote.get("dissent"):
                print(f"      Dissent: {', '.join(d['agent'] for d in vote['dissent'])}")
    
    # Lessons learned (mock - would be AI-generated in production)
    print(f"\n🎓 Lessons Learned:")
    lessons = []
    
    # Check if any SELL signals were missed
    if portfolio:
        positions = portfolio.get("positions", [])
        for pos in positions:
            grade = pos.get("grade", 0)
            pnl = pos.get("pnl", 0)
            if grade and grade < 45 and pnl < -500:
                lessons.append(f"{pos['ticker']}: Grade {grade} but still holding. Loss: ${pnl:,.0f}")
    
    if lessons:
        for lesson in lessons[:3]:
            print(f"   ⚠️ {lesson}")
    else:
        print("   ✅ No major lessons today")
    
    # Action items for tomorrow
    print(f"\n📋 Action Items for Tomorrow:")
    actions = []
    
    if portfolio:
        positions = portfolio.get("positions", [])
        sell_candidates = [p for p in positions if p.get("grade", 0) < 45]
        if sell_candidates:
            actions.append(f"Review {len(sell_candidates)} positions with grade < 45")
        
        crypto_positions = [p for p in positions if p["ticker"] in ["BTC", "ETH", "BNB", "SOL"]]
        crypto_value = sum(p["value"] for p in crypto_positions)
        total_value = portfolio.get("total_value", 1)
        if crypto_value / total_value > 0.10:
            actions.append(f"Trim crypto: {crypto_value/total_value*100:.1f}% (limit 10%)")
    
    if actions:
        for action in actions:
            print(f"   ☐ {action}")
    else:
        print("   ✅ No urgent actions")
    
    # Save
    debrief = {
        "date": today,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "regime": regime.get("regime", "Unknown"),
        "portfolio_value": portfolio.get("total_value", 0) if portfolio else 0,
        "portfolio_pnl": portfolio.get("total_pnl", 0) if portfolio else 0,
        "trades_today": len(today_trades),
        "lessons": lessons,
        "actions": actions,
    }
    
    output_file = Path.home() / ".hermes" / "scripts" / "vox_daily_debrief.json"
    with open(output_file, 'w') as f:
        json.dump(debrief, f, indent=2)
    
    print(f"\n✅ Saved to {output_file}")
    return debrief


def show_history():
    """Show debrief history"""
    print("📜 Debrief history not yet implemented")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="VOX Daily Debrief")
    parser.add_argument("command", choices=["generate", "history"])
    
    args = parser.parse_args()
    
    if args.command == "generate":
        generate_debrief()
    elif args.command == "history":
        show_history()


if __name__ == "__main__":
    main()
