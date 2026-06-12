#!/usr/bin/env python3
"""
VOX Insights Generator v1.0
Generates proactive insights - not just data, but "what it means".

Reads all agent outputs, synthesizes into actionable intelligence.

Usage:
    python3 vox_insights_generator.py generate
    python3 vox_insights_generator.py dashboard
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

SCRIPTS_DIR = Path.home() / ".hermes" / "scripts"
DASHBOARD_DIR = Path.home() / "dev" / "vox-dashboard" / "public"


def load_json(filename: str) -> Dict:
    """Load a JSON file from scripts dir"""
    filepath = SCRIPTS_DIR / filename
    if filepath.exists():
        with open(filepath) as f:
            return json.load(f)
    return {}


def generate_insights() -> List[Dict]:
    """Generate insights from all agent outputs"""
    insights = []
    
    # 1. Portfolio Status
    portfolio = load_json("dashboard_positions.json")
    if portfolio:
        positions = portfolio.get("positions", [])
        total_value = portfolio.get("total_value", 0)
        
        # Find worst performers
        losers = sorted([p for p in positions if p.get("pnl", 0) < 0], 
                       key=lambda x: x["pnl"])[:3]
        
        if losers:
            insights.append({
                "id": "portfolio_losers",
                "priority": "high",
                "icon": "📉",
                "title": f"{len([p for p in positions if p.get('pnl', 0) < -500])} positions losing >$500",
                "body": f"Worst: {', '.join(p['ticker'] + ' ($' + str(abs(int(p['pnl']))) + ')' for p in losers)}",
                "action": "Review Portfolio",
                "action_link": "/portfolio",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        
        # Grade distribution
        low_grades = [p for p in positions if p.get("grade", 0) > 0 and p.get("grade", 0) < 45]
        if low_grades:
            insights.append({
                "id": "low_grades",
                "priority": "high",
                "icon": "🔴",
                "title": f"{len(low_grades)} positions with grade < 45 (SELL zone)",
                "body": f"Top: {', '.join(p['ticker'] for p in sorted(low_grades, key=lambda x: x['grade'])[:3])}",
                "action": "View Plays",
                "action_link": "/plays",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
    
    # 2. Market Regime
    regime = load_json("vox_market_regime.json")
    if regime:
        adjustments = regime.get("strategy_adjustments", {})
        insights.append({
            "id": "market_regime",
            "priority": "medium",
            "icon": "🌍",
            "title": f"Market: {regime.get('regime', 'Unknown')}",
            "body": f"Grade threshold: {adjustments.get('grade_threshold', 50)} | Position size: {adjustments.get('position_size', 1.0)}x | Stop: {adjustments.get('stop_loss', 10)}%",
            "action": "Check Intelligence",
            "action_link": "/intelligence",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    
    # 3. Crypto Alert
    if portfolio:
        crypto_tickers = ["BTC", "ETH", "BNB", "SOL", "DOGE", "XRP", "ADA", "TRX", "SUI"]
        crypto_value = sum(p["value"] for p in positions if p["ticker"] in crypto_tickers)
        crypto_pct = crypto_value / total_value * 100 if total_value > 0 else 0
        
        if crypto_pct > 10:
            insights.append({
                "id": "crypto_overweight",
                "priority": "high",
                "icon": "⚠️",
                "title": f"Crypto overweight: {crypto_pct:.1f}% (limit 10%)",
                "body": f"${crypto_value:,.0f} in crypto. Consider trimming to rebalance.",
                "action": "Rebalance",
                "action_link": "/rebalancing",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
    
    # 4. Technical Signals
    tech = load_json("vox_technical_analysis.json")
    if tech and tech.get("results"):
        bullish = [r for r in tech["results"] if r.get("conviction", 0) > 30]
        bearish = [r for r in tech["results"] if r.get("conviction", 0) < -30]
        
        if bullish:
            insights.append({
                "id": "technical_bullish",
                "priority": "low",
                "icon": "🟢",
                "title": f"{len(bullish)} positions technically bullish",
                "body": f"Strongest: {', '.join(r['ticker'] for r in sorted(bullish, key=lambda x: x['conviction'], reverse=True)[:3])}",
                "action": "View Watchlist",
                "action_link": "/watchlist",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
    
    # 5. Earnings Alert
    earnings = load_json("vox_earnings_calendar.json")
    if earnings and earnings.get("upcoming"):
        upcoming = earnings["upcoming"]
        high_impact = [e for e in upcoming if e.get("urgency") == "HIGH"]
        
        if high_impact:
            insights.append({
                "id": "earnings_alert",
                "priority": "medium",
                "icon": "📅",
                "title": f"{len(high_impact)} high-impact earnings this week",
                "body": f"{', '.join(e['ticker'] + ' (' + e['date'] + ')' for e in high_impact)}",
                "action": "View Earnings",
                "action_link": "/earnings",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
    
    # 6. Sector Rotation
    rotation = load_json("vox_sector_rotation.json")
    if rotation and rotation.get("rotation"):
        rot = rotation["rotation"]
        if rot.get("strength") != "NONE":
            insights.append({
                "id": "sector_rotation",
                "priority": "medium",
                "icon": "🔄",
                "title": f"Sector rotation: {rot.get('strength', 'Unknown')}",
                "body": f"Money flowing TO: {', '.join(rot.get('to', []))} | FROM: {', '.join(rot.get('from', []))}",
                "action": "View Sectors",
                "action_link": "/sector-macro",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
    
    # 7. Volume Spikes
    volume = load_json("vox_volume_scan.json")
    if volume and volume.get("alerts"):
        alerts = volume["alerts"]
        strong = [a for a in alerts if "STRONG" in a.get("alert", "")]
        
        if strong:
            insights.append({
                "id": "volume_spike",
                "priority": "medium",
                "icon": "📊",
                "title": f"{len(strong)} volume spikes detected",
                "body": f"{', '.join(a['ticker'] for a in strong[:3])}",
                "action": "View Screener",
                "action_link": "/screener",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
    
    # 8. Council Consensus
    council = load_json("vox_council_votes.json")
    if council and council.get("results"):
        sells = [r for r in council["results"] if r.get("consensus") == "SELL"]
        if sells:
            insights.append({
                "id": "council_sell",
                "priority": "high",
                "icon": "🗳️",
                "title": f"Agent Council: SELL {len(sells)} positions",
                "body": f"Consensus: {', '.join(s['ticker'] for s in sells[:3])}",
                "action": "View Council",
                "action_link": "/council",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
    
    # Sort by priority
    priority_order = {"high": 0, "medium": 1, "low": 2}
    insights.sort(key=lambda x: priority_order.get(x["priority"], 3))
    
    return insights


def save_insights(insights: List[Dict]):
    """Save insights to scripts and dashboard"""
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "count": len(insights),
        "high_priority": len([i for i in insights if i["priority"] == "high"]),
        "insights": insights,
    }
    
    # Save to scripts
    with open(SCRIPTS_DIR / "vox_insights.json", 'w') as f:
        json.dump(output, f, indent=2)
    
    # Save to dashboard
    if DASHBOARD_DIR.exists():
        with open(DASHBOARD_DIR / "vox_insights.json", 'w') as f:
            json.dump(output, f, indent=2)
    
    print(f"✅ Saved {len(insights)} insights")


def print_insights(insights: List[Dict]):
    """Print insights to console"""
    print(f"\n💡 VOX INSIGHTS ({len(insights)} found)")
    print("=" * 70)
    
    for insight in insights:
        emoji = "🔴" if insight["priority"] == "high" else "🟡" if insight["priority"] == "medium" else "⚪"
        print(f"\n{emoji} {insight['title']}")
        print(f"   {insight['body']}")
        print(f"   → {insight['action']}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="VOX Insights Generator")
    parser.add_argument("command", choices=["generate", "dashboard", "print"])
    
    args = parser.parse_args()
    
    insights = generate_insights()
    
    if args.command == "generate":
        save_insights(insights)
        print_insights(insights)
    elif args.command == "dashboard":
        save_insights(insights)
        print(f"✅ Dashboard insights updated ({len(insights)} insights)")
    elif args.command == "print":
        print_insights(insights)


if __name__ == "__main__":
    main()
