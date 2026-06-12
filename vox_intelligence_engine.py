#!/usr/bin/env python3
"""
VOX Intelligence Engine v2.0
Generates comprehensive intelligence from ALL tracking sources.

Reads:
- Trump alerts
- Volume spikes
- Earnings calendar
- Sector rotation
- Market regime
- Sentiment report
- Macro report
- Portfolio positions
- Agent council outputs

Generates:
- vox_intelligence.json — structured feed
- vox_intelligence_summary.md — human-readable summary
"""

import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List

SCRIPTS_DIR = Path.home() / ".hermes" / "scripts"
DASHBOARD_DIR = Path.home() / "dev" / "vox-dashboard" / "public"

def load_json(filename: str, default=None):
    try:
        with open(SCRIPTS_DIR / filename) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default or {}

def generate_intelligence():
    now = datetime.now(timezone.utc)
    
    # Load ALL data sources
    portfolio = load_json("dashboard_positions.json", {})
    positions = portfolio.get("positions", [])
    
    earnings = load_json("vox_earnings_calendar.json", {})
    sector = load_json("vox_sector_rotation.json", {})
    regime = load_json("vox_market_regime.json", {})
    sentiment = load_json("vox_sentiment_report.json", {})
    macro = load_json("vox_macro_report.json", {})
    insights = load_json("vox_insights.json", {})
    predictions = load_json("vox_predictions.json", {})
    council = load_json("vox_council_votes.json", {})
    
    intelligence_items = []
    
    # 1. MACRO ALERTS (Highest priority)
    if macro.get("macro_regime") == "HOSTILE":
        intelligence_items.append({
            "category": "MACRO",
            "priority": "HIGH",
            "title": f"Macro regime: {macro['macro_regime']}",
            "body": f"Fed restrictive at {macro['fed']['fed_funds_rate']}%, yield curve inverted. Defensive positioning recommended.",
            "tickers": [],
            "action": "Reduce Risk",
            "source": "macro",
            "timestamp": now.isoformat(),
        })
    
    for alert in macro.get("alerts", []):
        intelligence_items.append({
            "category": "MACRO",
            "priority": alert.get("level", "MEDIUM"),
            "title": alert["message"][:60],
            "body": alert["message"],
            "tickers": [],
            "action": "Review Exposure",
            "source": "macro",
            "timestamp": now.isoformat(),
        })
    
    # 2. SENTIMENT ALERTS
    if sentiment.get("overall_sentiment") in ["EXTREME_GREED", "EXTREME_FEAR"]:
        intelligence_items.append({
            "category": "SENTIMENT",
            "priority": "HIGH",
            "title": f"Sentiment: {sentiment['overall_sentiment']}",
            "body": f"Fear/Greed index at {sentiment.get('fear_greed', {}).get('index', 50)}. {sentiment.get('alerts', [{}])[0].get('message', 'Extreme sentiment detected.')}",
            "tickers": [],
            "action": sentiment.get("alerts", [{}])[0].get("action", "Monitor"),
            "source": "sentiment",
            "timestamp": now.isoformat(),
        })
    
    # 3. PORTFOLIO ALERTS
    big_losers = [p for p in positions if p.get("pnl", 0) < -500]
    if big_losers:
        total_loss = sum(p["pnl"] for p in big_losers)
        intelligence_items.append({
            "category": "PORTFOLIO",
            "priority": "HIGH",
            "title": f"{len(big_losers)} positions losing >$500",
            "body": f"Total unrealized loss: ${abs(total_loss):,.0f}. Review stops and thesis.",
            "tickers": [p["ticker"] for p in big_losers],
            "action": "Review Portfolio",
            "source": "portfolio",
            "timestamp": now.isoformat(),
        })
    
    big_winners = [p for p in positions if p.get("pnl", 0) > 5000]
    if big_winners:
        total_gain = sum(p["pnl"] for p in big_winners)
        intelligence_items.append({
            "category": "PORTFOLIO",
            "priority": "MEDIUM",
            "title": f"{len(big_winners)} positions up >$5,000",
            "body": f"Total unrealized gain: ${total_gain:,.0f}. Consider trailing stops.",
            "tickers": [p["ticker"] for p in big_winners],
            "action": "Set Trailing Stops",
            "source": "portfolio",
            "timestamp": now.isoformat(),
        })
    
    # 4. CRYPTO ALERT
    crypto_tickers = ["BTC", "ETH", "BNB", "SOL", "DOGE", "XRP", "ADA", "TRX"]
    crypto_positions = [p for p in positions if p["ticker"] in crypto_tickers]
    crypto_value = sum(p["value"] for p in crypto_positions)
    total_value = portfolio.get("total_value", 197818)
    crypto_pct = (crypto_value / total_value) * 100 if total_value > 0 else 0
    
    if crypto_pct > 10:
        intelligence_items.append({
            "category": "CRYPTO",
            "priority": "HIGH",
            "title": f"Crypto overweight: {crypto_pct:.1f}%",
            "body": f"Crypto allocation is {crypto_pct:.1f}% (limit 10%). Value: ${crypto_value:,.0f}. Trim speculative positions.",
            "tickers": [p["ticker"] for p in crypto_positions],
            "action": "Rebalance Crypto",
            "source": "portfolio",
            "timestamp": now.isoformat(),
        })
    
    # 5. EARNINGS ALERTS
    upcoming_earnings = earnings.get("upcoming", [])
    portfolio_tickers = {p["ticker"] for p in positions}
    
    for earn in upcoming_earnings:
        if earn.get("ticker") in portfolio_tickers:
            days = earn.get("days_until", 0)
            if days <= 3:
                priority = "HIGH"
            elif days <= 7:
                priority = "MEDIUM"
            else:
                priority = "LOW"
            
            intelligence_items.append({
                "category": "EARNINGS",
                "priority": priority,
                "title": f"{earn['ticker']} earnings in {days} days",
                "body": f"Earnings on {earn.get('date', 'soon')}. Estimate: ${earn.get('eps_estimate', 'N/A')}. Consider position size before event.",
                "tickers": [earn["ticker"]],
                "action": "Review Position",
                "source": "earnings",
                "timestamp": now.isoformat(),
            })
    
    # 6. SECTOR ROTATION
    leading_sectors = sector.get("leading", [])
    if leading_sectors:
        intelligence_items.append({
            "category": "SECTOR",
            "priority": "MEDIUM",
            "title": f"Leading sectors: {', '.join(leading_sectors[:3])}",
            "body": f"Sector momentum detected in {', '.join(leading_sectors[:3])}. Consider adding exposure via ETFs or leaders.",
            "tickers": [],
            "action": "Check Screener",
            "source": "sector",
            "timestamp": now.isoformat(),
        })
    
    # 7. MARKET REGIME
    regime_name = regime.get("regime", "UNKNOWN")
    if regime_name in ["EARLY_BEAR", "LATE_BEAR", "VOLATILE"]:
        intelligence_items.append({
            "category": "REGIME",
            "priority": "HIGH",
            "title": f"Market regime: {regime_name}",
            "body": f"Risk-off environment detected. Reduce exposure, raise cash, tighten stops.",
            "tickers": [],
            "action": "Defensive Positioning",
            "source": "regime",
            "timestamp": now.isoformat(),
        })
    elif regime_name == "EARLY_BULL":
        intelligence_items.append({
            "category": "REGIME",
            "priority": "MEDIUM",
            "title": f"Market regime: {regime_name}",
            "body": f"Risk-on environment. Add to winners, buy dips.",
            "tickers": [],
            "action": "Offensive Positioning",
            "source": "regime",
            "timestamp": now.isoformat(),
        })
    
    # 8. COUNCIL SIGNALS
    council_signals = []
    for result in council.get("results", []):
        ticker = result.get("ticker", "")
        consensus = result.get("consensus", "HOLD")
        confidence = result.get("consensus_pct", 0)
        
        if consensus in ["BUY", "SELL"] and confidence >= 75:
            council_signals.append({
                "ticker": ticker,
                "signal": consensus,
                "confidence": confidence,
            })
    
    for signal in council_signals[:3]:
        intelligence_items.append({
            "category": "COUNCIL",
            "priority": "MEDIUM",
            "title": f"Council: {signal['ticker']} {signal['signal']}",
            "body": f"Agent consensus: {signal['signal']} with {signal['confidence']:.0f}% confidence.",
            "tickers": [signal["ticker"]],
            "action": f"Review {signal['ticker']}",
            "source": "council",
            "timestamp": now.isoformat(),
        })
    
    # 9. PREDICTIONS
    pred_list = predictions.get("predictions", [])
    high_confidence = [p for p in pred_list if p.get("confidence", 0) > 60]
    for pred in high_confidence[:3]:
        intelligence_items.append({
            "category": "PREDICTION",
            "priority": "LOW",
            "title": f"{pred['ticker']}: {pred.get('direction', 'N/A')} ({pred.get('confidence', 0)}%)",
            "body": f"Target: {pred.get('target', 'N/A')}. Timeframe: {pred.get('timeframe', 'N/A')}. Models: {', '.join(pred.get('models', ['unknown']))}.",
            "tickers": [pred["ticker"]],
            "action": "Monitor",
            "source": "prediction",
            "timestamp": now.isoformat(),
        })
    
    # Sort by priority
    priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    intelligence_items.sort(key=lambda x: priority_order.get(x["priority"], 3))
    
    # Build output
    output = {
        "timestamp": now.isoformat(),
        "portfolio_value": total_value,
        "regime": regime_name,
        "sentiment": sentiment.get("overall_sentiment", "UNKNOWN"),
        "macro_regime": macro.get("macro_regime", "UNKNOWN"),
        "total_items": len(intelligence_items),
        "high_priority": len([i for i in intelligence_items if i["priority"] == "HIGH"]),
        "medium_priority": len([i for i in intelligence_items if i["priority"] == "MEDIUM"]),
        "low_priority": len([i for i in intelligence_items if i["priority"] == "LOW"]),
        "items": intelligence_items,
        "sources": list(set(i["source"] for i in intelligence_items)),
    }
    
    # Save
    with open(SCRIPTS_DIR / "vox_intelligence.json", 'w') as f:
        json.dump(output, f, indent=2)
    
    with open(DASHBOARD_DIR / "vox_intelligence.json", 'w') as f:
        json.dump(output, f, indent=2)
    
    # Generate summary
    summary = generate_summary(output)
    with open(SCRIPTS_DIR / "vox_intelligence_summary.md", 'w') as f:
        f.write(summary)
    
    return output

def generate_summary(data: Dict) -> str:
    lines = [
        "# VOX Intelligence Summary",
        f"Generated: {data['timestamp']}",
        f"Portfolio: ${data['portfolio_value']:,.0f}",
        f"Market Regime: {data['regime']}",
        f"Macro Regime: {data['macro_regime']}",
        f"Sentiment: {data['sentiment']}",
        "",
        "## Priority Overview",
        f"- 🔴 High: {data['high_priority']}",
        f"- 🟡 Medium: {data['medium_priority']}",
        f"- ⚪ Low: {data['low_priority']}",
        f"- Total: {data['total_items']}",
        "",
        "## Active Intelligence",
        "",
    ]
    
    for item in data["items"]:
        emoji = "🔴" if item["priority"] == "HIGH" else "🟡" if item["priority"] == "MEDIUM" else "⚪"
        lines.extend([
            f"### {emoji} {item['title']}",
            f"**Category:** {item['category']} | **Source:** {item['source']}",
            f"**Body:** {item['body']}",
        ])
        if item["tickers"]:
            lines.append(f"**Tickers:** {', '.join(item['tickers'])}")
        lines.extend([
            f"**Action:** {item['action']}",
            "",
        ])
    
    lines.extend([
        "---",
        f"*Sources: {', '.join(data['sources'])}*",
    ])
    
    return "\n".join(lines)

def main():
    print("="*60)
    print("🧠 VOX INTELLIGENCE ENGINE v2.0")
    print("="*60)
    
    data = generate_intelligence()
    
    print(f"\nGenerated {data['total_items']} intelligence items")
    print(f"  🔴 High: {data['high_priority']}")
    print(f"  🟡 Medium: {data['medium_priority']}")
    print(f"  ⚪ Low: {data['low_priority']}")
    print(f"\nRegime: {data['regime']}")
    print(f"Macro: {data['macro_regime']}")
    print(f"Sentiment: {data['sentiment']}")
    print(f"\nSources: {', '.join(data['sources'])}")
    print(f"\nFiles saved:")
    print(f"  ✅ vox_intelligence.json")
    print(f"  ✅ vox_intelligence_summary.md")

if __name__ == "__main__":
    main()
