#!/usr/bin/env python3
"""
Politician Insider Trading Tracker — JOS-31
Tracks congressional stock trades for alpha signals.
Sources: Quiver Quant, House/Senate Stock Watcher
"""

import os
import json
import urllib.request
from pathlib import Path
from datetime import datetime, timedelta


def load_env():
    env_path = Path.home() / ".hermes" / ".env"
    keys = {}
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    keys[key] = val
    return keys


def quiver_get(endpoint):
    """Quiver Quantitative API GET."""
    env = load_env()
    api_key = env.get("QUIVER_API_KEY", "")
    if not api_key:
        return {"error": "QUIVER_API_KEY not set"}

    url = f"https://api.quiverquant.com/beta{endpoint}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Token {api_key}",
            "Accept": "application/json",
            "User-Agent": "Vox-Finance/1.0"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}", "details": e.read().decode()[:200]}
    except Exception as e:
        return {"error": str(e)}


def get_congress_trades(ticker=None, politician=None, days=30):
    """Get recent congressional trades."""
    if ticker:
        data = quiver_get(f"/live/congresstrading?ticker={ticker}")
    elif politician:
        data = quiver_get(f"/live/congresstrading?representative={politician}")
    else:
        data = quiver_get("/live/congresstrading")

    if isinstance(data, list):
        # Filter recent trades
        cutoff = datetime.now() - timedelta(days=days)
        recent = []
        for trade in data:
            trade_date = trade.get("TransactionDate", "")
            if trade_date:
                try:
                    td = datetime.strptime(trade_date, "%Y-%m-%d")
                    if td >= cutoff:
                        recent.append(trade)
                except:
                    pass
        return recent
    return []


def get_top_politicians():
    """Get list of politicians with most trading activity."""
    data = quiver_get("/live/congresstrading")
    if not isinstance(data, list):
        return []

    # Count trades by politician
    counts = {}
    for trade in data:
        name = trade.get("Representative", "Unknown")
        counts[name] = counts.get(name, 0) + 1

    return sorted(counts.items(), key=lambda x: x[1], reverse=True)[:20]


def analyze_trade(trade):
    """Analyze a single trade for signals."""
    ticker = trade.get("Ticker", "")
    politician = trade.get("Representative", "Unknown")
    action = trade.get("Transaction", "")  # Purchase or Sale
    amount = trade.get("Amount", "")
    date = trade.get("TransactionDate", "")
    asset_type = trade.get("AssetType", "")

    # Determine signal
    signal = "BUY" if "Purchase" in action else "SELL" if "Sale" in action else "UNKNOWN"

    # Amount range parsing
    amount_map = {
        "$1,001 - $15,000": "small",
        "$15,001 - $50,000": "medium",
        "$50,001 - $100,000": "large",
        "$100,001 - $250,000": "very_large",
        "$250,001 - $500,000": "huge",
        "$500,001 - $1,000,000": "massive",
        "$1,000,001+": "whale",
    }
    size = amount_map.get(amount, "unknown")

    return {
        "ticker": ticker,
        "politician": politician,
        "signal": signal,
        "amount": amount,
        "size": size,
        "date": date,
        "asset_type": asset_type,
        "raw": trade,
    }


def format_alert(trade_analysis):
    """Format a trade alert."""
    emoji = "🟢" if trade_analysis["signal"] == "BUY" else "🔴" if trade_analysis["signal"] == "SELL" else "⚪"
    size_emoji = "🐋" if trade_analysis["size"] in ["huge", "massive", "whale"] else "🐟" if trade_analysis["size"] in ["medium", "large"] else "🦐"

    return f"""{emoji} {size_emoji} POLITICIAN TRADE ALERT

{trade_analysis['politician']} — {trade_analysis['signal']} {trade_analysis['ticker']}
Amount: {trade_analysis['amount']}
Date: {trade_analysis['date']}
Asset: {trade_analysis['asset_type']}

_Note: Trade disclosed ~30-45 days after execution._
"""


def run_tracker():
    """Main tracker runner."""
    print("=" * 70)
    print("🏛️ POLITICIAN INSIDER TRADING TRACKER")
    print("=" * 70)
    print(f"Scan time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Check if API key is configured
    env = load_env()
    if not env.get("QUIVER_API_KEY"):
        print("⚠️ QUIVER_API_KEY not set in ~/.hermes/.env")
        print()
        print("To get a free API key:")
        print("1. Go to https://www.quiverquant.com/")
        print("2. Sign up for free account")
        print("3. Get API key from dashboard")
        print("4. Add to ~/.hermes/.env: QUIVER_API_KEY=your_key")
        print()
        print("Alternative: Use House/Senate Stock Watcher (no API key needed)")
        print("- https://housestockwatcher.com/")
        print("- https://senatestockwatcher.com/")
        return

    # Get top politicians
    print("Fetching top trading politicians...")
    top_politicians = get_top_politicians()
    print(f"\nTop 10 Most Active Traders (last 30 days):")
    for i, (name, count) in enumerate(top_politicians[:10], 1):
        print(f"{i:2}. {name:30} | {count:3} trades")

    # Get recent trades for our watchlist
    print("\n" + "=" * 70)
    print("RECENT TRADES FOR WATCHLIST")
    print("=" * 70)

    watchlist = ["AAPL", "MSFT", "GOOGL", "NVDA", "TSLA", "AMZN", "META", "PLTR", "WDC", "AMD"]
    all_trades = []

    for ticker in watchlist:
        trades = get_congress_trades(ticker=ticker, days=60)
        if trades:
            print(f"\n{ticker}:")
            for trade in trades[:3]:  # Top 3 per ticker
                analysis = analyze_trade(trade)
                all_trades.append(analysis)
                print(f"  {analysis['signal']:4} | {analysis['politician']:25} | {analysis['amount']}")

    # Save results
    out_path = Path.home() / ".hermes" / "scripts" / "politician_tracker_results.json"
    with open(out_path, "w") as f:
        json.dump({
            "scan_time": datetime.now().isoformat(),
            "politicians_tracked": len(top_politicians),
            "trades_found": len(all_trades),
            "trades": all_trades,
        }, f, indent=2)

    print(f"\n💾 Saved to: {out_path}")


def main():
    run_tracker()


if __name__ == "__main__":
    main()
