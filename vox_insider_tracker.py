#!/usr/bin/env python3
"""
VOX Insider Tracker v1.0
Tracks insider buying/selling activity.

Usage:
    python3 vox_insider_tracker.py scan
    python3 vox_insider_tracker.py check --ticker TSLA
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List

# Mock insider data (would integrate with SEC API)
INSIDER_ACTIVITY = {
    "TSLA": [
        {"date": "2026-05-20", "insider": "Elon Musk", "type": "SELL", "shares": 10000, "price": 240},
    ],
    "NVDA": [
        {"date": "2026-05-15", "insider": "Jensen Huang", "type": "BUY", "shares": 5000, "price": 210},
    ],
    "AAPL": [
        {"date": "2026-05-10", "insider": "Tim Cook", "type": "SELL", "shares": 20000, "price": 190},
    ],
}

def load_portfolio():
    """Load portfolio tickers"""
    positions_file = Path.home() / ".hermes" / "scripts" / "dashboard_positions.json"
    if not positions_file.exists():
        return []
    
    with open(positions_file) as f:
        data = json.load(f)
    
    return list(set(p["ticker"] for p in data.get("positions", [])))

def analyze_insider_activity(ticker: str) -> Dict:
    """Analyze insider activity for a ticker"""
    activity = INSIDER_ACTIVITY.get(ticker, [])
    
    if not activity:
        return {"ticker": ticker, "activity": [], "signal": "NONE"}
    
    # Calculate net activity
    total_buys = sum(a["shares"] for a in activity if a["type"] == "BUY")
    total_sells = sum(a["shares"] for a in activity if a["type"] == "SELL")
    
    net = total_buys - total_sells
    
    if net > 10000:
        signal = "STRONG_BUY"
    elif net > 0:
        signal = "BUY"
    elif net < -10000:
        signal = "STRONG_SELL"
    elif net < 0:
        signal = "SELL"
    else:
        signal = "NEUTRAL"
    
    return {
        "ticker": ticker,
        "activity": activity,
        "total_buys": total_buys,
        "total_sells": total_sells,
        "net": net,
        "signal": signal,
    }

def scan_portfolio():
    """Scan portfolio for insider activity"""
    tickers = load_portfolio()
    
    print(f"\n👔 INSIDER ACTIVITY SCAN")
    print("=" * 60)
    
    results = []
    signals = []
    
    for ticker in tickers:
        result = analyze_insider_activity(ticker)
        if result["activity"]:
            results.append(result)
            
            if result["signal"] != "NEUTRAL":
                signals.append(result)
                emoji = "🟢" if "BUY" in result["signal"] else "🔴"
                print(f"   {emoji} {ticker:8} | {result['signal']:12} | Net: {result['net']:+,.0f} shares")
                for a in result["activity"]:
                    print(f"      {a['date']} | {a['insider']} | {a['type']} {a['shares']:,} @ ${a['price']}")
    
    if not signals:
        print("   ✅ No significant insider activity")
    
    # Save
    output_file = Path.home() / ".hermes" / "scripts" / "vox_insider_activity.json"
    with open(output_file, 'w') as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "results": results,
            "signals": signals,
        }, f, indent=2)
    
    print(f"\n✅ Saved to {output_file}")
    return results

def main():
    import argparse
    parser = argparse.ArgumentParser(description="VOX Insider Tracker")
    parser.add_argument("command", choices=["scan", "check"])
    parser.add_argument("--ticker", help="Check specific ticker")
    
    args = parser.parse_args()
    
    if args.command == "scan":
        scan_portfolio()
    elif args.command == "check" and args.ticker:
        result = analyze_insider_activity(args.ticker)
        print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
